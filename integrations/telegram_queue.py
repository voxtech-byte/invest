"""
Sovereign Quant V15 — Telegram Rate Limiting & Batching Module

Prevents Telegram API rate limits (max 30 messages/second, 20 messages/minute to same chat)
by implementing a message queue with rate limiting and batching capabilities.
"""

import asyncio
import time
from typing import List, Dict, Any, Optional
from collections import deque
from logger import get_logger

logger = get_logger(__name__)


class TelegramRateLimiter:
    """
    Rate limiter untuk Telegram API dengan:
    - Max 30 messages per second globally
    - Max 20 messages per minute to same chat
    - Message queue dengan backoff
    """
    
    def __init__(self):
        # Global rate limiting: 30 msg/sec
        self.global_window = 1.0  # 1 second window
        self.global_max = 30
        self.global_timestamps: deque = deque()
        
        # Per-chat rate limiting: 20 msg/minute
        self.chat_window = 60.0  # 60 second window
        self.chat_max = 20
        self.chat_timestamps: Dict[str, deque] = {}
        
        self.lock = asyncio.Lock()
    
    async def acquire(self, chat_id: str) -> bool:
        """
        Acquire permission to send message. Returns True if allowed, False if should wait.
        """
        async with self.lock:
            now = time.time()
            
            # Cleanup old timestamps
            self._cleanup_old_timestamps(now)
            
            # Check global rate limit
            if len(self.global_timestamps) >= self.global_max:
                return False
            
            # Check per-chat rate limit
            if chat_id not in self.chat_timestamps:
                self.chat_timestamps[chat_id] = deque()
            
            chat_ts = self.chat_timestamps[chat_id]
            if len(chat_ts) >= self.chat_max:
                return False
            
            # Record this request
            self.global_timestamps.append(now)
            chat_ts.append(now)
            
            return True
    
    def _cleanup_old_timestamps(self, now: float):
        """Remove timestamps outside the rate limit windows."""
        # Cleanup global timestamps
        while self.global_timestamps and (now - self.global_timestamps[0]) > self.global_window:
            self.global_timestamps.popleft()
        
        # Cleanup per-chat timestamps
        for chat_id in list(self.chat_timestamps.keys()):
            chat_ts = self.chat_timestamps[chat_id]
            while chat_ts and (now - chat_ts[0]) > self.chat_window:
                chat_ts.popleft()
            
            # Remove empty chat entries
            if not chat_ts:
                del self.chat_timestamps[chat_id]
    
    async def get_wait_time(self, chat_id: str) -> float:
        """Calculate how long to wait before next message can be sent."""
        async with self.lock:
            now = time.time()
            self._cleanup_old_timestamps(now)
            
            wait_times = []
            
            # Check global limit
            if len(self.global_timestamps) >= self.global_max:
                oldest_global = self.global_timestamps[0]
                wait_times.append(self.global_window - (now - oldest_global))
            
            # Check chat limit
            if chat_id in self.chat_timestamps:
                chat_ts = self.chat_timestamps[chat_id]
                if len(chat_ts) >= self.chat_max:
                    oldest_chat = chat_ts[0]
                    wait_times.append(self.chat_window - (now - oldest_chat))
            
            return max(wait_times) if wait_times else 0.0


class TelegramQueue:
    """
    Async message queue untuk Telegram dengan automatic rate limiting.
    """
    
    def __init__(self):
        self.queue: asyncio.Queue = asyncio.Queue()
        self.rate_limiter = TelegramRateLimiter()
        self.processing = False
        self._batch_buffer: List[Dict[str, Any]] = []
        self._batch_timer: Optional[asyncio.Task] = None
        self.batch_interval = 2.0  # seconds
        self.batch_max_size = 5  # max messages per batch
    
    async def start(self):
        """Start the queue processor."""
        if not self.processing:
            self.processing = True
            asyncio.create_task(self._process_queue())
            logger.info("📨 Telegram queue processor started")
    
    async def stop(self):
        """Stop the queue processor and flush remaining messages."""
        self.processing = False
        # Flush batch buffer
        if self._batch_buffer:
            await self._send_batch()
        logger.info("📨 Telegram queue processor stopped")
    
    async def enqueue(self, message: str, chat_id: str, token: str,
                     msg_type: str = 'info', photo_path: Optional[str] = None,
                     priority: int = 5) -> None:
        """
        Add message to queue.
        
        Args:
            message: Message text
            chat_id: Telegram chat ID
            token: Bot token
            msg_type: Message type (info, warning, critical)
            photo_path: Optional photo attachment
            priority: 1-10 (1 = highest, 10 = lowest)
        """
        await self.queue.put({
            'message': message,
            'chat_id': chat_id,
            'token': token,
            'msg_type': msg_type,
            'photo_path': photo_path,
            'priority': priority,
            'timestamp': time.time()
        })
    
    async def enqueue_batch(self, messages: List[Dict[str, Any]]) -> None:
        """Enqueue multiple messages at once."""
        for msg in messages:
            await self.queue.put(msg)
    
    async def _process_queue(self):
        """Main queue processor loop."""
        while self.processing:
            try:
                # Get message with timeout to allow checking processing flag
                msg = await asyncio.wait_for(self.queue.get(), timeout=1.0)
                
                # Add to batch buffer
                self._batch_buffer.append(msg)
                
                # Start batch timer if not started
                if self._batch_timer is None or self._batch_timer.done():
                    self._batch_timer = asyncio.create_task(self._batch_timeout())
                
                # Send immediately if batch is full
                if len(self._batch_buffer) >= self.batch_max_size:
                    await self._send_batch()
                    if self._batch_timer:
                        self._batch_timer.cancel()
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Telegram queue error: {e}")
    
    async def _batch_timeout(self):
        """Timer untuk force send batch setelah interval tertentu."""
        await asyncio.sleep(self.batch_interval)
        if self._batch_buffer:
            await self._send_batch()
    
    async def _send_batch(self):
        """Send batched messages with rate limiting."""
        if not self._batch_buffer:
            return
        
        # Sort by priority (lower number = higher priority)
        self._batch_buffer.sort(key=lambda x: x.get('priority', 5))
        
        # Group by chat_id for efficient sending
        by_chat: Dict[str, List[Dict]] = {}
        for msg in self._batch_buffer:
            chat_id = msg['chat_id']
            if chat_id not in by_chat:
                by_chat[chat_id] = []
            by_chat[chat_id].append(msg)
        
        # Send messages with rate limiting
        for chat_id, messages in by_chat.items():
            for msg in messages:
                # Wait for rate limit
                while not await self.rate_limiter.acquire(chat_id):
                    wait_time = await self.rate_limiter.get_wait_time(chat_id)
                    logger.debug(f"Rate limit hit, waiting {wait_time:.2f}s")
                    await asyncio.sleep(wait_time + 0.1)
                
                # Actually send the message
                await self._send_single_message(msg)
        
        # Clear buffer
        self._batch_buffer = []
    
    async def _send_single_message(self, msg: Dict[str, Any]):
        """Send single message via Telegram API."""
        try:
            from integrations.alerts import TelegramNotifier
            
            notifier = TelegramNotifier('trading')
            notifier.token = msg['token']
            notifier.chat_id = msg['chat_id']
            
            success = await notifier.send(
                message=msg['message'],
                msg_type=msg['msg_type'],
                photo_path=msg.get('photo_path')
            )
            
            if not success:
                logger.warning(f"Failed to send Telegram message to {msg['chat_id']}")
                
        except Exception as e:
            logger.error(f"Error sending Telegram message: {e}")


# Global queue instance
_telegram_queue: Optional[TelegramQueue] = None


async def get_telegram_queue() -> TelegramQueue:
    """Get or create global Telegram queue instance."""
    global _telegram_queue
    if _telegram_queue is None:
        _telegram_queue = TelegramQueue()
        await _telegram_queue.start()
    return _telegram_queue


async def send_telegram_queued(
    message: str,
    chat_id: Optional[str] = None,
    token: Optional[str] = None,
    msg_type: str = 'info',
    photo_path: Optional[str] = None,
    priority: int = 5
) -> bool:
    """
    Send Telegram message via rate-limited queue.
    
    Args:
        message: Message text
        chat_id: Telegram chat ID (defaults to env var)
        token: Bot token (defaults to env var)
        msg_type: Message type
        photo_path: Optional photo path
        priority: Message priority (1-10, lower = higher priority)
        
    Returns:
        True if queued successfully
    """
    import os
    
    token = token or os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = chat_id or os.getenv('TELEGRAM_CHAT_ID')
    
    if not token or not chat_id:
        logger.warning("Telegram credentials not configured")
        return False
    
    queue = await get_telegram_queue()
    await queue.enqueue(message, chat_id, token, msg_type, photo_path, priority)
    return True


async def flush_telegram_queue():
    """Force flush all pending Telegram messages."""
    if _telegram_queue:
        await _telegram_queue.stop()

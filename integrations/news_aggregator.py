import requests
import feedparser
import pandas as pd
from typing import List, Dict
from logger import get_logger

logger = get_logger(__name__)

RSS_FEEDS = {
    "CNBC_ID_MARKET": "https://www.cnbcindonesia.com/market/rss",
    "BISNIS_ID_MARKET": "https://www.bisnis.com/rss/indeks/5/market",
    "KONTAN_ID_MARKET": "https://www.kontan.co.id/rss/investasi"
}

def fetch_indonesia_market_news() -> List[Dict]:
    """
    Scrape latest Indonesian financial news from RSS feeds using a browser-like User-Agent.
    """
    all_news = []
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    for name, url in RSS_FEEDS.items():
        try:
            logger.info(f"Fetching news from {name}...")
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                feed = feedparser.parse(response.content)
                for entry in feed.entries[:12]:
                    all_news.append({
                        "source": name,
                        "title": entry.title,
                        "link": entry.link,
                        "published": entry.published if hasattr(entry, 'published') else "N/A"
                    })
            else:
                logger.warning(f"Failed to fetch {name}: Status {response.status_code}")
        except Exception as e:
            logger.error(f"Failed to fetch news from {name}: {e}")
            
    return all_news

def analyze_political_keywords(news_list: List[Dict]) -> Dict:
    """
    Search for political and macro keywords to gauge 'Political Noise' levels.
    """
    # Expanded keywords for better sensitivity to Indo market context
    keywords = [
        "politik", "menteri", "kebijakan", "fiskal", "pemerintah", "ihsg", 
        "suku bunga", "bi rate", "rupiah", "inflasi", "sri mulyani", "prabowo",
        "gibran", "bawaslu", "mk", "pemilu", "demonstrasi", "subsidi", "bbm"
    ]
    
    noise_count = 0
    relevant_headlines = []
    
    for article in news_list:
        title_lower = article['title'].lower()
        # Find how many keywords match this headline
        matches = [kw for kw in keywords if kw in title_lower]
        if matches:
            # More matches per headline = higher noise
            noise_count += len(matches)
            relevant_headlines.append(article['title'])
            
    # Normalize score: more news in general usually means more noise
    # We cap the score at 10.
    total_news = len(news_list)
    if total_news > 0:
        # Heuristic: noise_count / news_density
        raw_score = (noise_count / 3) + (total_news / 15)
        noise_level = min(10, round(raw_score))
    else:
        noise_level = 0
    
    return {
        "political_noise_level": noise_level,
        "status": "HIGH RISK" if noise_level > 7 else "MODERATE" if noise_level > 3 else "STABLE",
        "sample_headlines": relevant_headlines[:5]
    }

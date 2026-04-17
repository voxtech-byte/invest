import streamlit as st

def inject_terminal_theme():
    """Injects high-tier industrial Bloomberg-style CSS and Fonts."""
    st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Roboto+Mono:wght@300;500&display=swap');

/* Base Overrides */
[data-testid="stAppViewContainer"] {
    background-color: #0D1117;
    color: #c9d1d9;
    font-family: 'JetBrains Mono', monospace;
}

[data-testid="stHeader"] {
    background-color: rgba(13, 17, 23, 0.9);
}

/* Typography */
h1, h2, h3, .stMarkdown {
    font-family: 'JetBrains Mono', monospace;
}

/* Custom Bloomberg-style Cards */
.sovereign-card {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 4px;
    padding: 1.2rem;
    margin-bottom: 1rem;
    box-shadow: 0 4px 12px rgba(0,0,0,0.5);
}

.metric-label { 
    font-size: 0.75rem; 
    color: #8b949e; 
    text-transform: uppercase; 
    letter-spacing: 1.5px;
    font-weight: 700;
}

.metric-value { 
    font-size: 1.4rem; 
    font-weight: 700; 
    color: #58a6ff;
}

.glow-green { color: #3FB950; text-shadow: 0 0 10px rgba(63, 185, 80, 0.3); }
.glow-red { color: #F85149; text-shadow: 0 0 10px rgba(248, 81, 73, 0.3); }
.glow-blue { color: #58A6FF; text-shadow: 0 0 10px rgba(88, 166, 255, 0.3); }

/* Ticker Tape Animation */
@keyframes ticker {
    0% { transform: translateX(100%); }
    100% { transform: translateX(-100%); }
}

.ticker-wrap {
    width: 100%;
    overflow: hidden;
    background-color: #010409;
    padding: 10px 0;
    border-top: 1px solid #30363d;
    position: fixed;
    bottom: 0;
    left: 0;
    z-index: 999;
}

.ticker {
    display: inline-block;
    white-space: nowrap;
    padding-right: 100%;
    animation: ticker 90s linear infinite;
}

.ticker-item {
    display: inline-block;
    padding: 0 2rem;
    font-size: 0.85rem;
    color: #8b949e;
}

.ticker-item strong { color: #f0f6fc; }

/* Custom Scrollbar */
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: #0d1117; }
::-webkit-scrollbar-thumb { background: #30363d; border-radius: 10px; }

</style>
""", unsafe_allow_html=True)

def get_icon(name):
    """Returns SVG string for Lucide-style icons."""
    icons = {
        "activity": '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline></svg>',
        "shield": '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path></svg>',
        "zap": '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon></svg>',
        "trending-up": '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"></polyline><polyline points="17 6 23 6 23 12"></polyline></svg>',
        "layers": '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 2 7 12 12 22 7 12 2"></polygon><polyline points="2 17 12 22 22 17"></polyline><polyline points="2 12 12 17 22 12"></polyline></svg>'
    }
    return icons.get(name, "")

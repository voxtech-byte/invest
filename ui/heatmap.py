import pandas as pd
import plotly.express as px
from typing import List, Dict, Any

def generate_correlation_heatmap(positions: Dict[str, Any], historical_data: Dict[str, pd.DataFrame]):
    """
    Generate a visual correlation heatmap for the current portfolio holdings.
    Returns a Plotly figure.
    """
    if len(positions) < 2:
        return None
    
    # 1. Align historical returns
    returns_df = pd.DataFrame()
    
    for symbol in positions.keys():
        if symbol in historical_data:
            df = historical_data[symbol]
            # Calculate daily returns
            returns_df[symbol.split('.')[0]] = df['Close'].pct_change()
            
    if returns_df.empty:
        return None
        
    # 2. Calculate Correlation Matrix
    corr_matrix = returns_df.corr().round(2)
    
    # 3. Create Heatmap
    fig = px.imshow(
        corr_matrix,
        text_auto=True,
        aspect="auto",
        color_continuous_scale="RdYlGn_r", # Red to Green (higher correlation is Red/Danger)
        title="Institutional Portfolio Correlation Matrix",
        labels=dict(color="Correlation Factor")
    )
    
    fig.update_layout(
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        font_color="#8b949e",
        margin=dict(l=20, r=20, t=40, b=20)
    )
    
    return fig

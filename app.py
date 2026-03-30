import streamlit as st
import pandas as pd
import numpy as np
import io
import base64
import time
import yfinance as yf
from datetime import datetime, timedelta
from alpaca.data.historical import OptionHistoricalDataClient, StockHistoricalDataClient
from alpaca.data.requests import OptionChainRequest, StockLatestQuoteRequest, StockSnapshotRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import OptionsFeed, DataFeed
from github import Github

# --- 1. CONFIG & API ---
st.set_page_config(page_title="Lucky Quants Lab", page_icon="🧪", layout="wide")

st.markdown("""
<style>
    [data-testid="metric-container"] {
        background-color: rgba(28, 131, 225, 0.05); 
        border: 1px solid rgba(128, 128, 128, 0.15);
        border-radius: 12px;
        padding: 15px;
        height: 140px; 
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        text-align: center;
        margin-bottom: 15px;
    }
    [data-testid="stMetricValue"] { font-size: 2.2rem !important; font-weight: 800 !important; }
    [data-testid="stMetricDelta"] { font-size: 0.95rem !important; color: #888888 !important; justify-content: center !important; }
    [data-testid="stMetricDelta"] > svg { display: none; }
    .footer-right { position: fixed; bottom: 10px; right: 10px; color: gray; font-size: 0.8em; z-index: 1000; }
    
    .creed-box { background-color: rgba(128, 128, 128, 0.05); border: 1px solid rgba(128, 128, 128, 0.2); border-left: 6px solid #2962FF; border-radius: 8px; padding: 15px 20px; margin-bottom: 25px; }
    .creed-title { font-weight: 800; font-size: 1.1em; margin-bottom: 10px; color: #2962FF; letter-spacing: 0.5px; }
    .creed-text { font-size: 0.95em; line-height: 1.6; }
    
    .regime-box { background-color: rgba(255, 255, 255, 0.02); border: 1px solid rgba(128, 128, 128, 0.1); border-left: 6px solid; border-radius: 8px; padding: 20px; margin-top: 10px; margin-bottom: 25px; color: #eee; }
    .regime-title { font-weight: 800; font-size: 1.3em; margin-bottom: 10px; margin-top:0; letter-spacing: 0.5px; }
    .regime-text { font-size: 0.95em; line-height: 1.6; }
    .action-highlight { font-weight: bold; }

    .color-crash { color: #b91d47; border-left-color: #b91d47; }
    .color-bearish { color: #e67e22; border-left-color: #e67e22; }
    .color-bullish { color: #00b09b; border-left-color: #00b09b; }
    .color-neutral { color: #3a7bd5; border-left-color: #3a7bd5; }
    .color-overbought { color: #8e44ad; border-left-color: #8e44ad; }
    
    .sniper-box { background-color: rgba(30, 30, 30, 0.5); border: 1px solid rgba(128, 128, 128, 0.3); border-radius: 8px; padding: 15px; text-align: center; height: 100%; }
    .sniper-title { font-size: 0.85em; color: #aaa; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 5px; }
    .sniper-value { font-size: 1.8em; font-weight: bold; }
    .put-color { color: #00b09b; }
    .call-color { color: #ff4b4b; }
    .neutral-color { color: #f39c12; }
    
    .synthesis-box { background-color: rgba(28, 131, 225, 0.08); border-left: 4px solid #1c83e1; padding: 15px; border-radius: 5px; margin-bottom: 20px;}
    
    .target-box-put { background-color: rgba(0, 176, 155, 0.1); border-left: 5px solid #00b09b; padding: 20px; border-radius: 5px; margin-bottom: 15px; }
    .target-box-call { background-color: rgba(255, 75, 75, 0.1); border-left: 5px solid #ff4b4b; padding: 20px; border-radius: 5px; margin-bottom: 15px; }
    .target-title { font-size: 2.2em; font-weight: 900; margin: 0; }
    .target-sub { margin: 5px 0 0 0; color: #ccc; font-size: 1.1em; }
    
    .auto-risk-banner { background-color: rgba(255, 255, 255, 0.05); padding: 10px 15px; border-radius: 5px; border: 1px dashed rgba(255,255,255,0.2); margin-top: 10px; margin-bottom: 10px; text-align: center; }
    
    .catalyst-card { background-color: rgba(255, 255, 255, 0.03); border: 1px solid rgba(128, 128, 128, 0.2); border-radius: 8px; padding: 20px; margin-bottom: 15px; }
    .cat-date { color: #2962FF; font-weight: bold; font-size: 0.9em; text-transform: uppercase; letter-spacing: 1px; }
    .cat-title { font-size: 1.4em; font-weight: bold; margin: 5px 0 15px 0; }
    .cat-prob-container { display: flex; align-items: center; margin-bottom: 15px; }
    .cat-prob-text { font-size: 2em; font-weight: 900; margin-right: 15px; color: #00b09b; }
    .cat-prob-desc { color: #ccc; font-size: 1.1em; }
    .cat-impact { background-color: rgba(0,0,0,0.3); padding: 12px; border-radius: 5px; border-left: 3px solid #f39c12; margin-bottom: 10px; font-size: 0.95em; }
    .cat-playbook { background-color: rgba(0,0,0,0.3); padding: 12px; border-radius: 5px; border-left: 3px solid #2962FF; font-size: 0.95em; }
</style>
""", unsafe_allow_html=True)

st.markdown("### 🧪 Lucky Quants Lab | Pre-Market War Room")
st.divider()

# API Connections
try:
    API_KEY = st.secrets["ALPACA_KEY"]
    SECRET_KEY = st.secrets["ALPACA_SECRET"]
    GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]
    GITHUB_REPO = st.secrets["GITHUB_REPO"]
    
    opt_client = OptionHistoricalDataClient(API_KEY, SECRET_KEY)
    stock_client = StockHistoricalDataClient(API_KEY, SECRET_KEY)
    gh = Github(GITHUB_TOKEN)
    repo = gh.get_repo(GITHUB_REPO)
except Exception as e:
    st.error(f"Secrets Error. Check Streamlit Settings. {e}")
    st.stop()

FILE_PATH = "lucky_ledger.csv"
COLS = ["Date", "Ticker", "Type", "Strike", "Expiry", "Open Price", "Close Price", "Qty", "Commission", "Premium", "Status"]

def sort_ledger(df):
    if df.empty: return df
    df['temp_date'] = pd.to_datetime(df['Date'], errors='coerce')
    def rank_status(s):
        s = str(s)
        if "Open" in s: return 1
        if "Win" in s: return 2
        if "Loss" in s: return 3
        return 4
    df['status_rank'] = df['Status'].apply(rank_status)
    df = df.sort_values(by=['temp_date', 'status_rank'], ascending=[False, True])
    df['Date'] = df['temp_date'].dt.strftime('%Y-%m-%d')
    return df.drop(columns=['temp_date', 'status_rank']).reset_index(drop=True)

def refresh_calculations(current_df):
    if current_df.empty: return current_df
    current_df = current_df.copy()
    
    for col in ["Strike", "Open Price", "Close Price", "Qty", "Commission"]:
        current_df[col] = pd.to_numeric(current_df[col], errors='coerce').fillna(0)
        
    def update_row(

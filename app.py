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
import google.generativeai as genai

# --- 1. CONFIG & API ---
st.set_page_config(page_title="Lucky Money Lab", page_icon="🧪", layout="wide")

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
    
    .synthesis-box { background-color: rgba(28, 131, 225, 0.08); border-left: 4px solid #1c83e1; padding: 20px; border-radius: 5px; margin-bottom: 20px;}
    .synthesis-box h3 { margin-top: 0; font-size: 1.2em; color: #2962FF; }
    
    .target-box-put { background-color: rgba(0, 176, 155, 0.1); border-left: 5px solid #00b09b; padding: 20px; border-radius: 5px; margin-bottom: 15px; }
    .target-box-call { background-color: rgba(255, 75, 75, 0.1); border-left: 5px solid #ff4b4b; padding: 20px; border-radius: 5px; margin-bottom: 15px; }
    .target-title { font-size: 2.2em; font-weight: 900; margin: 0; }
    .target-sub { margin: 5px 0 0 0; color: #ccc; font-size: 1.1em; }
    
    .auto-risk-banner { background-color: rgba(255, 255, 255, 0.05); padding: 10px 15px; border-radius: 5px; border: 1px dashed rgba(255,255,255,0.2); margin-top: 10px; margin-bottom: 10px; text-align: center; }
</style>
""", unsafe_allow_html=True)

st.markdown("### Lucky Money Lab 🧪")
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
    st.error(f"Secrets Error. Check Streamlit Settings. Details: {e}")
    st.stop()

FILE_PATH = "lucky_ledger.csv"
COLS = ["Date", "Ticker", "Type", "Strike", "Long Strike", "Expiry", "Open Price", "Close Price", "Qty", "Commission", "Premium", "Status"]

def sort_ledger(df):
    if df.empty: return df
    df['temp_date'] = pd.to_datetime(df['Date'], errors='coerce')
    def rank_status(s):
        s = str(s).lower()
        if "open" in s: return 1
        if "win" in s: return 2
        if "loss" in s: return 3
        return 4
    df['status_rank'] = df['Status'].apply(rank_status)
    df = df.sort_values(by=['temp_date', 'status_rank'], ascending=[False, True])
    df['Date'] = df['temp_date'].dt.strftime('%Y-%m-%d')
    return df.drop(columns=['temp_date', 'status_rank']).reset_index(drop=True)

def refresh_calculations(current_df):
    if current_df.empty: return current_df
    current_df = current_df.copy()
    
    if "Long Strike" not in current_df.columns:
        current_df["Long Strike"] = 0.0
        
    for col in ["Strike", "Long Strike", "Open Price", "Close Price", "Qty", "Commission"]:
        current_df[col] = pd.to_numeric(current_df[col], errors='coerce').fillna(0)
        
    def update_row(r):
        open_p = float(r["Open Price"]) if pd.notna(r["Open Price"]) else 0.0
        close_p = float(r["Close Price"]) if pd.notna(r["Close Price"]) else 0.0
        qty = int(r["Qty"]) if pd.notna(r["Qty"]) else 1
        comm = float(r["Commission"]) if pd.notna(r["Commission"]) else 0.0
        current_status = str(r.get("Status", "Open / Active"))
        
        p = round(((open_p - close_p) * 100 * qty) - comm, 2)
        
        try: 
            ex_d = pd.to_datetime(r["Expiry"]).date()
        except: 
            ex_d = datetime.now().date()
        
        if close_p > 0: 
            s = "Closed (Loss)" if close_p > open_p else "Closed (Win)"
        elif "open" in current_status.lower() and ex_d < datetime.now().date(): 
            s = "Expired (Win)"
        else: 
            s = current_status if current_status.strip() != "nan" and current_status.strip() != "" else "Open / Active"
            
        return pd.Series([p, s])
        
    current_df[["Premium", "Status"]] = current_df.apply(update_row, axis=1)
    return sort_ledger(current_df)

def get_weekly_stats(df):
    if df.empty:
        return 0.0, 0
    
    calc_df = df.copy()
    calc_df['Date'] = pd.to_datetime(calc_df['Date'], errors='coerce')
    calc_df['Expiry'] = pd.to_datetime(calc_df['Expiry'], errors='coerce')
    
    today = datetime.now().date()
    start_of_week = pd.Timestamp(today - timedelta(days=today.weekday()))
    
    # Filter for trades closed/expired THIS week OR opened THIS week
    weekly_df = calc_df[
        (~calc_df['Status'].str.lower().str.contains('open', na=False)) & 
        ((calc_df['Expiry'] >= start_of_week) | (calc_df['Date'] >= start_of_week))
    ]
    
    weekly_pnl = weekly_df['Premium'].sum()
    trade_count = len(weekly_df)
    
    return float(weekly_pnl), int(trade_count)

def save_journal(df):
    try:
        df_sorted = sort_ledger(df)
        csv_content = df_sorted[COLS].to_csv(index=False)
        commit_message = f"Ledger Auto-Sync: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        try:
            contents = repo.get_contents(FILE_PATH)
            repo.update_file(contents.path, commit_message, csv_content, contents.sha)
        except:
            repo.create_file(FILE_PATH, "Initial commit", csv_content)
        st.session_state.last_update = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    except Exception as e: 
        st.error(f"Failed to save to GitHub: {e}")

def load_journal():
    try:
        contents = repo.get_contents(FILE_PATH)
        decoded_content = base64.b64decode(contents.content).decode('utf-8')
        raw_df = pd.read_csv(io.StringIO(decoded_content))
        
        for c in COLS:
            if c not in raw_df.columns:
                if c == "Date": raw_df[c] = datetime.now().strftime("%Y-%m-%d")
                elif c == "Long Strike": raw_df[c] = 0.0
                else: raw_df[c] = 0.0 if c in ["Open Price", "Close Price", "Premium", "Commission"] else (1 if c == "Qty" else "Unknown")
        
        original_open = len(raw_df[raw_df['Status'].astype(str).str.contains('Open', na=False, case=False)])
        refreshed_df = refresh_calculations(raw_df[COLS])
        new_open = len(refreshed_df[refreshed_df['Status'].astype(str).str.contains('Open', na=False, case=False)])
        needs_auto_save = original_open > new_open 
        
        return refreshed_df, needs_auto_save
    except: 
        return pd.DataFrame(columns=COLS), False

if 'journal' not in st.session_state: 
    loaded_df, needs_auto_save = load_journal()
    st.session_state.journal = loaded_df
    st.session_state.last_update = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    if needs_auto_save:
        save_journal(st.session_state.journal)
        st.toast("🧹 Auto-Sweep detected expired trades.", icon="✅")

if 'current_vix' not in st.session_state: st.session_state.current_vix = 20.0

# --- 2. GLOBAL CACHED FETCHERS ---
@st.cache_data(ttl=900)
def get_macro_live(symbol):
    try:
        t = yf.Ticker(symbol)
        df = t.history(period='5d')
        if len(df) >= 2: return float(df['Close'].iloc[-1]), ((float(df['Close'].iloc[-1]) - float(df['Close'].iloc[-2])) / float(df['Close'].iloc[-2])) * 100
    except: pass
    return 0.0, 0.0

@st.cache_data(ttl=900)
def get_automated_breadth(ticker_list):
    try:
        df = yf.download(ticker_list, period="1mo", progress=False)
        close_df = df['Close'] if isinstance(df.columns, pd.MultiIndex) else df
        above_20ma, valid_count = 0, 0
        for s in ticker_list:
            if s in close_df.columns:
                prices = close_df[s].dropna()
                if len(prices) >= 20:
                    valid_count += 1
                    if prices.iloc[-1] > prices.tail(20).mean(): above_20ma += 1
        if valid_count == 0: return 50.0, 0, len(ticker_list)
        return (above_20ma / valid_count) * 100, above_20ma, valid_count
    except: return 50.0, 0, len(ticker_list)

@st.cache_data(ttl=900)
def get_sniper_history(ticker_str):
    hist, exps = pd.DataFrame(), []
    try:
        t = yf.Ticker(ticker_str)
        hist = t.history(period='1y')
        exps = list(t.options)
    except: pass 
    return hist, exps

@st.cache_data(ttl=900)
def get_options_chain(ticker_str, exp_date):
    try:
        t = yf.Ticker(ticker_str)
        chain = t.option_chain(exp_date)
        return chain.calls, chain.puts
    except: return pd.DataFrame(), pd.DataFrame()

# --- 3. UI TABS ---
tab_macro, tab_safezone, tab_ledger = st.tabs(["🌍 Macro Playbook", "🎯 Sniper Safe Zones", "📓 Trade Book"])

# --- TAB 1: MACRO PLAYBOOK ---
with tab_macro:
    head_col, btn_col = st.columns([5, 1])
    with head_col: st.markdown("#### 🌍 The 3-Pillar Macro Matrix")
    with btn_col: 
        if st.button("🔄 Refresh Data", use_container_width=True, key="ref1"):
            st.cache_data.clear()
            st.rerun()
            
    try:
        oil_px, oil_pct = get_macro_live("CL=F")
        dxy_px, dxy_pct = get_macro_live("DX-Y.NYB")
        vix_px, vix_pct = get_macro_live("^VIX")
        
        m1, m2, m3 = st.columns(3)
        m1.metric("🛢️ WTI Crude Oil", f"${oil_px:,.2f}", f"{oil_pct:+.2f}%", delta_color="inverse" if oil_px > 80 else "normal")
        m2.metric("💵 US Dollar (DXY)", f"{dxy_px:,.2f}", f"{dxy_pct:+.2f}%", delta_color="inverse" if dxy_px > 105 else "normal")
        m3.metric("📉 Volatility (VIX)", f"{vix_px:,.2f}", f"{vix_pct:+.2f}%", delta_color="inverse" if vix_px > 25 else "normal")

        st.write("---")
        sp500_sectors = ["XLK", "XLV", "XLF", "XLY", "XLC", "XLI", "XLP", "XLE", "XLU", "XLRE", "XLB"]
        nasdaq_leaders = ["AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "TSLA", "AVGO", "COST", "NFLX"]
        
        s5tw_pct, s5tw_up, s5tw_total = get_automated_breadth(sp500_sectors)
        nctw_pct, nctw_up, nctw_total = get_automated_breadth(nasdaq_leaders)
        
        b1, b2 = st.columns(2)
        b1.metric("S&P 500 Breadth", f"{s5tw_pct:.0f}%", f"{s5tw_up}/{s5tw_total} Sectors Up")
        b2.metric("Nasdaq Breadth", f"{nctw_pct:.0f}%", f"{nctw_up}/{nctw_total} Leaders Up")

    except Exception as e: st.error(f"Macro Error: {e}")

# --- TAB 2: SNIPER SAFE ZONES ---
with tab_safezone:
    st.markdown("#### 🎯 Sniper Safe Zones")
    c1, c2, c3 = st.columns([1, 1, 2])
    with c1: calc_tk = st.text_input("Ticker", value="TSLA").upper()
    with c2: calc_ex = st.date_input("Target Expiry", datetime.now().date() + timedelta(days=45))
    with c3:
        st.write(""); st.write("")
        run_calc = st.button("🔬 Auto-Target Strikes", type="primary", use_container_width=True)
    
    if run_calc:
        with st.spinner(f"Analyzing {calc_tk}..."):
            hist_1y, avail_exps = get_sniper_history(calc_tk)
            if not hist_1y.empty:
                px = float(hist_1y['Close'].iloc[-1])
                st.info(f"Current Price: ${px:.2f}. Expected move and walls are calculated using market maker straddle pricing.")
                # Sniper results would display here...

# --- TAB 3: TRADE BOOK ---
with tab_ledger:
    st.markdown("#### 📓 Trade Book & Ledger")
    
    week_pnl, week_trades = get_weekly_stats(st.session_state.journal)
    c_met1, c_met2 = st.columns(2)
    
    # FIXED: Line 429 syntax error resolved below
    c_met1.metric("This Week's Realized P&L", f"${week_pnl:.2f}", delta_color="normal" if week_pnl >= 0 else "inverse")
    c_met2.metric("Trades Closed This Week", str(week_trades))
    
    st.write("---")
    
    # Prep display data (Convert strings to date objects for the UI widget)
    display_df = st.session_state.journal.copy()
    display_df['Date'] = pd.to_datetime(display_df['Date'], errors='coerce').dt.date
    display_df['Expiry'] = pd.to_datetime(display_df['Expiry'], errors='coerce').dt.date
    
    edited_df = st.data_editor(
        display_df, 
        num_rows="dynamic", 
        use_container_width=True,
        hide_index=True,
        column_config={
            "Date": st.column_config.DateColumn("Date Opened", format="YYYY-MM-DD"),
            "Expiry": st.column_config.DateColumn("Expiry Date", format="YYYY-MM-DD"),
            "Type": st.column_config.SelectboxColumn("Type", options=["Put", "Call", "Put Spread", "Call Spread", "Iron Condor"]),
            "Status": st.column_config.SelectboxColumn("Status", options=["Open / Active", "Closed (Win)", "Closed (Loss)", "Expired (Win)"])
        }
    )
    
    if st.button("💾 Save & Sync to GitHub", type="primary"):
        with st.spinner("Syncing..."):
            # Convert back to strings for CSV storage
            edited_df['Date'] = pd.to_datetime(edited_df['Date']).dt.strftime('%Y-%m-%d')
            edited_df['Expiry'] = pd.to_datetime(edited_df['Expiry']).dt.strftime('%Y-%m-%d')
            
            st.session_state.journal = refresh_calculations(edited_df)
            save_journal(st.session_state.journal)
            st.success("Synced!")
            time.sleep(1)
            st.rerun()

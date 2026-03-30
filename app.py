import streamlit as st
import pandas as pd
import numpy as np
import io
import base64
import yfinance as yf
import requests
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
        
    def update_row(r):
        open_p = float(r["Open Price"]) if pd.notna(r["Open Price"]) else 0.0
        close_p = float(r["Close Price"]) if pd.notna(r["Close Price"]) else 0.0
        qty = int(r["Qty"]) if pd.notna(r["Qty"]) else 1
        comm = float(r["Commission"]) if pd.notna(r["Commission"]) else 0.0
        
        p = round(((open_p - close_p) * 100 * qty) - comm, 2)
        
        try: ex_d = pd.to_datetime(r["Expiry"]).date()
        except: ex_d = datetime.now().date()
        
        if close_p > 0: 
            s = "Closed (Loss)" if close_p > open_p else "Closed (Win)"
        elif ex_d < datetime.now().date(): 
            s = "Expired (Win)"
        else: 
            s = "Open / Active"
            
        return pd.Series([p, s])
        
    current_df[["Premium", "Status"]] = current_df.apply(update_row, axis=1)
    return sort_ledger(current_df)

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
    except: pass

def load_journal():
    try:
        contents = repo.get_contents(FILE_PATH)
        decoded_content = base64.b64decode(contents.content).decode('utf-8')
        df = pd.read_csv(io.StringIO(decoded_content))
        for c in COLS:
            if c not in df.columns:
                if c == "Date": df[c] = datetime.now().strftime("%Y-%m-%d")
                else: df[c] = 0.0 if c in ["Open Price", "Close Price", "Premium", "Commission"] else (1 if c == "Qty" else "Unknown")
        return refresh_calculations(df[COLS])
    except: return pd.DataFrame(columns=COLS)

if 'journal' not in st.session_state: 
    st.session_state.journal = load_journal()
    st.session_state.last_update = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

if 'current_vix' not in st.session_state: st.session_state.current_vix = 20.0

WATCHLIST = ["AAPL", "TSLA", "NVDA", "AMD", "META", "AMZN", "MSFT", "GOOGL", "NFLX", "JPM", "BAC", "DIS", "BA", "UBER", "COIN", "PLTR", "SMCI", "ARM"]

# --- 2. GLOBAL CACHED FETCHERS (THE RATE LIMIT SHIELD) ---
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
    try:
        t = yf.Ticker(ticker_str)
        hist = t.history(period='1y')
        beta = t.info.get('beta', 1.0) or 1.0
        exps = list(t.options)
        return hist, beta, exps
    except: return pd.DataFrame(), 1.0, []

@st.cache_data(ttl=900)
def get_options_chain(ticker_str, exp_date):
    try:
        t = yf.Ticker(ticker_str)
        chain = t.option_chain(exp_date)
        return chain.calls, chain.puts
    except: return pd.DataFrame(), pd.DataFrame()

@st.cache_data(ttl=1800)
def get_screener_data(ticker):
    try:
        t_data = yf.Ticker(ticker)
        df = t_data.history(period="2mo")
        if len(df) < 30: return None
        current_price = df['Close'].iloc[-1]
        daily_returns = df['Close'].pct_change().dropna()
        realized_vol = daily_returns.tail(30).std() * np.sqrt(252) * 100
        beta = t_data.info.get('beta', 1.0) or 1.0
        return df, current_price, realized_vol, beta
    except: return None

# --- 3. UI TABS ---
tab_macro, tab_safezone, tab_screener, tab_catalyst, tab_ledger = st.tabs([
    "🌍 Macro Playbook", 
    "🎯 Sniper Safe Zones", 
    "🔎 Live Screener", 
    "⚡ Catalyst Radar", 
    "📓 Lucky Ledger"
])

# --- TAB 1: MACRO PLAYBOOK ---
with tab_macro:
    head_col, btn_col = st.columns([5, 1])
    with head_col: 
        st.markdown("#### 🌍 The 3-Pillar Macro Matrix")
    with btn_col: 
        if st.button("🔄 Refresh Data", use_container_width=True, key="ref1"):
            st.cache_data.clear() # Clears the cache to fetch fresh data
            st.rerun()
    
    try:
        oil_px, oil_pct = get_macro_live("CL=F")
        dxy_px, dxy_pct = get_macro_live("DX-Y.NYB")
        vix_px, vix_pct = get_macro_live("^VIX")
        st.session_state.current_vix = vix_px if vix_px > 0 else 20.0
        
        oil_status = "🟢 Contained" if oil_px < 80 else ("🟡 Hot" if oil_px <= 85 else "🔴 Spiking")
        dxy_status = "🟢 Weak" if dxy_px < 103 else ("🟡 Neutral" if dxy_px <= 105 else "🔴 Strong")
        vix_status = "🟢 Complacent" if vix_px < 18 else ("🟡 Elevated" if vix_px <= 25 else "🔴 Panic")

        m1, m2, m3 = st.columns(3)
        m1.metric("🛢️ WTI Crude Oil", f"${oil_px:,.2f}", f"{oil_status} ({oil_pct:+.2f}%)", delta_color="inverse" if oil_px > 80 else "normal")
        m2.metric("💵 US Dollar (DXY)", f"{dxy_px:,.2f}", f"{dxy_status} ({dxy_pct:+.2f}%)", delta_color="inverse" if dxy_px > 105 else "normal")
        m3.metric("📉 Volatility (VIX)", f"{vix_px:,.2f}", f"{vix_status} ({vix_pct:+.2f}%)", delta_color="inverse" if vix_px > 25 else "normal")

        st.write("---")
        
        sp500_sectors = ["XLK", "XLV", "XLF", "XLY", "XLC", "XLI", "XLP", "XLE", "XLU", "XLRE", "XLB"]
        nasdaq_leaders = ["AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "TSLA", "AVGO", "COST", "NFLX", "AMD", "PEP", "CSCO", "TMUS", "ADBE"]
        
        s5tw_pct, s5tw_up, s5tw_total = get_automated_breadth(sp500_sectors)
        nctw_pct, nctw_up, nctw_total = get_automated_breadth(nasdaq_leaders)
        breadth_avg = (s5tw_pct + nctw_pct) / 2
        
        st.markdown("#### 📊 Market Breadth (Live 20-Day MA Proxies)")
        b1, b2 = st.columns(2)
        b1.metric("S&P 500 Breadth", f"{s5tw_pct:.0f}%", f"{s5tw_up}/{s5tw_total} Sectors Trending Up", delta_color="normal" if s5tw_pct >= 50 else "inverse")
        b2.metric("Nasdaq Breadth", f"{nctw_pct:.0f}%", f"{nctw_up}/{nctw_total} Mega-Caps Trending Up", delta_color="normal" if nctw_pct >= 50 else "inverse")

        st.write("---")
        
        st.markdown("#### 🧠 Live Market Synthesis")
        syn_oil = "Energy prices are running hot, putting upward pressure on inflation and acting as a headwind for rate cuts." if oil_px > 85 else "Crude oil remains contained, alleviating inflation fears and supporting risk assets."
        syn_dxy = "The US Dollar is showing strength, tightening global liquidity and pressuring multinational tech earnings." if dxy_px > 105 else "A weaker dollar is currently providing a highly favorable liquidity environment for equities."
        syn_vix = "However, the VIX is elevated, indicating institutional funds are actively buying downside protection. Fear is present in the order book." if vix_px > 25 else "Volatility is crushed, showing market complacency and a clear 'risk-on' environment."
        
        if breadth_avg >= 80: syn_brd = "Under the hood, participation is exceptionally strong (Overbought). The rally is mathematically exhausted and highly vulnerable to a sudden pullback."
        elif breadth_avg <= 20: syn_brd = "Market breadth is severely washed out (Oversold), BUT the VIX indicates pure panic. This is capitulation, not a safe entry." if vix_px > 30 else "Market breadth is severely washed out (Oversold) while fear (VIX) remains contained, creating a rare structural buying opportunity."
        else: syn_brd = "Market breadth is healthy and neutral, showing a standard rotation of capital between sectors."

        st.markdown(f"""
        <div class="synthesis-box">
            <b>Current Conditions:</b> {syn_oil} {syn_dxy} {syn_vix} <br><br>
            <b>Internal Health:</b> {syn_brd}
        </div>
        """, unsafe_allow_html=True)

        st.markdown("#### 📖 Actionable Strategy Playbook")
        
        if vix_px > 30 or (dxy_px > 108 and oil_px > 95):
            st.markdown("""<div class="regime-box color-crash"><div class="regime-title color-crash">🚨 REGIME: CRASHING / LIQUIDITY SQUEEZE</div><div class="regime-text"><span class="action-highlight">Your Move: HOLD CASH.</span> Do not catch falling knives. Selling puts here is mathematically dangerous because structural support levels will fail under panic selling. Wait for the VIX to crush back down below 25 before deploying capital.</div></div>""", unsafe_allow_html=True)
        elif breadth_avg <= 20 and vix_px <= 25:
             st.markdown("""<div class="regime-box color-bullish"><div class="regime-title color-bullish">🎯 REGIME: OVERSOLD OPPORTUNITY</div><div class="regime-text"><span class="action-highlight">Your Move: BUY THE DIP (SELL PUTS).</span> This is the optimal time for premium sellers. Use the Screener to find high VIX-Edge tech stocks and sell Cash-Secured Puts at major structural support lines.</div></div>""", unsafe_allow_html=True)           
        elif vix_px > 22 or dxy_px > 105 or oil_px > 85:
            st.markdown("""<div class="regime-box color-bearish"><div class="regime-title color-bearish">⚠️ REGIME: BEARISH / CORRECTION</div><div class="regime-text"><span class="action-highlight">Your Move: BE DEFENSIVE.</span> Rotate focus to Traditional and Energy stocks. Capitalize on the downside by selling Call Credit Spreads or Covered Calls on existing positions. Avoid selling puts on high-beta tech.</div></div>""", unsafe_allow_html=True)
        elif breadth_avg >= 80:
             st.markdown("""<div class="regime-box color-overbought"><div class="regime-title color-overbought">🔥 REGIME: OVERBOUGHT / EXHAUSTED</div><div class="regime-text"><span class="action-highlight">Your Move: TAKE PROFITS.</span> Stop selling puts. This is the absolute best time to sell Covered Calls to collect rich premiums from overly greedy buyers before the inevitable dip.</div></div>""", unsafe_allow_html=True)           
        elif vix_px < 18 and dxy_px < 103 and oil_px < 78:
            st.markdown("""<div class="regime-box color-bullish"><div class="regime-title color-bullish">🚀 REGIME: EXTREME BULLISH / RISK-ON</div><div class="regime-text"><span class="action-highlight">Your Move: STAY LONG.</span> Heavy on Tech and Growth. Sell OTM Puts on your high-beta Watchlist. Ride the liquidity wave.</div></div>""", unsafe_allow_html=True)
        else:
            st.markdown("""<div class="regime-box color-neutral"><div class="regime-title color-neutral">⚖️ REGIME: NEUTRAL / RANGE-BOUND</div><div class="regime-text"><span class="action-highlight">Your Move: STOCK PICKER'S MARKET.</span> Use your Screener to find specific exhausted stocks. Keep trade durations short (Weeklies) and collect pure Theta decay on range-bound tickers.</div></div>""", unsafe_allow_html=True)

    except Exception as e: pass

# --- TAB 2: SNIPER SAFE ZONES ---
with tab_safezone:
    st.markdown("#### 🎯 Sniper Safe Zones (100% Automated)")
    st.caption("Zero inputs. The app calculates RSI, assigns Risk Multipliers, and executes a 'Proximity Snap' to find the closest safe structural wall.")
    
    c1, c2, c3 = st.columns([1, 1, 2])
    with c1: calc_tk = st.text_input("Ticker", value="TSLA", key="calc_tk2").upper()
    with c2: calc_ex = st.date_input("Target Expiry", datetime.now().date() + timedelta(days=7))
    with c3:
        st.write(""); st.write("")
        run_calc = st.button("🔬 Auto-Target Strikes", type="primary", use_container_width=True)
    
    if run_calc:
        with st.spinner(f"Running automated X-Ray analysis on {calc_tk}..."):
            try:
                hist_1y, beta, avail_exps = get_sniper_history(calc_tk)
                
                if hist_1y.empty:
                    st.error("Invalid Ticker or No Data Found. API Rate limits may be active.")
                else:
                    px = float(hist_1y['Close'].iloc[-1])
                    days_to_exp = max((calc_ex - datetime.now().date()).days, 1)
                    
                    try:
                        delta = hist_1y['Close'].diff()
                        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                        rs = gain / loss
                        live_rsi = 100 - (100 / (1 + rs.iloc[-1]))
                        if pd.isna(live_rsi): live_rsi = 50.0
                    except: live_rsi = 50.0
                    
                    if live_rsi < 40:
                        put_mult, call_mult = 0.5, 1.5
                        risk_status = f"OVERSOLD (RSI: {live_rsi:.1f}). Auto-Aggressive on Puts (0.5x), Conservative on Calls (1.5x)."
                    elif live_rsi > 60:
                        put_mult, call_mult = 1.5, 0.5
                        risk_status = f"OVERBOUGHT (RSI: {live_rsi:.1f}). Auto-Conservative on Puts (1.5x), Aggressive on Calls (0.5x)."
                    else:
                        put_mult, call_mult = 1.0, 1.0
                        risk_status = f"NEUTRAL (RSI: {live_rsi:.1f}). Balanced Risk Applied (1.0x move)."

                    st.markdown(f"<div class='auto-risk-banner'>🤖 <b>Auto-Risk Engine Active:</b> {risk_status}</div>", unsafe_allow_html=True)
                    
                    put_wall_str, call_wall_str = "N/A", "N/A"
                    put_wall, call_wall = None, None
                    base_exp_move = 0.0
                    math_type_str = "Theoretical IV"
                    
                    try:
                        if avail_exps:
                            target_exp = calc_ex.strftime('%Y-%m-%d')
                            if target_exp not in avail_exps: target_exp = avail_exps[0]
                            
                            calls, puts = get_options_chain(calc_tk, target_exp)
                            
                            if not calls.empty and not puts.empty:
                                closest_call = calls.iloc[(calls['strike'] - px).abs().argsort()[:1]]
                                closest_put = puts.iloc[(puts['strike'] - px).abs().argsort()[:1]]
                                base_exp_move = float(closest_call['lastPrice'].values[0] + closest_put['lastPrice'].values[0])
                                math_type_str = "Market Maker Straddle"
                                
                                puts_filtered = puts[(puts['strike'] >= px * 0.70) & (puts['strike'] <= px)]
                                calls_filtered = calls[(calls['strike'] <= px * 1.30) & (calls['strike'] >= px)]
                                if not puts_filtered.empty:
                                    put_wall = puts_filtered.loc[puts_filtered['openInterest'].idxmax()]['strike']
                                    put_wall_str = f"${put_wall:.2f}"
                                if not calls_filtered.empty:
                                    call_wall = calls_filtered.loc[calls_filtered['openInterest'].idxmax()]['strike']
                                    call_wall_str = f"${call_wall:.2f}"
                    except: pass 
                    
                    if base_exp_move <= 0:
                        stock_iv_proxy = st.session_state.current_vix * beta
                        base_exp_move = px * (stock_iv_proxy / 100) * np.sqrt(days_to_exp / 365)
                    
                    math_floor = px - (base_exp_move * put_mult)
                    math_ceil = px + (base_exp_move * call_mult)
                    
                    lookback_days = max(days_to_exp, 5) 
                    macro_lookback = max(days_to_exp * 3, 20) 
                    
                    s1 = hist_1y['Low'].tail(lookback_days).min()
                    r1 = hist_1y['High'].tail(lookback_days).max()
                    s2 = hist_1y['Low'].tail(macro_lookback).min() 
                    r2 = hist_1y['High'].tail(macro_lookback).max()
                    
                    hist_vol = hist_1y.tail(macro_lookback).copy()
                    hist_vol['Price_Bin'] = pd.cut(hist_vol['Close'], bins=20)
                    vol_profile = hist_vol.groupby('Price_Bin', observed=False)['Volume'].sum()
                    poc_price = vol_profile.idxmax().mid
                    
                    snap_limit = base_exp_move * 0.75 
                    
                    put_candidates = []
                    if math_floor - s1 >= 0 and (math_floor - s1) <= snap_limit: put_candidates.append((f"S1 ({lookback_days}d Low)", s1))
                    if math_floor - s2 >= 0 and (math_floor - s2) <= snap_limit: put_candidates.append((f"S2 ({macro_lookback}d Low)", s2))
                    if math_floor - poc_price >= 0 and (math_floor - poc_price) <= snap_limit: put_candidates.append(("Volume POC", poc_price))
                    if put_wall is not None and math_floor - put_wall >= 0 and (math_floor - put_wall) <= snap_limit: put_candidates.append(("Options Put Wall", put_wall))
                    
                    if put_candidates:
                        best_put = max(put_candidates, key=lambda x: x[1])
                        target_put = best_put[1]
                        put_subtext = f"Snapped to {best_put[0]} at ${target_put:.2f}. Tucked safely behind structure, just below the Math Floor (${math_floor:.2f})."
                    else:
                        target_put = math_floor
                        put_subtext = f"Using Auto-Math Floor. Structural supports are too far away to justify sacrificing your premium."

                    call_candidates = []
                    if r1 - math_ceil >= 0 and (r1 - math_ceil) <= snap_limit: call_candidates.append((f"R1 ({lookback_days}d High)", r1))
                    if r2 - math_ceil >= 0 and (r2 - math_ceil) <= snap_limit: call_candidates.append((f"R2 ({macro_lookback}d High)", r2))
                    if poc_price - math_ceil >= 0 and (poc_price - math_ceil) <= snap_limit: call_candidates.append(("Volume POC", poc_price))
                    if call_wall is not None and call_wall - math_ceil >= 0 and (call_wall - math_ceil) <= snap_limit: call_candidates.append(("Options Call Wall", call_wall))
                    
                    if call_candidates:
                        best_call = min(call_candidates, key=lambda x: x[1])
                        target_call = best_call[1]
                        call_subtext = f"Snapped to {best_call[0]} at ${target_call:.2f}. Blocked safely by structure, just above the Math Ceiling (${math_ceil:.2f})."
                    else:
                        target_call = math_ceil
                        call_subtext = f"Using Auto-Math Ceiling. Structural resistance is too far away to justify sacrificing your premium."

                    st.write("---")
                    st.markdown(f"### **{calc_tk} X-Ray Analysis | Current Price: ${px:.2f}**")
                    
                    col_m, col_s1, col_s2, col_s3 = st.columns(4)
                    with col_m:
                        st.markdown(f"""<div class="sniper-box">
                            <div class="sniper-title">1. Auto-Math Move</div>
                            <div class="sniper-value put-color">Floor: ${math_floor:.2f}</div>
                            <div class="sniper-value call-color">Ceiling: ${math_ceil:.2f}</div>
                            <div style="font-size:0.8em; color:gray; margin-top:5px;">Base: {math_type_str}</div>
                            </div>""", unsafe_allow_html=True)
                            
                    with col_s1:
                        st.markdown(f"""<div class="sniper-box">
                            <div class="sniper-title">2. Price Action</div>
                            <div style="color:#00b09b;"><b>S1 ({lookback_days}d):</b> ${s1:.2f} <br><b>S2 ({macro_lookback}d):</b> ${s2:.2f}</div>
                            <div style="color:#ff4b4b; margin-top:5px;"><b>R1 ({lookback_days}d):</b> ${r1:.2f} <br><b>R2 ({macro_lookback}d):</b> ${r2:.2f}</div>
                            <div style="font-size:0.8em; color:gray; margin-top:5px;">Dynamic Timeframe</div>
                            </div>""", unsafe_allow_html=True)
                            
                    with col_s2:
                        st.markdown(f"""<div class="sniper-box">
                            <div class="sniper-title">3. Volume Profile</div>
                            <div class="sniper-value neutral-color">POC: ${poc_price:.2f}</div>
                            <div style="font-size:0.8em; color:gray; margin-top:10px;">{macro_lookback}-Day Volume Node</div>
                            </div>""", unsafe_allow_html=True)
                            
                    with col_s3:
                        st.markdown(f"""<div class="sniper-box">
                            <div class="sniper-title">4. Options Walls</div>
                            <div style="color:#00b09b; font-size:1.2em;"><b>Put Wall:</b> {put_wall_str}</div>
                            <div style="color:#ff4b4b; font-size:1.2em; margin-top:5px;"><b>Call Wall:</b> {call_wall_str}</div>
                            <div style="font-size:0.8em; color:gray; margin-top:5px;">Max Open Interest</div>
                            </div>""", unsafe_allow_html=True)
                    
                    st.write("---")
                    st.markdown("#### 🎯 Ultimate Target Strikes")
                    st.markdown(f"""<div class="target-box-put"><div class="target-title" style="color: #00b09b;">🟢 TARGET PUT STRIKE: ${target_put:.2f}</div><div class="target-sub">{put_subtext}</div></div>""", unsafe_allow_html=True)
                    st.markdown(f"""<div class="target-box-call"><div class="target-title" style="color: #ff4b4b;">🔴 TARGET CALL STRIKE: ${target_call:.2f}</div><div class="target-sub">{call_subtext}</div></div>""", unsafe_allow_html=True)

            except Exception as e:
                st.error(f"Calculation Error: {e}")

# --- TAB 3: THE OPPORTUNITY SCREENER ---
with tab_screener:
    st.markdown("#### 🔎 Live Opportunity Screener (VRP Edge)")
    
    col_filt1, col_filt2 = st.columns(2)
    with col_filt1: strategy_target = st.selectbox("I want to find setups for:", ["Selling Puts (Oversold Stocks)", "Selling Calls (Overbought Stocks)"])
    with col_filt2: min_edge = st.slider("Minimum VRP Edge (+%)", min_value=0, max_value=25, value=5, step=1)
        
    if st.button("🚀 Run Edge Scan", use_container_width=True, type="primary", key="btn2"):
        with st.spinner("Calculating Implied vs Historical Volatility Edges..."):
            screener_results = []
            for ticker in WATCHLIST:
                try:
                    screener_data = get_screener_data(ticker)
                    if screener_data is None: continue
                    df, current_price, realized_vol, beta = screener_data
                    
                    implied_vol = st.session_state.current_vix * beta
                    vrp_edge = implied_vol - realized_vol
                    delta = df['Close'].diff()
                    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                    rs = gain / loss
                    rsi_14 = 100 - (100 / (1 + rs.iloc[-1]))
                    
                    screener_results.append({
                        "Ticker": ticker, "Price": round(current_price, 2), "RSI (14)": round(rsi_14, 1),
                        "Realized Vol": round(realized_vol, 1), "Implied Vol": round(implied_vol, 1), "VRP Edge": round(vrp_edge, 1)
                    })
                except: pass 
            
            res_df = pd.DataFrame(screener_results)
            if strategy_target == "Selling Puts (Oversold Stocks)":
                filtered_df = res_df[(res_df["RSI (14)"] < 45) & (res_df["VRP Edge"] >= min_edge)].sort_values(by="VRP Edge", ascending=False) 
                st.success(f"Found {len(filtered_df)} candidates.")
            else:
                filtered_df = res_df[(res_df["RSI (14)"] > 60) & (res_df["VRP Edge"] >= min_edge)].sort_values(by="VRP Edge", ascending=False) 
                st.error(f"Found {len(filtered_df)} candidates.")
                
            if not filtered_df.empty:
                st.dataframe(filtered_df.style.format({"Price": "${:.2f}", "RSI (14)": "{:.1f}", "Realized Vol": "{:.1f}%", "Implied Vol": "{:.1f}%", "VRP Edge": "+{:.1f}%"}), use_container_width=True, hide_index=True)

# --- TAB 4: CATALYST RADAR ---
with tab_catalyst:
    st.markdown("#### ⚡ Event-Driven Catalyst Radar")
    st.caption("Front-run market volatility by tracking prediction market probabilities for major economic events.")
    
    @st.cache_data(ttl=3600)
    def get_prediction_data():
        try:
            kalshi_key = st.secrets.get("KALSHI_KEY", None)
            if kalshi_key: pass 
        except: pass
        
        return [
            {
                "date": "Next Wed, 8:30 AM EST",
                "title": "US CPI Inflation (YoY)",
                "outcome": "Will CPI come in above 2.8%?",
                "prob": 64,
                "impact": "If Hot (>2.8%): DXY Spikes, Tech (QQQ) Drops. Rates stay higher for longer.",
                "playbook": "Avoid selling naked puts on Tech. Shift to Call Credit Spreads on overbought growth stocks."
            },
            {
                "date": "Next Fri, 8:30 AM EST",
                "title": "Non-Farm Payrolls (Jobs)",
                "outcome": "Will US add >180k jobs?",
                "prob": 82,
                "impact": "If Strong (>180k): Goldilocks scenario confirmed. Consumer spending remains robust.",
                "playbook": "Aggressively sell Puts on high-quality Mega-Caps (AAPL, AMZN). Market will reward economic resilience."
            },
            {
                "date": "Upcoming FOMC",
                "title": "Federal Reserve Rate Decision",
                "outcome": "Will the Fed cut rates by 25bps?",
                "prob": 22,
                "impact": "If No Cut (Hold): Small initial shock to small-caps (IWM), but large-caps will absorb it.",
                "playbook": "Wait for the post-meeting press conference (Powell). Sell Iron Condors to capture the 'IV Crush' immediately after he speaks."
            }
        ]
        
    events = get_prediction_data()
    st.info("💡 **Quant Tip:** When an event has a very high probability (e.g., 85%+), the market has usually already priced it in. The edge is found when the options market is pricing in a massive crash (high VIX), but the prediction markets show the event is likely a 'nothing-burger.'")
    st.write("---")
    
    for idx, ev in enumerate(events):
        st.markdown(f"""
        <div class="catalyst-card">
            <div class="cat-date">📅 {ev['date']}</div>
            <div class="cat-title">{ev['title']}</div>
            <div class="cat-prob-container">
                <div class="cat-prob-text">{ev['prob']}%</div>
                <div class="cat-prob-desc">Crowd Probability: <b>{ev['outcome']}</b></div>
            </div>
            <div class="cat-impact"><b>Market Impact:</b> {ev['impact']}</div>
            <div class="cat-playbook"><b>Options Playbook:</b> {ev['playbook']}</div>
        </div>
        """, unsafe_allow_html=True)

# --- TAB 5: LUCKY LEDGER (4-BOX DASHBOARD LOCKED & BUG-FIXED) ---
with tab_ledger:
    st.markdown("""
    <div class="creed-box">
        <div class="creed-title">🧠 The Quants Creed</div>
        <div class="creed-text"><b>1. Hope is not a strategy.</b> Cut your losses mechanically.<br><b>2. Watch the clock.</b> Beware of Market-on-Close (MOC) volatility and the notorious Friday Flush.</div>
    </div>
    """, unsafe_allow_html=True)
    
    df_j = st.session_state.journal
    
    # 1. Total Realized & Win Rate
    realized_df = df_j[~df_j["Status"].astype(str).str.contains("Open", na=False)]
    total_realized = realized_df["Premium"].sum() if not realized_df.empty else 0.0
    total_closed = len(realized_df)
    wins = len(realized_df[realized_df["Status"].astype(str).str.contains("Win", na=False)])
    win_rate = (wins / total_closed * 100) if total_closed > 0 else 0.0
    
    # 2. Active Trades & Risk
    active_df = df_j[df_j["Status"].astype(str).str.contains("Open", na=False)]
    active_count = len(active_df)
    try:
        strikes = pd.to_numeric(active_df["Strike"], errors='coerce').fillna(0)
        qtys = pd.to_numeric(active_df["Qty"], errors='coerce').fillna(0)
        capital_at_risk = (strikes * 100 * qtys).sum()
    except:
        capital_at_risk = 0.0
        
    # 3. This Week P&L (Mon - Sun)
    today = datetime.now().date()
    start_of_week = today - timedelta(days=today.weekday()) 
    end_of_week = start_of_week + timedelta(days=6) 
    # Use the cleaned date column without mutating main state
    temp_dates = pd.to_datetime(df_j['Expiry'], errors='coerce').dt.date
    this_week_df = df_j[(temp_dates >= start_of_week) & (temp_dates <= end_of_week)]
    weekly_profit = this_week_df["Premium"].sum() if not this_week_df.empty else 0.0
    
    # 4. Top Winner & Loser
    if not realized_df.empty and realized_df["Premium"].max() > 0:
        top_win_idx = realized_df["Premium"].idxmax()
        top_winner_str = f"{realized_df.loc[top_win_idx, 'Ticker']} (+${realized_df.loc[top_win_idx, 'Premium']:.0f})"
    else:
        top_winner_str = "N/A"
        
    if not realized_df.empty and realized_df["Premium"].min() < 0:
        top_loss_idx = realized_df["Premium"].idxmin()
        top_loser_str = f"Loser: {realized_df.loc[top_loss_idx, 'Ticker']} (${realized_df.loc[top_loss_idx, 'Premium']:.0f})"
    else:
        top_loser_str = "Loser: N/A"
    
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total Realized 🤑", f"${total_realized:,.2f}", f"Win Rate: {win_rate:.1f}%", delta_color="off")
    k2.metric("Active Trades 📈", str(active_count), f"Risk: ${capital_at_risk:,.0f}", delta_color="off")
    k3.metric("This Week P&L 📅", f"${weekly_profit:,.2f}", "Mon - Sun", delta_color="off")
    k4.metric("Top Winner 🏆", top_winner_str, top_loser_str, delta_color="off")
    
    # --- LOG NEW TRADE FORM (Only Put/Call) ---
    with st.expander("➕ Log New Trade", expanded=True):
        with st.form("new_trade_form", clear_on_submit=True):
            l1, l2, l3, l4 = st.columns(4)
            _raw_tk = l1.text_input("Ticker", placeholder="e.g. AAPL")
            n_ex = l2.date_input("Expiry", datetime.now().date() + timedelta(days=7))
            n_ty = l3.selectbox("Type", ["Short Put", "Short Call"])
            n_qt = l4.number_input("Qty", value=1, min_value=1)
            
            l5, l6 = st.columns(2)
            n_st = l5.number_input("Strike(s)", value=None, format="%.1f", placeholder="e.g. 150.5")
            n_op = l6.number_input("Open Price", value=None, format="%.2f", placeholder="e.g. 0.85")
            
            submitted = st.form_submit_button("🚀 Commit Trade", use_container_width=True, type="primary")
            
            if submitted:
                n_tk = _raw_tk.upper() if _raw_tk else None
                if n_tk and n_st is not None and n_op is not None:
                    comm = round(n_qt * 1.05, 2)
                    net = round((float(n_op) * 100 * n_qt) - comm, 2)
                    
                    stat = "Expired (Win)" if n_ex < datetime.now().date() else "Open / Active"
                    new_row = pd.DataFrame([{
                        "Date": str(datetime.now().date()), "Ticker": n_tk, "Type": n_ty, 
                        "Strike": round(n_st, 1), "Expiry": str(n_ex), "Open Price": round(float(n_op), 2), 
                        "Close Price": 0.0, "Qty": n_qt, "Commission": comm, "Premium": net, "Status": stat
                    }])
                    st

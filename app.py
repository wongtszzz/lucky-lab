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
st.set_page_config(page_title="Lucky Money Lab", page_icon="🧪", layout="wide")

# Custom Dark Terminal Stylesheet matching the Prototype
st.markdown("""
<style>
    /* Global changes */
    .reportview-container { background: #0d0e12; }
    
    /* Premium Dashboard Cards */
    .terminal-card {
        background-color: #14161d;
        border: 1px solid #222530;
        border-radius: 10px;
        padding: 20px;
        margin-bottom: 20px;
        height: 100%;
        min-height: 340px;
    }
    .card-title {
        font-size: 0.85rem;
        color: #707584;
        text-transform: uppercase;
        letter-spacing: 1.5px;
        font-weight: 700;
        margin-bottom: 15px;
    }
    .main-metric {
        font-size: 2.4rem;
        font-weight: 800;
        color: #00b09b;
        margin-bottom: 2px;
    }
    .sub-metric-row {
        font-size: 0.82rem;
        font-style: italic;
        color: #a0a5b5;
        margin-bottom: 15px;
        display: flex;
        justify-content: space-between;
    }
    .data-row {
        display: flex;
        justify-content: space-between;
        padding: 8px 0;
        border-bottom: 1px solid #1c1e27;
        font-size: 0.95rem;
    }
    .data-row:last-child { border-bottom: none; }
    .data-label { color: #989da9; }
    .data-value { font-weight: 600; color: #ffffff; }
    .data-value.positive { color: #00b09b; }
    .data-value.neutral { color: #f39c12; }
    
    /* Creed Box Customization */
    .creed-box { 
        background-color: #14161d; 
        border: 1px solid #222530; 
        border-left: 6px solid #0052cc; 
        border-radius: 10px; 
        padding: 20px; 
        height: 100%;
        min-height: 340px;
    }
    .creed-title { font-weight: 800; font-size: 1.1em; margin-bottom: 12px; color: #0052cc; letter-spacing: 0.5px; text-transform: uppercase; }
    .creed-text { font-size: 0.9rem; line-height: 1.6; color: #c0c5d5; }
    
    /* Sniper Styles */
    .sniper-box { background-color: #14161d; border: 1px solid #222530; border-radius: 8px; padding: 15px; text-align: center; height: 100%; }
    .sniper-title { font-size: 0.85em; color: #707584; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 5px; }
    .sniper-value { font-size: 1.8em; font-weight: bold; }
    .put-color { color: #00b09b; }
    .call-color { color: #ff4b4b; }
    .neutral-color { color: #f39c12; }
    
    .target-box-put { background-color: rgba(0, 176, 155, 0.08); border-left: 5px solid #00b09b; padding: 20px; border-radius: 5px; margin-bottom: 15px; }
    .target-box-call { background-color: rgba(255, 75, 75, 0.08); border-left: 5px solid #ff4b4b; padding: 20px; border-radius: 5px; margin-bottom: 15px; }
    .target-title { font-size: 2.2em; font-weight: 900; margin: 0; }
    .target-sub { margin: 5px 0 0 0; color: #989da9; font-size: 1.0em; }
    
    .auto-risk-banner { background-color: #14161d; padding: 10px 15px; border-radius: 5px; border: 1px dashed #222530; margin-top: 10px; margin-bottom: 10px; text-align: center; }
    .footer-right { position: fixed; bottom: 10px; right: 10px; color: gray; font-size: 0.8em; z-index: 1000; }
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
    st.error(f"Secrets Error. Check Streamlit Settings. {e}")
    st.stop()

FILE_PATH = "lucky_ledger.csv"
COLS = ["Date", "Ticker", "Type", "Strike", "Long Strike", "Expiry", "Open Price", "Close Price", "Qty", "Commission", "Premium", "Status"]

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
        
        # Credit Basis Architecture: open trades reflect full premium collected
        p = round(((open_p - close_p) * 100 * qty) - comm, 2)
        
        try: ex_d = pd.to_datetime(r["Expiry"]).date()
        except: ex_d = datetime.now().date()
        
        if close_p > 0: 
            s = "Closed (Loss)" if close_p > open_p else "Closed (Win)"
        elif "Open" in current_status and ex_d < datetime.now().date(): 
            s = "Expired (Win)"
        else: 
            s = current_status if current_status.strip() != "nan" and current_status.strip() != "" else "Open / Active"
            
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
        raw_df = pd.read_csv(io.StringIO(decoded_content))
        
        for c in COLS:
            if c not in raw_df.columns:
                if c == "Date": raw_df[c] = datetime.now().strftime("%Y-%m-%d")
                elif c == "Long Strike": raw_df[c] = 0.0
                else: raw_df[c] = 0.0 if c in ["Open Price", "Close Price", "Premium", "Commission"] else (1 if c == "Qty" else "Unknown")
        
        original_open = len(raw_df[raw_df['Status'].astype(str).str.contains('Open', na=False)])
        refreshed_df = refresh_calculations(raw_df[COLS])
        new_open = len(refreshed_df[refreshed_df['Status'].astype(str).str.contains('Open', na=False)])
        needs_auto_save = original_open > new_open 
        
        return refreshed_df, needs_auto_save
    except: return pd.DataFrame(columns=COLS), False

if 'journal' not in st.session_state: 
    loaded_df, needs_auto_save = load_journal()
    st.session_state.journal = loaded_df
    st.session_state.last_update = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    if needs_auto_save:
        save_journal(st.session_state.journal)
        st.toast("🧹 Auto-Sweep: Passed expiration dates executed on Credit P&L.", icon="✅")

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
    hist = pd.DataFrame()
    exps = []
    try:
        t = yf.Ticker(ticker_str)
        hist = t.history(period='1y')
    except: pass 
    try:
        t = yf.Ticker(ticker_str)
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

@st.cache_data(ttl=3600)
def get_market_rankings_ytd():
    indices = {"Nasdaq": "^IXIC", "Russell 2000": "^RUT", "S&P 500": "^GSPC", "Dow Jones": "^DJI"}
    rankings = {}
    for name, sym in indices.items():
        try:
            t = yf.Ticker(sym)
            df = t.history(start="2026-01-01")
            if not df.empty:
                start_px = df['Close'].iloc[0]
                end_px = df['Close'].iloc[-1]
                rankings[name] = ((end_px - start_px) / start_px) * 100
            else: rankings[name] = 0.0
        except: rankings[name] = 0.0
    return rankings

# --- 3. UI TABS ---
tab_macro, tab_safezone, tab_ledger = st.tabs([
    "🌍 Macro Playbook", 
    "🎯 Sniper Safe Zones", 
    "📓 Trade Book"
])

# --- TAB 1: MACRO PLAYBOOK ---
with tab_macro:
    head_col, btn_col = st.columns([5, 1])
    with head_col: 
        st.markdown("#### 🌍 The 3-Pillar Macro Matrix")
    with btn_col: 
        if st.button("🔄 Refresh Data", use_container_width=True, key="ref1"):
            st.cache_data.clear()
            st.rerun()
            
    st.caption(f"Last API Sync: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
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
        
        st.markdown("#### 📊 Market Breadth (Live 20-Day MA Proxies)")
        b1, b2 = st.columns(2)
        b1.metric("S&P 500 Breadth", f"{s5tw_pct:.0f}%", f"{s5tw_up}/{s5tw_total} Sectors Trending Up", delta_color="normal" if s5tw_pct >= 50 else "inverse")
        b2.metric("Nasdaq Breadth", f"{nctw_pct:.0f}%", f"{nctw_up}/{nctw_total} Mega-Caps Trending Up", delta_color="normal" if nctw_pct >= 50 else "inverse")

    except Exception as e: pass

# --- TAB 2: SNIPER SAFE ZONES ---
with tab_safezone:
    st.markdown("#### 🎯 Sniper Safe Zones")
    
    c_tog1, c_tog2 = st.columns([3, 1])
    with c_tog1:
        st.caption("Enter ticker and expiry to calculate structural support.")
    with c_tog2:
        dynamic_risk = st.checkbox("🛡️ Enable RSI Risk Shield", value=False)
    
    c1, c2, c3 = st.columns([1, 1, 2])
    with c1: calc_tk = st.text_input("Ticker", value="TSLA", key="calc_tk2").upper()
    with c2: calc_ex = st.date_input("Target Expiry", datetime.now().date() + timedelta(days=45))
    with c3:
        st.write(""); st.write("")
        run_calc = st.button("🔬 Auto-Target Strikes", type="primary", use_container_width=True)
    
    if run_calc:
        with st.spinner(f"Running automated X-Ray and fetching Options Matrix for {calc_tk}..."):
            try:
                hist_1y, avail_exps = get_sniper_history(calc_tk)
                
                if hist_1y.empty:
                    st.error(f"Invalid Ticker or No Data Found for {calc_tk}.")
                else:
                    px = float(hist_1y['Close'].iloc[-1])
                    beta = 1.0 
                    days_to_exp = max((calc_ex - datetime.now().date()).days, 1)
                    
                    try:
                        delta = hist_1y['Close'].diff()
                        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                        rs = gain / loss
                        live_rsi = 100 - (100 / (1 + rs.iloc[-1]))
                        if pd.isna(live_rsi): live_rsi = 50.0
                    except: live_rsi = 50.0
                    
                    if dynamic_risk:
                        if live_rsi < 40:
                            put_mult, call_mult = 0.5, 1.5
                            risk_status = f"🛡️ Shield ACTIVE: OVERSOLD (RSI: {live_rsi:.1f}). Put Risk Skew: 0.5x."
                        elif live_rsi > 60:
                            put_mult, call_mult = 1.5, 0.5
                            risk_status = f"🛡️ Shield ACTIVE: OVERBOUGHT (RSI: {live_rsi:.1f}). Put Risk Skew: 1.5x."
                        else:
                            put_mult, call_mult = 1.0, 1.0
                            risk_status = f"🛡️ Shield ACTIVE: NEUTRAL (RSI: {live_rsi:.1f}). Risk Skew: 1.0x."
                    else:
                        put_mult, call_mult = 1.0, 1.0
                        risk_status = f"⚠️ Shield OFF: Rigid 1.0x Multiplier applied."

                    st.markdown(f"<div class='auto-risk-banner'>🤖 <b>Risk Engine:</b> {risk_status}</div>", unsafe_allow_html=True)
                    
                    put_wall_str, call_wall_str = "N/A", "N/A"
                    put_wall, call_wall = None, None
                    base_exp_move = 0.0
                    math_type_str = "Theoretical IV"
                    calls_data, puts_data = pd.DataFrame(), pd.DataFrame()
                    
                    try:
                        if avail_exps:
                            target_exp = calc_ex.strftime('%Y-%m-%d')
                            if target_exp not in avail_exps: target_exp = avail_exps[0]
                            calls_data, puts_data = get_options_chain(calc_tk, target_exp)
                            if not calls_data.empty and not puts_data.empty:
                                closest_call = calls_data.iloc[(calls_data['strike'] - px).abs().argsort()[:1]]
                                closest_put = puts_data.iloc[(puts_data['strike'] - px).abs().argsort()[:1]]
                                base_exp_move = float(closest_call['lastPrice'].values[0] + closest_put['lastPrice'].values[0])
                                math_type_str = "Market Maker Straddle"
                                
                                puts_filtered = puts_data[(puts_data['strike'] >= px * 0.70) & (puts_data['strike'] <= px)]
                                calls_filtered = calls_data[(calls_data['strike'] <= px * 1.30) & (calls_data['strike'] >= px)]
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
                        put_subtext = f"Snapped to {best_put[0]} at ${target_put:.2f}."
                    else:
                        target_put = math_floor
                        put_subtext = f"Using Auto-Math Floor."

                    st.write("---")
                    st.markdown(f"### **{calc_tk} Current Price: ${px:.2f}**")
                    
                    col_m, col_s1, col_s2, col_s3 = st.columns(4)
                    with col_m:
                        st.markdown(f"""<div class="sniper-box">
                            <div class="sniper-title">1. Auto-Math Move</div>
                            <div class="sniper-value put-color">Floor: ${math_floor:.2f}</div>
                            <div class="sniper-value call-color">Ceiling: ${math_ceil:.2f}</div>
                            </div>""", unsafe_allow_html=True)
                    with col_s1:
                        st.markdown(f"""<div class="sniper-box">
                            <div class="sniper-title">2. Price Action</div>
                            <div style="color:#00b09b;"><b>S1:</b> ${s1:.2f} | <b>S2:</b> ${s2:.2f}</div>
                            <div style="color:#ff4b4b; margin-top:5px;"><b>R1:</b> ${r1:.2f} | <b>R2:</b> ${r2:.2f}</div>
                            </div>""", unsafe_allow_html=True)
                    with col_s2:
                        st.markdown(f"""<div class="sniper-box">
                            <div class="sniper-title">3. Volume Profile</div>
                            <div class="sniper-value neutral-color">POC: ${poc_price:.2f}</div>
                            </div>""", unsafe_allow_html=True)
                    with col_s3:
                        st.markdown(f"""<div class="sniper-box">
                            <div class="sniper-title">4. Options Walls</div>
                            <div style="color:#00b09b;"><b>Put Wall:</b> {put_wall_str}</div>
                            <div style="color:#ff4b4b; margin-top:5px;"><b>Call Wall:</b> {call_wall_str}</div>
                            </div>""", unsafe_allow_html=True)
                    
                    st.write("---")
                    st.markdown("#### 🎯 Target Strikes")
                    c_tgt1, c_tgt2 = st.columns(2)
                    c_tgt1.markdown(f"""<div class="target-box-put"><div class="target-title" style="color: #00b09b;">🟢 TARGET PUT: ${target_put:.2f}</div><div class="target-sub">{put_subtext}</div></div>""", unsafe_allow_html=True)
                    c_tgt2.markdown(f"""<div class="target-box-call"><div class="target-title" style="color: #ff4b4b;">🔴 TARGET CALL: ${math_ceil:.2f}</div><div class="target-sub">Auto-Ceiling</div></div>""", unsafe_allow_html=True)

                    if not puts_data.empty:
                        st.write("---")
                        st.markdown("#### 🛒 Live Premium Matrix (Puts)")
                        display_puts = puts_data[(puts_data['strike'] <= px) & (puts_data['strike'] > px * 0.6)].copy()
                        if not display_puts.empty:
                            display_puts['Distance %'] = ((px - display_puts['strike']) / px) * 100
                            display_puts['Mid'] = (display_puts['bid'] + display_puts['ask']) / 2
                            display_puts = display_puts.sort_values(by='strike', ascending=False)
                            matrix_df = display_puts[['strike', 'Distance %', 'bid', 'ask', 'Mid', 'openInterest']]
                            matrix_df.columns = ['Strike', 'Distance (%)', 'Bid', 'Ask', 'Mid Premium', 'Open Interest']
                            st.dataframe(matrix_df.style.format({'Strike': '${:.2f}', 'Distance (%)': '{:.1f}%', 'Bid': '${:.2f}', 'Ask': '${:.2f}', 'Mid Premium': '${:.2f}', 'Open Interest': '{:,.0f}'}), use_container_width=True, hide_index=True)
            except Exception as e: st.error(f"Calculation Error: {e}")

# --- TAB 3: TRADE BOOK ---
with tab_ledger:
    df_j = st.session_state.journal
    
    # ----------------------------------------------------
    # DATA PARSING ENGINE (Open/Credit Basis Window Slicing)
    # ----------------------------------------------------
    today = datetime.now().date()
    current_year = today.year
    current_month_num = today.month
    current_month_name = today.strftime("%B")
    current_week_num = datetime.now().isocalendar()[1]
    
    # Process Slices based strictly on standard transaction 'Date'
    if not df_j.empty:
        df_j['parsed_open_date'] = pd.to_datetime(df_j['Date'], errors='coerce').dt.date
        df_j['parsed_expiry_date'] = pd.to_datetime(df_j['Expiry'], errors='coerce').dt.date
        
        # This Week Window
        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=6)
        this_week_df = df_j[(df_j['parsed_open_date'] >= start_of_week) & (df_j['parsed_open_date'] <= end_of_week)]
        weekly_profit = this_week_df["Premium"].sum()
        
        # Month to Date Window
        mtd_df = df_j[(pd.to_datetime(df_j['Date']).dt.year == current_year) & (pd.to_datetime(df_j['Date']).dt.month == current_month_num)]
        mtd_profit = mtd_df["Premium"].sum()
        
        # Year to Date Window
        ytd_df = df_j[pd.to_datetime(df_j['Date']).dt.year == current_year]
        ytd_profit = ytd_df["Premium"].sum()
        
        # Structural Metrics Engine (DTE and Averages)
        valid_dte_df = this_week_df.dropna(subset=['parsed_open_date', 'parsed_expiry_date'])
        if not valid_dte_df.empty:
            avg_dte = int((valid_dte_df['parsed_expiry_date'] - valid_dte_df['parsed_open_date']).dt.days.mean())
        else:
            avg_dte = 45 # Default engine fallback
            
        unique_weeks = df_j['Date'].apply(lambda x: pd.to_datetime(x).isocalendar()[1]).nunique()
        avg_weekly_premium = ytd_profit / max(unique_weeks, 1)
        
        # Year-End Projection Math Model
        days_elapsed = max((datetime.now().date() - datetime(current_year, 1, 1).date()).days, 1)
        ye_projection = (ytd_profit / days_elapsed) * 365
    else:
        weekly_profit, mtd_profit, ytd_profit, avg_dte, avg_weekly_premium, ye_projection = 0.0, 0.0, 0.0, 45, 0.0, 0.0
        this_week_df = pd.DataFrame()

    # ----------------------------------------------------
    # THE 4-BOX STREAMLIT DASHBOARD TERMINAL LAYOUT
    # ----------------------------------------------------
    row1_col1, row1_col2 = st.columns(2)
    
    # BOX 1: THE PREMIUMS DASHBOARD CARD
    with row1_col1:
        st.markdown(f"""
        <div class="terminal-card">
            <div class="card-title">Premiums Strategy Desk</div>
            <div class="main-metric">${weekly_profit:,.2f}</div>
            <div class="sub-metric-row">
                <span>Avg DTE: {avg_dte}d</span>
                <span>Avg Weekly Premium: ${avg_weekly_premium:,.2f}</span>
            </div>
            <div class="data-row">
                <span class="data-label">{current_month_name} Production</span>
                <span class="data-value positive">${mtd_profit:,.2f}</span>
            </div>
            <div class="data-row">
                <span class="data-label">{current_year} YTD Balance</span>
                <span class="data-value positive">${ytd_profit:,.2f}</span>
            </div>
            <div class="data-row">
                <span class="data-label">Year-End Projection</span>
                <span class="data-value neutral">${ye_projection:,.2f}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
    # BOX 2: THE QUANTS CREED RECORD PANEL
    with row1_col2:
        st.markdown("""
        <div class="creed-box">
            <div class="creed-title">🧠 The Quants Creed</div>
            <div class="creed-text">
                <b>3 Emergency Protocols - when the market goes against you:</b><br>
                • <b>Cut:</b> Take the 200% - 300% mechanical loss. No hesitation.<br>
                • <b>Roll:</b> Roll out in time, but only for a net credit.<br>
                • <b>Hold:</b> Best is to wait it out and accept you could lose the entire collateral amount.<br><br>
                <b>The 45-DTE Golden Rules:</b><br>
                🎯 Close trades when hitting 60% - 75% profit.<br>
                ⏱️ Optimal holding period is 20 to 30 days (Target: 24 DTE)<br>
                ⚠️ Do not hold into the final 20 days — Gamma risk will destroy your steady Theta gains.
            </div>
        </div>
        """, unsafe_allow_html=True)

    row2_col1, row2_col2 = st.columns(2)
    
    # BOX 3: TICKER PERFORMANCE GRID (Cross-referenced to current week profit)
    with row2_col1:
        st.markdown('<div class="card-title" style="margin-bottom: 5px;">Active Weekly Allocations</div>', unsafe_allow_html=True)
        if not this_week_df.empty:
            # Build clean breakdown table metrics
            grid_records = []
            for ticker, group in this_week_df.groupby("Ticker"):
                cc_val = group[group["Type"].astype(str).str.contains("Call", na=False)]["Premium"].sum()
                put_val = group[group["Type"].astype(str).str.contains("Put", na=False)]["Premium"].sum()
                total_val = cc_val + put_val
                grid_records.append({"Ticker": ticker, "Covered Call": cc_val, "PUT": put_val, "Total Premium": total_val})
            
            grid_df = pd.DataFrame(grid_records)
            # Append Total Cross-reference Check Row at the bottom
            total_row = pd.DataFrame([{"Ticker": "TOTAL", "Covered Call": grid_df["Covered Call"].sum(), "PUT": grid_df["PUT"].sum(), "Total Premium": grid_df["Total Premium"].sum()}])
            grid_df = pd.concat([grid_df, total_row], ignore_index=True)
            
            st.dataframe(grid_df.style.format({
                'Covered Call': '${:,.2f}',
                'PUT': '${:,.2f}',
                'Total Premium': '${:,.2f}'
            }).background_gradient(subset=['Total Premium'], cmap='BuGn', low=0.0, high=0.3), use_container_width=True, hide_index=True)
        else:
            st.info("No options logged or active in the current weekly window cycle.")

    # BOX 4: MARKET BENCHMARK RANKINGS & TOP PERFORMERS DUAL CORE PANEL
    with row2_col2:
        sub_left, sub_right = st.columns(2)
        
        with sub_left:
            st.markdown('<div class="card-title" style="margin-bottom: 5px;">📊 Market Rankings YTD</div>', unsafe_allow_html=True)
            live_benchmarks = get_market_rankings_ytd()
            
            # Estimate structural baseline performance percent return against standard margin limits
            account_return_pct = (ytd_profit / 250000.0) * 100 if ytd_profit != 0 else 0.0
            
            for index_name, return_val in live_benchmarks.items():
                st.markdown(f"""
                <div class="data-row">
                    <span class="data-label">{index_name}</span>
                    <span class="data-value">+{return_val:.2f}%</span>
                </div>
                """, unsafe_allow_html=True)
            st.markdown(f"""
            <div class="data-row" style="background: rgba(0, 176, 155, 0.06); border-radius: 4px; padding: 4px 6px;">
                <span class="data-label" style="color: #00b09b; font-weight: bold;">Lucky Money Lab</span>
                <span class="data-value positive">+{account_return_pct:.2f}%</span>
            </div>
            """, unsafe_allow_html=True)
            
        with sub_right:
            st.markdown('<div class="card-title" style="margin-bottom: 5px;">🏆 Top 5 Performers</div>', unsafe_allow_html=True)
            if not df_j.empty:
                top_perf = df_j.groupby("Ticker")["Premium"].sum().sort_values(ascending=False).head(5).reset_index()
                for _, row in top_perf.iterrows():
                    st.markdown(f"""
                    <div class="data-row">
                        <span class="data-label">{row['Ticker']}</span>
                        <span class="data-value positive">${row['Premium']:,.2f}</span>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.caption("Awaiting performance ledger history computation updates.")

    st.write("---")
    
    # ----------------------------------------------------
    # SINGLE-LEG OPTION LOGGING INTERFACE FORM
    # ----------------------------------------------------
    with st.expander("➕ Log New Trade Entry", expanded=True):
        with st.form("new_trade_form", clear_on_submit=True):
            l1, l2, l3 = st.columns(3)
            _raw_tk = l1.text_input("Ticker Label", placeholder="e.g. TSLA")
            n_ex = l2.date_input("Contract Expiry", datetime.now().date() + timedelta(days=45))
            n_qt = l3.number_input("Contract Volume Qty", value=1, min_value=1)
            
            l4, l5, l6 = st.columns(3)
            n_ty = l4.selectbox("Execution Strategy Class", ["Short Put", "Covered Call"])
            n_st = l5.number_input("Strike Target (Sell)", value=None, format="%.1f", placeholder="e.g. 150.0")
            n_op = l6.number_input("Net Premium Captured Price", value=None, format="%.2f", placeholder="e.g. 1.45")
            
            submitted = st.form_submit_button("🚀 Commit Trade to Ledger Network", use_container_width=True, type="primary")
            
            if submitted:
                n_tk = _raw_tk.upper() if _raw_tk else None
                if n_tk and n_st is not None and n_op is not None:
                    # Single leg operational execution math engine ($1.05 per contract contract standard fee limits)
                    comm_rate = 1.05
                    comm = round(n_qt * comm_rate, 2)
                    net = round((float(n_op) * 100 * n_qt) - comm, 2)
                    
                    stat = "Open / Active"
                    if n_ex < datetime.now().date(): stat = "Expired (Win)"
                    
                    new_row = pd.DataFrame([{
                        "Date": str(datetime.now().date()), "Ticker": n_tk, "Type": n_ty, 
                        "Strike": round(n_st, 1), "Long Strike": 0.0,
                        "Expiry": str(n_ex), "Open Price": round(float(n_op), 2), 
                        "Close Price": 0.0, "Qty": n_qt, "Commission": comm, "Premium": net, "Status": stat
                    }])
                    st.session_state.journal = sort_ledger(pd.concat([df_j, new_row], ignore_index=True))
                    save_journal(st.session_state.journal)
                    st.rerun()

    st.write("### Complete Trade History Ledger Block")
    
    display_df = st.session_state.journal.drop(columns=['temp_exp', 'temp_date', 'status_rank', 'parsed_open_date', 'parsed_expiry_date'], errors='ignore')
    
    edt = st.data_editor(
        display_df, 
        num_rows="dynamic", 
        use_container_width=True, 
        key="ledger_final_locked",
        column_config={
            "Date": st.column_config.TextColumn("Date", help="YYYY-MM-DD Setup"),
            "Strike": st.column_config.NumberColumn(format="%.2f"),
            "Long Strike": st.column_config.NumberColumn(format="%.2f"),
            "Open Price": st.column_config.NumberColumn(format="%.2f"),
            "Close Price": st.column_config.NumberColumn(format="%.2f"),
            "Commission": st.column_config.NumberColumn(format="$%.2f"),
            "Premium": st.column_config.NumberColumn(format="$%.2f")
        }
    )

    if not edt.equals(display_df):
        updated_df = refresh_calculations(edt)
        st.session_state.journal = updated_df
        save_journal(updated_df)
        st.rerun()

st.markdown(f'<div class="footer-right">Repository Master Live Handshake Sync: {st.session_state.last_update}</div>', unsafe_allow_html=True)

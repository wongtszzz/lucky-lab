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
    /* Global Background Override */
    .stApp { background-color: #0E1117; color: #E6EDF3; }
    
    /* Dark Dashboard Card Styling */
    .dash-card {
        background-color: #161A25; 
        border: 1px solid #2D3342;
        border-radius: 12px;
        padding: 20px;
        height: 100%;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
        margin-bottom: 15px;
    }
    .dash-title { font-size: 0.9em; font-weight: 700; color: #8B949E; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 15px; border-bottom: 1px solid #2D3342; padding-bottom: 8px;}
    .dash-metric-row { display: flex; justify-content: space-between; margin-bottom: 10px; font-size: 1.1em; }
    .dash-metric-label { color: #8B949E; }
    .dash-metric-val { color: #E6EDF3; font-weight: 600; }
    .dash-metric-green { color: #3FB950; font-weight: 700; }
    .dash-metric-red { color: #F85149; font-weight: 700; }
    .dash-subtext { font-size: 0.8em; color: #8B949E; font-style: italic; margin-top: -5px; margin-bottom: 15px;}
    
    /* Creed Box */
    .creed-text { font-size: 0.9em; line-height: 1.6; color: #C9D1D9; }
    .creed-highlight { color: #58A6FF; font-weight: 600; }

    /* Old Styles needed for Macro & Safezone Tabs */
    .sniper-box { background-color: rgba(30, 30, 30, 0.5); border: 1px solid rgba(128, 128, 128, 0.3); border-radius: 8px; padding: 15px; text-align: center; height: 100%; }
    .sniper-title { font-size: 0.85em; color: #aaa; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 5px; }
    .sniper-value { font-size: 1.8em; font-weight: bold; }
    .put-color { color: #00b09b; }
    .call-color { color: #ff4b4b; }
    .neutral-color { color: #f39c12; }
    .synthesis-box { background-color: rgba(28, 131, 225, 0.08); border-left: 4px solid #1c83e1; padding: 20px; border-radius: 5px; margin-bottom: 20px;}
    .target-box-put { background-color: rgba(0, 176, 155, 0.1); border-left: 5px solid #00b09b; padding: 20px; border-radius: 5px; margin-bottom: 15px; }
    .target-box-call { background-color: rgba(255, 75, 75, 0.1); border-left: 5px solid #ff4b4b; padding: 20px; border-radius: 5px; margin-bottom: 15px; }
    .target-title { font-size: 2.2em; font-weight: 900; margin: 0; }
    .target-sub { margin: 5px 0 0 0; color: #ccc; font-size: 1.1em; }
    .auto-risk-banner { background-color: rgba(255, 255, 255, 0.05); padding: 10px 15px; border-radius: 5px; border: 1px dashed rgba(255,255,255,0.2); margin-top: 10px; margin-bottom: 10px; text-align: center; }
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
        
        p = round(((open_p - close_p) * 100 * qty) - comm, 2)
        if "LEAPS Call" in str(r.get("Type", "")):
            p = round(((close_p - open_p) * 100 * qty) - comm, 2)
        
        try: ex_d = pd.to_datetime(r["Expiry"]).date()
        except: ex_d = datetime.now().date()
        
        if close_p > 0: 
            s = "Closed (Loss)" if close_p > open_p else "Closed (Win)"
            if "LEAPS Call" in str(r.get("Type", "")):
                 s = "Closed (Win)" if close_p > open_p else "Closed (Loss)"
        elif "Open" in current_status and ex_d < datetime.now().date(): 
            s = "Expired (Win)"
            if "LEAPS Call" in str(r.get("Type", "")): s = "Expired (Loss)"
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
        st.toast("🧹 Auto-Sweep: Passed expiration dates detected. Trades marked as Expired and permanently moved to Realized P&L.", icon="✅")

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

# --- 3. UI TABS ---
tab_macro, tab_safezone, tab_ledger = st.tabs([
    "🌍 Macro Playbook", 
    "🎯 Sniper Safe Zones", 
    "📓 Portfolio & Trade Book"
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
            
    st.caption(f"Last API Sync: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (Pulls fresh data every 15 mins or on manual refresh)")
    
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
        
        st.markdown("#### 🧠 AI Chief Economist Brief")
        
        @st.cache_data(ttl=3600) 
        def get_ai_macro_brief(vix, dxy, oil, breadth_avg):
            try:
                genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
                valid_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                target_model = next((m for m in valid_models if 'lite' in m), valid_models[0])
                model = genai.GenerativeModel(target_model)
                
                prompt = f"""
                You are the ruthless, professional Chief Market Strategist for an options volatility trading desk. 
                Write a morning macro brief based strictly on these live numbers:
                - VIX: {vix:.2f}
                - DXY (US Dollar): {dxy:.2f}
                - WTI Crude Oil: ${oil:.2f}
                - Market Breadth: {breadth_avg:.0f}% of stocks trending up.
                
                Format your response in exactly 3 short, punchy sections using Markdown. Do not use filler words.
                
                ### 🌍 The Current Regime
                (Synthesize what these specific metrics mean together right now. Identify if it is risk-on, risk-off, a divergent top, or oversold capitulation).
                
                ### 📰 The Forward Look
                (Based on these metrics, what macroeconomic themes or breaking points should the desk watch out for in the coming days).
                
                ### 🎯 Option Seller Action Plan
                (Give specific tactical advice. Should we sell 45-DTE Puts? Switch to Call Credit Spreads? Avoid weeklies? Be definitive).
                """
                
                response = model.generate_content(prompt)
                return response.text
                
            except Exception as e:
                try:
                    debug_models = [m.name for m in genai.list_models()]
                    return f"⚠️ **AI Engine Offline.** <br><br><b>Error:</b> {e}<br><br><b>Google says these are your ONLY approved models:</b><br> {debug_models}"
                except:
                    return f"⚠️ **AI Engine Offline.** Error details: {e}"

        with st.spinner("Chief Economist is analyzing the live data..."):
            ai_brief = get_ai_macro_brief(vix_px, dxy_px, oil_px, breadth_avg)
            
        st.markdown(f"""
        <div class="synthesis-box">
            {ai_brief}
        </div>
        """, unsafe_allow_html=True)

    except Exception as e: pass

# --- TAB 2: SNIPER SAFE ZONES ---
with tab_safezone:
    st.markdown("#### 🎯 Sniper Safe Zones")
    
    c_tog1, c_tog2 = st.columns([3, 1])
    with c_tog1:
        st.caption("Enter ticker and expiry to calculate structural support. Matrix will load below.")
    with c_tog2:
        dynamic_risk = st.checkbox("🛡️ Enable RSI Risk Shield", value=False, help="When checked, modifies risk multiplier based on Oversold/Overbought conditions.")
    
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
                        risk_status = f"⚠️ Shield OFF: Rigid 1.0x Multiplier applied regardless of RSI ({live_rsi:.1f})."

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
                        put_subtext = f"Snapped to {best_put[0]} at ${target_put:.2f}. Tucked safely behind structure, just below the Math Floor (${math_floor:.2f})."
                    else:
                        target_put = math_floor
                        put_subtext = f"Using Auto-Math Floor. Structural supports are too far away to justify sacrificing your premium."

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
                    st.markdown("#### 🎯 Target Strikes")
                    c_tgt1, c_tgt2 = st.columns(2)
                    c_tgt1.markdown(f"""<div class="target-box-put"><div class="target-title" style="color: #00b09b;">🟢 TARGET PUT: ${target_put:.2f}</div><div class="target-sub">{put_subtext}</div></div>""", unsafe_allow_html=True)
                    c_tgt2.markdown(f"""<div class="target-box-call"><div class="target-title" style="color: #ff4b4b;">🔴 TARGET CALL: ${math_ceil:.2f}</div><div class="target-sub">Auto-Ceiling</div></div>""", unsafe_allow_html=True)

                    if not puts_data.empty:
                        st.write("---")
                        st.markdown("#### 🛒 Live Premium Matrix (Puts)")
                        st.caption("Check the 'Bid' and 'Ask' closely. If the spread is wide (e.g. Bid $0.10, Ask $1.00), do NOT trade it. Slippage will kill you.")
                        
                        display_puts = puts_data[(puts_data['strike'] <= px) & (puts_data['strike'] > px * 0.6)].copy()
                        
                        if not display_puts.empty:
                            display_puts['Distance %'] = ((px - display_puts['strike']) / px) * 100
                            display_puts['Mid'] = (display_puts['bid'] + display_puts['ask']) / 2
                            display_puts = display_puts.sort_values(by='strike', ascending=False)
                            
                            matrix_df = display_puts[['strike', 'Distance %', 'bid', 'ask', 'Mid', 'openInterest']]
                            matrix_df.columns = ['Strike', 'Distance (%)', 'Bid', 'Ask', 'Mid Premium', 'Open Interest']
                            
                            st.dataframe(matrix_df.style.format({
                                'Strike': '${:.2f}', 
                                'Distance (%)': '{:.1f}%', 
                                'Bid': '${:.2f}', 
                                'Ask': '${:.2f}', 
                                'Mid Premium': '${:.2f}',
                                'Open Interest': '{:,.0f}'
                            }).highlight_max(subset=['Open Interest'], color='rgba(0,176,155,0.2)'), use_container_width=True, hide_index=True)
                        else:
                            st.warning("No relevant strikes found below current price.")
                    else:
                        st.warning("Could not fetch Live Premium Matrix. Exchange data may be unavailable.")

            except Exception as e:
                st.error(f"Calculation Error: {e}")


# --- TAB 3: PORTFOLIO DASHBOARD & TRADE BOOK ---
with tab_ledger:
    df_j = st.session_state.journal.copy()
    
    # --- DATA PROCESSING ---
    df_j['temp_date'] = pd.to_datetime(df_j['Date'], errors='coerce')
    realized_df = df_j[~df_j["Status"].astype(str).str.contains("Open", na=False)].copy()
    
    # Time Filters
    today = datetime.now().date()
    start_of_week = today - timedelta(days=today.weekday())
    start_of_month = today.replace(day=1)
    
    current_year = today.year
    start_of_year = today.replace(month=1, day=1)
    
    # Advanced Realization Mapping
    def calculate_realization_date(row):
        try:
            status_str = str(row['Status'])
            opened_dt = pd.to_datetime(row['Date']).date()
            expiry_dt = pd.to_datetime(row['Expiry']).date()
            if "Expired" in status_str:
                return expiry_dt
            elif "Closed" in status_str:
                if expiry_dt <= today:
                    return expiry_dt
                return opened_dt
            return opened_dt
        except:
            return today

    if not realized_df.empty:
        realized_df['realized_date'] = realized_df.apply(calculate_realization_date, axis=1)
        weekly_p = realized_df[realized_df['realized_date'] >= start_of_week]["Premium"].sum()
        monthly_p = realized_df[realized_df['realized_date'] >= start_of_month]["Premium"].sum()
        ytd_p = realized_df[realized_df['realized_date'] >= start_of_year]["Premium"].sum()
    else:
        weekly_p, monthly_p, ytd_p = 0.0, 0.0, 0.0
    
    # Portfolio Metadata Metrics
    valid_dte_df = df_j.copy()
    valid_dte_df['t_open'] = pd.to_datetime(valid_dte_df['Date'], errors='coerce')
    valid_dte_df['t_exp'] = pd.to_datetime(valid_dte_df['Expiry'], errors='coerce')
    valid_dte_df['dte'] = (valid_dte_df['t_exp'] - valid_dte_df['t_open']).dt.days
    avg_dte = valid_dte_df['dte'].mean() if not valid_dte_df['dte'].dropna().empty else 0.0
    
    day_of_year = today.timetuple().tm_yday
    weeks_passed = max(1, day_of_year / 7)
    avg_weekly_p = ytd_p / weeks_passed
    
    # Projection Math
    trading_days_passed = max(1, day_of_year * (252/365))
    projected_p = (ytd_p / trading_days_passed) * 252 if trading_days_passed > 0 else 0.0

    # Dynamic Formatting Helper (FIXED: Strips minus sign entirely, uses color to denote win/loss)
    def fmt_money(val):
        color = "dash-metric-green" if val >= 0 else "dash-metric-red"
        text = f"${abs(val):,.0f}"
        return color, text

    wk_col, wk_str = fmt_money(weekly_p)
    mo_col, mo_str = fmt_money(monthly_p)
    ytd_col, ytd_str = fmt_money(ytd_p)
    proj_col, proj_str = fmt_money(projected_p)
    avg_wk_col, avg_wk_str = fmt_money(avg_weekly_p)

    # --- ROW 1: PREMIUMS & CREED ---
    r1c1, r1c2 = st.columns([1, 2])
    
    with r1c1:
        st.markdown(f"""
        <div class="dash-card">
            <div class="dash-title">🤑 Premiums</div>
            
            <div class="dash-metric-row" style="margin-bottom: 2px;">
                <span class="dash-metric-label">This Week</span>
                <span class="{wk_col}">{wk_str}</span>
            </div>
            <div class="dash-metric-row" style="margin-bottom: 15px;">
                <span class="dash-metric-label" style="font-size: 0.82em; font-style: italic; color: #8B949E;">Avg DTE: {avg_dte:.1f} days</span>
                <span class="{avg_wk_col}" style="font-size: 0.82em; text-align: right;">Avg Weekly: {avg_wk_str}</span>
            </div>
            
            <div class="dash-metric-row">
                <span class="dash-metric-label">{today.strftime('%B')} (MTD)</span>
                <span class="{mo_col}">{mo_str}</span>
            </div>
            
            <div class="dash-metric-row" style="margin-top: 15px;">
                <span class="dash-metric-label">{current_year} YTD</span>
                <span class="{ytd_col}" style="font-size: 1.2em;">{ytd_str}</span>
            </div>
            
            <div class="dash-metric-row" style="border-top: 1px dashed #2D3342; padding-top: 10px; margin-top: 15px;">
                <span class="dash-metric-label">Year-End Projection</span>
                <span class="{proj_col}">{proj_str}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
    with r1c2:
        st.markdown("""
        <div class="dash-card">
            <div class="dash-title">🧠 The Quants Creed</div>
            <div class="creed-text">
                <b>3 Emergency Protocols - when the market goes against you:</b><br>
                <b>Cut:</b> Take the 200% - 300% mechanical loss. No hesitation.<br>
                <b>Roll:</b> Roll out in time, but only for a net credit.<br>
                <b>Hold:</b> Best is to wait it out and accept you could lose the entire (spread - premium).<br><br>
                <b>The 45-DTE Golden Rules:</b><br>
                🎯 Close trades when hitting 60% - 75% profit.<br>
                ⏱️ Optimal holding period is 20 to 30 days (Target: 24 DTE)<br>
                ⚠️ Do not hold into the final 20 days — Gamma risk will destroy your steady Theta gains.
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.write("")

    # --- ROW 2: TICKER MATRIX & ROI CHART ---
    r2c1, r2c2 = st.columns([1.2, 1])
    
    with r2c1:
        st.markdown('<div class="dash-card"><div class="dash-title">Ticker Breakdown (Realized)</div>', unsafe_allow_html=True)
        if not realized_df.empty:
            def get_cat(t):
                if "Covered Call" in str(t): return "Covered Call"
                elif "Put" in str(t): return "PUT"
                elif "LEAPS" in str(t): return "LEAPS"
                return "Other"
            
            realized_df["Category"] = realized_df["Type"].apply(get_cat)
            pivot_df = realized_df.pivot_table(index="Ticker", columns="Category", values="Premium", aggfunc="sum").fillna(0)
            
            for col in ["Covered Call", "PUT", "LEAPS"]:
                if col not in pivot_df.columns: pivot_df[col] = 0.0
                
            pivot_df["Total Premium"] = pivot_df["Covered Call"] + pivot_df["PUT"] + pivot_df["LEAPS"]
            pivot_df = pivot_df.sort_values("Total Premium", ascending=False).reset_index()
            
            st.dataframe(
                pivot_df,
                column_config={
                    "Ticker": st.column_config.TextColumn("Ticker", width="small"),
                    "Covered Call": st.column_config.NumberColumn("CC", format="$%.0f"),
                    "PUT": st.column_config.NumberColumn("PUT", format="$%.0f"),
                    "LEAPS": st.column_config.NumberColumn("LEAPS", format="$%.0f"),
                    "Total Premium": st.column_config.ProgressColumn(
                        "Total Premium",
                        help="Total realized premium per ticker",
                        format="$%.0f",
                        min_value=0,
                        max_value=float(pivot_df["Total Premium"].max()) if not pivot_df.empty else 100,
                    ),
                },
                hide_index=True,
                use_container_width=True
            )
            
            st.markdown(f"<div style='text-align: right; color: #8B949E; font-weight: bold;'>GRAND TOTAL: <span style='color:#3FB950;'>${ytd_p:,.0f}</span></div>", unsafe_allow_html=True)
        else:
            st.caption("No closed trades logged yet.")
        st.markdown('</div>', unsafe_allow_html=True)

    with r2c2:
        st.markdown('<div class="dash-card"><div class="dash-title">Cumulative P&L (YTD)</div>', unsafe_allow_html=True)
        if not realized_df.empty:
            chart_data = realized_df[realized_df['temp_date'].dt.date >= start_of_year].sort_values('temp_date').copy()
            if not chart_data.empty:
                chart_data['Cumulative'] = chart_data['Premium'].cumsum()
                st.area_chart(chart_data.set_index('temp_date')['Cumulative'], color="#FF4B4B")
            else:
                st.caption("No trades closed this year yet.")
        else:
            st.caption("No data to chart.")
        st.markdown('</div>', unsafe_allow_html=True)

    st.write("")

    # --- ROW 3: MARKETS & TOP PERFORMERS ---
    r3c1, r3c2 = st.columns([1, 1])
    
    with r3c1:
        st.markdown('<div class="dash-card"><div class="dash-title">Market Rankings (YTD)</div>', unsafe_allow_html=True)
        
        @st.cache_data(ttl=3600)
        def get_market_ytd():
            tkrs = {"Nasdaq": "^IXIC", "Russell 2000": "^RUT", "S&P 500": "^GSPC", "Dow Jones": "^DJI"}
            results = []
            for name, tkr in tkrs.items():
                try:
                    hist = yf.Ticker(tkr).history(period="ytd")
                    ret = ((hist['Close'].iloc[-1] - hist['Close'].iloc[0]) / hist['Close'].iloc[0]) * 100
                    results.append({"Index": name, "YTD Return": ret})
                except: pass
            return pd.DataFrame(results)

        market_df = get_market_ytd()
        base_capital = 100000 
        my_ret = (ytd_p / base_capital) * 100
        market_df.loc[len(market_df)] = {"Index": "🧪 My Options Book", "YTD Return": my_ret}
        market_df = market_df.sort_values("YTD Return", ascending=False).reset_index(drop=True)
        
        st.dataframe(
            market_df,
            column_config={
                "Index": "Asset",
                "YTD Return": st.column_config.NumberColumn("Performance", format="%.2f%%")
            },
            hide_index=True,
            use_container_width=True
        )
        st.markdown('</div>', unsafe_allow_html=True)

    with r3c2:
        st.markdown('<div class="dash-card"><div class="dash-title">Top & Worst Performers (MTD)</div>', unsafe_allow_html=True)
        mtd_df = realized_df[realized_df['temp_date'].dt.date >= start_of_month]
        if not mtd_df.empty:
            mtd_grouped = mtd_df.groupby("Ticker")["Premium"].sum().reset_index()
            mtd_grouped = mtd_grouped.sort_values("Premium", ascending=False)
            
            c_top, c_bot = st.columns(2)
            with c_top:
                st.markdown("<span style='color:#8B949E; font-size:0.9em;'>Top 5 Winners</span>", unsafe_allow_html=True)
                st.dataframe(mtd_grouped.head(5), hide_index=True, column_config={"Premium": st.column_config.NumberColumn(format="$%.0f")}, use_container_width=True)
            with c_bot:
                st.markdown("<span style='color:#8B949E; font-size:0.9em;'>Bottom 5 (or Losers)</span>", unsafe_allow_html=True)
                st.dataframe(mtd_grouped.tail(5).sort_values("Premium", ascending=True), hide_index=True, column_config={"Premium": st.column_config.NumberColumn(format="$%.0f")}, use_container_width=True)
        else:
            st.caption("No closed trades this month.")
        st.markdown('</div>', unsafe_allow_html=True)

    st.write("---")
    
    # --- LOG NEW TRADE ---
    with st.expander("➕ Log New Trade", expanded=False):
        with st.form("new_trade_form", clear_on_submit=True):
            l1, l2, l3, l4 = st.columns(4)
            _raw_tk = l1.text_input("Ticker", placeholder="e.g. AAPL")
            n_ex = l2.date_input("Expiry", datetime.now().date() + timedelta(days=45))
            
            n_ty = l3.selectbox("Type", [
                "Short Put", 
                "Covered Call", 
                "LEAPS Call"
            ])
            n_qt = l4.number_input("Qty", value=1, min_value=1)
            
            l5, l6, l7 = st.columns(3)
            n_st = l5.number_input("Strike (Sell)", value=None, format="%.1f", placeholder="e.g. 150.5")
            n_ls = l6.number_input("Long Strike (Buy)", value=None, format="%.1f", placeholder="(Optional)")
            n_op = l7.number_input("Net Premium", value=None, format="%.2f", placeholder="e.g. 0.85")
            
            submitted = st.form_submit_button("🚀 Commit Trade", use_container_width=True, type="primary")
            
            if submitted:
                n_tk = _raw_tk.upper() if _raw_tk else None
                if n_tk and n_st is not None and n_op is not None:
                    comm_rate = 2.10 if (n_ls is not None and n_ls > 0) else 1.05
                    comm = round(n_qt * comm_rate, 2)
                    
                    net = round((float(n_op) * 100 * n_qt) - comm, 2)
                    if n_ty == "LEAPS Call": net = -abs(net)
                    
                    stat = "Open / Active"
                    if n_ex < datetime.now().date(): stat = "Expired (Win)"
                    
                    new_row = pd.DataFrame([{
                        "Date": str(datetime.now().date()), "Ticker": n_tk, "Type": n_ty, 
                        "Strike": round(n_st, 1), "Long Strike": round(float(n_ls if n_ls else 0.0), 1),
                        "Expiry": str(n_ex), "Open Price": round(float(n_op), 2), 
                        "Close Price": 0.0, "Qty": n_qt, "Commission": comm, "Premium": net, "Status": stat
                    }])
                    st.session_state.journal = sort_ledger(pd.concat([st.session_state.journal, new_row], ignore_index=True))
                    save_journal(st.session_state.journal)
                    st.rerun()

    # --- TRADE HISTORY ---
    st.write("### 📓 Raw Trade Ledger")
    
    display_df = st.session_state.journal.drop(columns=['temp_exp', 'temp_date', 'status_rank'], errors='ignore')
    
    edt = st.data_editor(
        display_df, 
        num_rows="dynamic", 
        use_container_width=True, 
        key="ledger_final_locked",
        column_config={
            "Date": st.column_config.TextColumn("Date", help="YYYY-MM-DD"),
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

st.markdown(f'<div class="footer-right">Last Synced to GitHub: {st.session_state.last_update}</div>', unsafe_allow_html=True)

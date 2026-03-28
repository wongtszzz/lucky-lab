import streamlit as st
import pandas as pd
import numpy as np
import io
import base64
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
        border: 1px solid rgba(128, 128, 128, 0.2);
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
    [data-testid="stMetricValue"] { font-size: 2rem !important; font-weight: 800 !important; }
    [data-testid="stMetricDelta"] { font-size: 1rem !important; color: #888888 !important; justify-content: center !important; }
    [data-testid="stMetricDelta"] > svg { display: none; }
    .footer-right { position: fixed; bottom: 10px; right: 10px; color: gray; font-size: 0.8em; z-index: 1000; }
    
    .creed-box { background-color: rgba(128, 128, 128, 0.05); border: 1px solid rgba(128, 128, 128, 0.2); border-left: 5px solid #2962FF; border-radius: 8px; padding: 15px 20px; margin-bottom: 25px; }
    .creed-title { font-weight: 800; font-size: 1.1em; margin-bottom: 10px; color: #2962FF; letter-spacing: 0.5px; }
    .creed-text { font-size: 0.95em; line-height: 1.6; }
    
    .regime-box { border-radius: 8px; padding: 20px; margin-top: 10px; margin-bottom: 25px; color: white; }
    
    .sniper-box { background-color: rgba(30, 30, 30, 0.5); border: 1px solid rgba(128, 128, 128, 0.3); border-radius: 8px; padding: 15px; text-align: center; }
    .sniper-title { font-size: 0.9em; color: #aaa; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 5px; }
    .sniper-value { font-size: 1.8em; font-weight: bold; }
    .put-color { color: #00b09b; }
    .call-color { color: #ff4b4b; }
    .neutral-color { color: #f39c12; }
    
    .synthesis-box { background-color: rgba(28, 131, 225, 0.1); border-left: 4px solid #1c83e1; padding: 15px; border-radius: 5px; margin-bottom: 20px;}
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

# --- 2. LOGIC & DATA ENGINE ---
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
        return sort_ledger(df[COLS])
    except: return pd.DataFrame(columns=COLS)

if 'journal' not in st.session_state: 
    st.session_state.journal = load_journal()
    st.session_state.last_update = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

if 'current_vix' not in st.session_state: st.session_state.current_vix = 20.0

WATCHLIST = ["AAPL", "TSLA", "NVDA", "AMD", "META", "AMZN", "MSFT", "GOOGL", "NFLX", "JPM", "BAC", "DIS", "BA", "UBER", "COIN", "PLTR", "SMCI", "ARM"]

# --- 3. UI TABS ---
tab_macro, tab_safezone, tab_screener, tab_ledger = st.tabs(["🌍 Macro Playbook", "🎯 Sniper Safe Zones", "🔎 Live Screener", "📓 Lucky Ledger"])

# --- TAB 1: MACRO PLAYBOOK (SYNCHRONIZED LOGIC) ---
with tab_macro:
    head_col, btn_col = st.columns([5, 1])
    with head_col: 
        st.markdown("#### 🌍 The 3-Pillar Macro Matrix")
    with btn_col: 
        st.button("🔄 Refresh Data", use_container_width=True, key="ref1")
    
    try:
        def get_macro_live(symbol):
            t = yf.Ticker(symbol)
            df = t.history(period='5d')
            if len(df) >= 2: return float(df['Close'].iloc[-1]), ((float(df['Close'].iloc[-1]) - float(df['Close'].iloc[-2])) / float(df['Close'].iloc[-2])) * 100
            return 0.0, 0.0
        
        # 1. Fetch Data
        oil_px, oil_pct = get_macro_live("CL=F")
        dxy_px, dxy_pct = get_macro_live("DX-Y.NYB")
        vix_px, vix_pct = get_macro_live("^VIX")
        st.session_state.current_vix = vix_px if vix_px > 0 else 20.0
        
        oil_status = "🟢 Contained" if oil_px < 80 else ("🟡 Hot" if oil_px <= 85 else "🔴 Spiking")
        dxy_status = "🟢 Weak" if dxy_px < 103 else ("🟡 Neutral" if dxy_px <= 105 else "🔴 Strong")
        vix_status = "🟢 Complacent" if vix_px < 18 else ("🟡 Elevated" if vix_px <= 25 else "🔴 Panic")

        # Render Top Metrics
        m1, m2, m3 = st.columns(3)
        m1.metric("🛢️ WTI Crude Oil", f"${oil_px:,.2f}", f"{oil_status} ({oil_pct:+.2f}%)", delta_color="inverse" if oil_px > 80 else "normal")
        m2.metric("💵 US Dollar (DXY)", f"{dxy_px:,.2f}", f"{dxy_status} ({dxy_pct:+.2f}%)", delta_color="inverse" if dxy_px > 105 else "normal")
        m3.metric("📉 Volatility (VIX)", f"{vix_px:,.2f}", f"{vix_status} ({vix_pct:+.2f}%)", delta_color="inverse" if vix_px > 25 else "normal")

        st.write("---")
        
        # 2. Fetch Breadth
        sp500_sectors = ["XLK", "XLV", "XLF", "XLY", "XLC", "XLI", "XLP", "XLE", "XLU", "XLRE", "XLB"]
        nasdaq_leaders = ["AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "TSLA", "AVGO", "COST", "NFLX", "AMD", "PEP", "CSCO", "TMUS", "ADBE"]
        
        @st.cache_data(ttl=900)
        def get_automated_breadth(ticker_list):
            try:
                df = yf.download(ticker_list, period="1mo", progress=False)
                close_df = df['Close'] if isinstance(df.columns, pd.MultiIndex) else df
                above_20ma = 0
                valid_count = 0
                for s in ticker_list:
                    if s in close_df.columns:
                        prices = close_df[s].dropna()
                        if len(prices) >= 20:
                            valid_count += 1
                            if prices.iloc[-1] > prices.tail(20).mean(): above_20ma += 1
                if valid_count == 0: return 50.0, 0, len(ticker_list)
                return (above_20ma / valid_count) * 100, above_20ma, valid_count
            except:
                return 50.0, 0, len(ticker_list)
                
        s5tw_pct, s5tw_up, s5tw_total = get_automated_breadth(sp500_sectors)
        nctw_pct, nctw_up, nctw_total = get_automated_breadth(nasdaq_leaders)
        breadth_avg = (s5tw_pct + nctw_pct) / 2
        
        st.markdown("#### 📊 Market Breadth (Live 20-Day MA Proxies)")
        b1, b2 = st.columns(2)
        
        b1.metric("S&P 500 Breadth", f"{s5tw_pct:.0f}%", f"{s5tw_up}/{s5tw_total} Sectors Trending Up", delta_color="normal" if s5tw_pct >= 50 else "inverse")
        b2.metric("Nasdaq Breadth", f"{nctw_pct:.0f}%", f"{nctw_up}/{nctw_total} Mega-Caps Trending Up", delta_color="normal" if nctw_pct >= 50 else "inverse")

        st.write("---")
        
        # 3. LIVE AI SYNTHESIS ENGINE (Synchronized to 80/20 Thresholds)
        st.markdown("#### 🧠 Live Market Synthesis")
        
        syn_oil = "Energy prices are running hot, putting upward pressure on inflation and acting as a headwind for rate cuts." if oil_px > 85 else "Crude oil remains contained, alleviating inflation fears and supporting risk assets."
        syn_dxy = "The US Dollar is showing strength, tightening global liquidity and pressuring multinational tech earnings." if dxy_px > 105 else "A weaker dollar is currently providing a highly favorable liquidity environment for equities."
        syn_vix = "However, the VIX is elevated, indicating institutional funds are actively buying downside protection. Fear is present in the order book." if vix_px > 25 else "Volatility is crushed, showing market complacency and a clear 'risk-on' environment."
        
        # Ironclad Breadth + VIX Logic Sync
        if breadth_avg >= 80: 
            syn_brd = "Under the hood, participation is exceptionally strong (Overbought). The rally is mathematically exhausted and highly vulnerable to a sudden pullback."
        elif breadth_avg <= 20: 
            if vix_px > 30:
                syn_brd = "Market breadth is severely washed out (Oversold), BUT the VIX indicates pure panic. This is capitulation, not a safe entry."
            else:
                syn_brd = "Market breadth is severely washed out (Oversold) while fear (VIX) remains contained, creating a rare structural buying opportunity."
        else: 
            syn_brd = "Market breadth is healthy and neutral, showing a standard rotation of capital between sectors."

        st.markdown(f"""
        <div class="synthesis-box">
            <b>Current Conditions:</b> {syn_oil} {syn_dxy} {syn_vix} <br><br>
            <b>Internal Health:</b> {syn_brd}
        </div>
        """, unsafe_allow_html=True)

        # 4. THE PLAYBOOK REGIME (Synchronized to 80/20 Thresholds)
        st.markdown("#### 📖 Actionable Strategy Playbook")
        
        # Priority 1: Crash/Panic
        if vix_px > 30 or (dxy_px > 108 and oil_px > 95):
            st.markdown("""
            <div class="regime-box" style="background: linear-gradient(135deg, #b91d47 0%, #800000 100%);">
                <h3 style="color: white; margin-top: 0;">🚨 REGIME: CRASHING / LIQUIDITY SQUEEZE</h3>
                <p style="font-size: 1.1em; margin-bottom: 0;">
                <b>What's happening:</b> Panic mode. Fear is extreme, funding is freezing, and everything is being sold for cash.<br><br>
                <b>Your Move:</b> HOLD CASH. Do not catch falling knives. Selling puts here is mathematically dangerous because structural support levels will fail under panic selling. Wait for the VIX to crush back down below 25 before deploying capital.
                </p>
            </div>
            """, unsafe_allow_html=True)
            
        # Priority 2: Safe Oversold Opportunity
        elif breadth_avg <= 20 and vix_px <= 25:
             st.markdown("""
            <div class="regime-box" style="background: linear-gradient(135deg, #00b09b 0%, #008080 100%);">
                <h3 style="color: white; margin-top: 0;">🎯 REGIME: OVERSOLD OPPORTUNITY</h3>
                <p style="font-size: 1.1em; margin-bottom: 0;">
                <b>What's happening:</b> The market is heavily washed out, but the VIX proves there is no systemic panic. <br><br>
                <b>Your Move:</b> BUY THE DIP (SELL PUTS). This is the optimal time for premium sellers. Use the Screener to find high VIX-Edge tech stocks and sell Cash-Secured Puts at major structural support lines.
                </p>
            </div>
            """, unsafe_allow_html=True)           

        # Priority 3: Bearish Macro
        elif vix_px > 22 or dxy_px > 105 or oil_px > 85:
            st.markdown("""
            <div class="regime-box" style="background: linear-gradient(135deg, #e67e22 0%, #d35400 100%);">
                <h3 style="color: white; margin-top: 0;">⚠️ REGIME: BEARISH / CORRECTION</h3>
                <p style="font-size: 1.1em; margin-bottom: 0;">
                <b>What's happening:</b> Macro headwinds (inflation/dollar strength) are pressuring equities.<br><br>
                <b>Your Move:</b> BE DEFENSIVE. Rotate focus to Traditional and Energy stocks. Capitalize on the downside by selling Call Credit Spreads or Covered Calls on existing positions. Avoid selling puts on high-beta tech.
                </p>
            </div>
            """, unsafe_allow_html=True)
            
        # Priority 4: Overbought Warning
        elif breadth_avg >= 80:
             st.markdown("""
            <div class="regime-box" style="background: linear-gradient(135deg, #8e44ad 0%, #9b59b6 100%);">
                <h3 style="color: white; margin-top: 0;">🔥 REGIME: OVERBOUGHT / EXHAUSTED</h3>
                <p style="font-size: 1.1em; margin-bottom: 0;">
                <b>What's happening:</b> Greed is at a maximum. Nearly everything is trending up, making the market vulnerable to a sudden, sharp pullback.<br><br>
                <b>Your Move:</b> TAKE PROFITS. Stop selling puts. This is the absolute best time to sell Covered Calls to collect rich premiums from overly greedy buyers before the inevitable dip.
                </p>
            </div>
            """, unsafe_allow_html=True)           
            
        # Priority 5: Perfect Bull Market
        elif vix_px < 18 and dxy_px < 103 and oil_px < 78:
            st.markdown("""
            <div class="regime-box" style="background: linear-gradient(135deg, #00b09b 0%, #96c93d 100%);">
                <h3 style="color: white; margin-top: 0;">🚀 REGIME: EXTREME BULLISH / RISK-ON</h3>
                <p style="font-size: 1.1em; margin-bottom: 0;">
                <b>What's happening:</b> The "Goldilocks" zone. Money is cheap, inflation is dead, and fear is nonexistent.<br><br>
                <b>Your Move:</b> STAY LONG. Heavy on Tech and Growth. Sell OTM Puts on your high-beta Watchlist. Ride the liquidity wave, but be extremely careful of sudden VIX spikes.
                </p>
            </div>
            """, unsafe_allow_html=True)
            
        # Default: Chop
        else:
            st.markdown("""
            <div class="regime-box" style="background: linear-gradient(135deg, #3a7bd5 0%, #3a6073 100%);">
                <h3 style="color: white; margin-top: 0;">⚖️ REGIME: NEUTRAL / RANGE-BOUND</h3>
                <p style="font-size: 1.1em; margin-bottom: 0;">
                <b>What's happening:</b> The market is chopping sideways, waiting for the next catalyst.<br><br>
                <b>Your Move:</b> STOCK PICKER'S MARKET. Use your Screener to find specific exhausted stocks. Keep trade durations short (Weeklies) and collect pure Theta decay on range-bound tickers.
                </p>
            </div>
            """, unsafe_allow_html=True)

    except Exception as e:
        pass

# --- TAB 2: SNIPER SAFE ZONES (Unchanged) ---
with tab_safezone:
    st.markdown("#### 🎯 Sniper Safe Zones (Math + Structure)")
    st.caption("Calculates Mathematical Expected Move and overlays it against Structural Support/Resistance data.")
    
    c1, c2, c3 = st.columns([1, 1, 2])
    with c1: calc_tk = st.text_input("Ticker", value="TSLA", key="calc_tk2").upper()
    with c2: calc_ex = st.date_input("Target Expiry", datetime.now().date() + timedelta(days=7))
    with c3:
        st.write(""); st.write("")
        run_calc = st.button("🔬 Extract Math & Structure", type="primary", use_container_width=True)
    
    if run_calc:
        with st.spinner(f"Running X-Ray data extraction on {calc_tk}..."):
            try:
                yf_tk = yf.Ticker(calc_tk)
                hist_1y = yf_tk.history(period='1y')
                
                if hist_1y.empty:
                    st.error("Invalid Ticker or No Data Found.")
                else:
                    px = float(hist_1y['Close'].iloc[-1])
                    beta = yf_tk.info.get('beta', 1.0) or 1.0
                    days_to_exp = max((calc_ex - datetime.now().date()).days, 1)
                    
                    # 1. THE MATH
                    stock_iv_proxy = st.session_state.current_vix * beta
                    exp_move_pct = (stock_iv_proxy / 100) * np.sqrt(days_to_exp / 365)
                    exp_move_dollar = px * exp_move_pct
                    math_floor = px - exp_move_dollar
                    math_ceil = px + exp_move_dollar
                    
                    # 2. PRICE ACTION
                    s1 = hist_1y['Low'].tail(30).min()
                    r1 = hist_1y['High'].tail(30).max()
                    s2 = hist_1y['Low'].tail(126).min() 
                    r2 = hist_1y['High'].tail(126).max()
                    
                    # 3. VOLUME PROFILE 
                    hist_6m = hist_1y.tail(126).copy()
                    hist_6m['Price_Bin'] = pd.cut(hist_6m['Close'], bins=30)
                    vol_profile = hist_6m.groupby('Price_Bin', observed=False)['Volume'].sum()
                    poc_interval = vol_profile.idxmax()
                    poc_price = poc_interval.mid
                    
                    # 4. OPTIONS WALLS 
                    put_wall_str, call_wall_str = "N/A", "N/A"
                    try:
                        avail_exps = yf_tk.options
                        if avail_exps:
                            target_exp = calc_ex.strftime('%Y-%m-%d')
                            if target_exp not in avail_exps: target_exp = avail_exps[0]
                            chain = yf_tk.option_chain(target_exp)
                            puts_filtered = chain.puts[(chain.puts['strike'] >= px * 0.70) & (chain.puts['strike'] <= px)]
                            calls_filtered = chain.calls[(chain.calls['strike'] <= px * 1.30) & (chain.calls['strike'] >= px)]
                            if not puts_filtered.empty:
                                put_wall = puts_filtered.loc[puts_filtered['openInterest'].idxmax()]['strike']
                                put_wall_str = f"${put_wall:.2f}"
                            if not calls_filtered.empty:
                                call_wall = calls_filtered.loc[calls_filtered['openInterest'].idxmax()]['strike']
                                call_wall_str = f"${call_wall:.2f}"
                    except: pass 
                    
                    st.write("---")
                    st.markdown(f"### **{calc_tk} X-Ray Analysis | Current Price: ${px:.2f}**")
                    
                    col_m, col_s1, col_s2, col_s3 = st.columns(4)
                    
                    with col_m:
                        st.markdown("""<div class="sniper-box">
                            <div class="sniper-title">1. The Math (68% Move)</div>
                            <div class="sniper-value put-color">Floor: $%.2f</div>
                            <div class="sniper-value call-color">Ceiling: $%.2f</div>
                            <div style="font-size:0.8em; color:gray; margin-top:5px;">Based on IV & Time</div>
                            </div>""" % (math_floor, math_ceil), unsafe_allow_html=True)
                            
                    with col_s1:
                        st.markdown("""<div class="sniper-box">
                            <div class="sniper-title">2. Price Action</div>
                            <div style="color:#00b09b;"><b>S1:</b> $%.2f <br><b>S2:</b> $%.2f</div>
                            <div style="color:#ff4b4b; margin-top:5px;"><b>R1:</b> $%.2f <br><b>R2:</b> $%.2f</div>
                            <div style="font-size:0.8em; color:gray; margin-top:5px;">Historical Bounces</div>
                            </div>""" % (s1, s2, r1, r2), unsafe_allow_html=True)
                            
                    with col_s2:
                        st.markdown("""<div class="sniper-box">
                            <div class="sniper-title">3. Volume Profile</div>
                            <div class="sniper-value neutral-color">POC: $%.2f</div>
                            <div style="font-size:0.8em; color:gray; margin-top:10px;">6-Mo Max Volume Node</div>
                            </div>""" % (poc_price), unsafe_allow_html=True)
                            
                    with col_s3:
                        st.markdown("""<div class="sniper-box">
                            <div class="sniper-title">4. Options Walls</div>
                            <div style="color:#00b09b; font-size:1.2em;"><b>Put Wall:</b> %s</div>
                            <div style="color:#ff4b4b; font-size:1.2em; margin-top:5px;"><b>Call Wall:</b> %s</div>
                            <div style="font-size:0.8em; color:gray; margin-top:5px;">Max Open Interest</div>
                            </div>""" % (put_wall_str, call_wall_str), unsafe_allow_html=True)
                    
                    st.write("---")
                    st.markdown("#### 🎯 Sniper Conclusion")
                    out_put, out_call = st.columns(2)
                    with out_put: st.info(f"**🟢 Put Seller (Bullish/Neutral):**\nThe math tells you it is statistically safe down to **${math_floor:.2f}**. However, structural buyers are sitting at S1 (**${s1:.2f}**). \n\n**Pro Move:** Look to sell the strike that is tucked safely underneath both the Math Floor *and* S1.")
                    with out_call: st.error(f"**🔴 Call Seller (Bearish/Neutral):**\nThe math tells you it is statistically safe up to **${math_ceil:.2f}**. However, structural sellers are sitting at R1 (**${r1:.2f}**). \n\n**Pro Move:** Look to sell the strike that is safely above both the Math Ceiling *and* R1.")

            except Exception as e:
                st.error(f"Calculation Error: {e}")

# --- TAB 3: THE OPPORTUNITY SCREENER (Unchanged) ---
with tab_screener:
    st.markdown("#### 🔎 Live Opportunity Screener (VRP Edge)")
    
    col_filt1, col_filt2 = st.columns(2)
    with col_filt1:
        strategy_target = st.selectbox("I want to find setups for:", ["Selling Puts (Oversold Stocks)", "Selling Calls (Overbought Stocks)"])
    with col_filt2:
        min_edge = st.slider("Minimum VRP Edge (+%)", min_value=0, max_value=25, value=5, step=1)
        
    if st.button("🚀 Run Edge Scan", use_container_width=True, type="primary", key="btn2"):
        with st.spinner("Calculating Implied vs Historical Volatility Edges..."):
            screener_results = []
            for ticker in WATCHLIST:
                try:
                    t_data = yf.Ticker(ticker)
                    df = t_data.history(period="2mo")
                    if len(df) < 30: continue
                    current_price = df['Close'].iloc[-1]
                    daily_returns = df['Close'].pct_change().dropna()
                    realized_vol = daily_returns.tail(30).std() * np.sqrt(252) * 100
                    beta = t_data.info.get('beta', 1.0) or 1.0
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

# --- TAB 4: LEDGER (Unchanged) ---
with tab_ledger:
    st.markdown("""
    <div class="creed-box">
        <div class="creed-title">🧠 The Quants Creed</div>
        <div class="creed-text"><b>1. Hope is not a strategy.</b> Cut your losses mechanically.<br><b>2. Watch the clock.</b> Beware of Market-on-Close (MOC) volatility and the notorious Friday Flush.</div>
    </div>
    """, unsafe_allow_html=True)
    
    edt = st.data_editor(st.session_state.journal.drop(columns=['temp_exp'], errors='ignore'), num_rows="dynamic", use_container_width=True, key="ledger_final")

st.markdown(f'<div class="footer-right">Last Synced to GitHub: {st.session_state.last_update}</div>', unsafe_allow_html=True)

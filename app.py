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
    
    .creed-box {
        background-color: rgba(128, 128, 128, 0.05); 
        border: 1px solid rgba(128, 128, 128, 0.2);
        border-left: 5px solid #2962FF; 
        border-radius: 8px;
        padding: 15px 20px;
        margin-bottom: 25px;
    }
    .creed-title { font-weight: 800; font-size: 1.1em; margin-bottom: 10px; color: #2962FF; letter-spacing: 0.5px; }
    .creed-text { font-size: 0.95em; line-height: 1.6; }
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
    except Exception as e:
        st.error(f"GitHub Sync Failed: {e}")

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
    except Exception as e:
        if "404" in str(e): return pd.DataFrame(columns=COLS)
        else:
            st.error(f"⚠️ Emergency Stop: Could not connect to GitHub. Error: {e}")
            st.stop()

if 'journal' not in st.session_state: 
    st.session_state.journal = load_journal()
    st.session_state.last_update = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

if 'current_vix' not in st.session_state:
    st.session_state.current_vix = 20.0

# Watchlist for the Screener
WATCHLIST = ["AAPL", "TSLA", "NVDA", "AMD", "META", "AMZN", "MSFT", "GOOGL", "NFLX", "JPM", "BAC", "DIS", "BA", "UBER", "COIN", "PLTR", "SMCI", "ARM"]

# --- 3. UI TABS ---
tab1, tab_screener, tab2 = st.tabs(["⚡ Macro & Safe Zones", "🔎 Live Screener", "📓 Lucky Ledger"])

# --- TAB 1: MACRO & IDEA GENERATION ---
with tab1:
    col_market, col_calc = st.columns(2, gap="large")
    
    with col_market:
        head_col, btn_col = st.columns([3, 1])
        with head_col: st.markdown("#### 🌍 Market Temperature")
        with btn_col: st.button("🔄 Refresh", use_container_width=True)
            
        st.caption("Live baseline metrics for the broader market.")
        
        try:
            def get_yf_metrics(symbol):
                t = yf.Ticker(symbol)
                df = t.history(period='5d')
                if len(df) >= 2:
                    prev = float(df['Close'].iloc[-2])
                    curr = float(df['Close'].iloc[-1])
                    return curr, ((curr - prev) / prev) * 100
                return 0.0, 0.0
            
            spy_px, spy_pct = get_yf_metrics("SPY")
            qqq_px, qqq_pct = get_yf_metrics("QQQ")
            vix_px, vix_pct = get_yf_metrics("^VIX")
            
            st.session_state.current_vix = vix_px if vix_px > 0 else 20.0
            
            m1, m2 = st.columns(2)
            m1.metric("S&P 500", f"${spy_px:,.2f}", f"{spy_pct:+.2f}%")
            m2.metric("Nasdaq", f"${qqq_px:,.2f}", f"{qqq_pct:+.2f}%")
            
            market_daily_expected_pct = st.session_state.current_vix / np.sqrt(252)
            
            m3, m4 = st.columns(2)
            m3.metric("Volatility (VIX)", f"{vix_px:,.2f}", f"{vix_pct:+.2f}%", delta_color="inverse")
            m4.metric("SPY 1-Day Exp. Move", f"± {market_daily_expected_pct:.2f}%", "Rule of 16 Baseline", delta_color="off")

        except Exception as e:
            st.error(f"Error fetching market data: {e}")

    with col_calc:
        st.markdown("#### 🛡️ Safe Zone Calculator")
        st.caption("Instantly calculates your mathematical floor and ceiling for any ticker.")
        
        c1, c2 = st.columns(2)
        calc_tk = c1.text_input("Ticker", value="TSLA", key="calc_tk").upper()
        calc_ex = c2.date_input("Target Expiry", datetime.now().date() + timedelta(days=7))
        
        if st.button("🧮 Calculate Safe Zones", type="primary", use_container_width=True):
            with st.spinner(f"Crunching quant math for {calc_tk}..."):
                try:
                    yf_tk = yf.Ticker(calc_tk)
                    hist_df = yf_tk.history(period='5d')
                    if hist_df.empty:
                        st.error("Invalid Ticker or No Data Found.")
                    else:
                        px = float(hist_df['Close'].iloc[-1])
                        beta = yf_tk.info.get('beta', 1.0) or 1.0
                        days_to_exp = max((calc_ex - datetime.now().date()).days, 1)
                        
                        stock_iv_proxy = st.session_state.current_vix * beta
                        exp_move_pct = (stock_iv_proxy / 100) * np.sqrt(days_to_exp / 365)
                        exp_move_dollar = px * exp_move_pct
                        
                        st.markdown(f"### **{calc_tk} Current Price: ${px:.2f}**")
                        st.write(f"**Beta:** {beta:.2f} | **Timeframe:** {days_to_exp} Days | **Expected Swing:** ± {exp_move_pct*100:.1f}% (± ${exp_move_dollar:.2f})")
                        
                        t1, t2 = st.columns(2)
                        with t1: st.info(f"🟢 **SAFE PUT FLOOR**\n# **${px - exp_move_dollar:.2f}**\n*Do not sell puts above this.*")
                        with t2: st.error(f"🔴 **SAFE CALL CEILING**\n# **${px + exp_move_dollar:.2f}**\n*Do not sell calls below this.*")
                except Exception as e:
                    st.error(f"Calculation Error: {e}")

# --- TAB 2: THE OPPORTUNITY SCREENER ---
with tab_screener:
    st.markdown("#### 🔎 Live Opportunity Screener")
    st.caption(f"Scanning the {len(WATCHLIST)} most liquid options tickers for mechanical setups.")
    
    col_filt1, col_filt2 = st.columns(2)
    with col_filt1:
        strategy_target = st.selectbox("I want to find setups for:", ["Selling Puts (Oversold Stocks)", "Selling Calls (Overbought Stocks)"])
    with col_filt2:
        min_vol = st.slider("Minimum Volatility (HV %)", min_value=10, max_value=100, value=35, step=5, help="Higher Volatility = Higher Option Premiums.")
        
    if st.button("🚀 Run Scan", use_container_width=True, type="primary"):
        with st.spinner("Analyzing price action, RSI, and Volatility..."):
            screener_results = []
            
            for ticker in WATCHLIST:
                try:
                    t_data = yf.Ticker(ticker)
                    df = t_data.history(period="2mo")
                    if len(df) < 30: continue
                    
                    current_price = df['Close'].iloc[-1]
                    
                    daily_returns = df['Close'].pct_change().dropna()
                    hv_30 = daily_returns.tail(30).std() * np.sqrt(252) * 100
                    
                    delta = df['Close'].diff()
                    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                    rs = gain / loss
                    rsi_14 = 100 - (100 / (1 + rs.iloc[-1]))
                    
                    sma_20 = df['Close'].rolling(window=20).mean().iloc[-1]
                    
                    screener_results.append({
                        "Ticker": ticker,
                        "Price": round(current_price, 2),
                        "RSI (14)": round(rsi_14, 1),
                        "Volatility %": round(hv_30, 1),
                        "vs 20-SMA": "Above" if current_price > sma_20 else "Below"
                    })
                except:
                    pass 
            
            res_df = pd.DataFrame(screener_results)
            
            if strategy_target == "Selling Puts (Oversold Stocks)":
                filtered_df = res_df[(res_df["RSI (14)"] < 45) & (res_df["Volatility %"] >= min_vol)]
                filtered_df = filtered_df.sort_values(by="RSI (14)", ascending=True) 
                st.success(f"Found {len(filtered_df)} beaten-down candidates with rich premiums.")
                
            else:
                filtered_df = res_df[(res_df["RSI (14)"] > 60) & (res_df["Volatility %"] >= min_vol)]
                filtered_df = filtered_df.sort_values(by="RSI (14)", ascending=False) 
                st.error(f"Found {len(filtered_df)} overbought candidates with rich premiums.")
                
            if not filtered_df.empty:
                # PRO FIX: Added strict "{:.1f}" formatting for the RSI column!
                display_df = filtered_df.style.format({
                    "Price": "${:.2f}",
                    "RSI (14)": "{:.1f}", 
                    "Volatility %": "{:.1f}%"
                })
                st.dataframe(display_df, use_container_width=True, hide_index=True)
                st.info("👉 **Next Step:** Take the top ticker from this list, plug it into the 'Safe Zone Calculator' on the first tab, and then execute the trade on your broker!")
            else:
                st.warning("No stocks met your strict criteria. The market might be chopping sideways. Protect your capital and wait for a better setup.")

# --- TAB 3: LEDGER ---
with tab2:
    st.markdown("""
    <div class="creed-box">
        <div class="creed-title">🧠 The Quants Creed</div>
        <div class="creed-text">
            <b>1. Hope is not a strategy.</b> Cut your losses mechanically.<br>
            <b>2. Watch the clock.</b> Beware of Market-on-Close (MOC) volatility and the notorious Friday Flush.
        </div>
    </div>
    """, unsafe_allow_html=True)

    df_j = st.session_state.journal
    realized_df = df_j[~df_j["Status"].astype(str).str.contains("Open", na=False)]
    total_realized = realized_df["Premium"].sum()
    total_closed = len(realized_df)
    wins = len(realized_df[realized_df["Status"].astype(str).str.contains("Win", na=False)])
    win_rate = (wins / total_closed * 100) if total_closed > 0 else 0.0
    active_df = df_j[df_j["Status"].astype(str).str.contains("Open", na=False)]
    active_count = len(active_df)
    capital_at_risk = (pd.to_numeric(active_df["Strike"]) * 100 * pd.to_numeric(active_df["Qty"])).sum()
    
    today = datetime.now().date()
    start_of_week = today - timedelta(days=today.weekday()) 
    end_of_week = start_of_week + timedelta(days=6) 
    
    df_j['temp_exp'] = pd.to_datetime(df_j['Expiry'], errors='coerce').dt.date
    this_week_df = df_j[(df_j['temp_exp'] >= start_of_week) & (df_j['temp_exp'] <= end_of_week)]
    weekly_profit = this_week_df["Premium"].sum()
    
    r1c1, r1c2 = st.columns(2)
    r1c1.metric("Total Realized 🤑", f"${total_realized:,.2f}", f"Win Rate: {win_rate:.1f}%", delta_color="off")
    r1c2.metric("Active Trades 📈", str(active_count), f"Capital at Risk: ${capital_at_risk:,.0f}", delta_color="off")
    
    with st.expander("➕ Log New Trade", expanded=True):
        with st.form("new_trade_form", clear_on_submit=True):
            l1, l2, l3, l4 = st.columns(4)
            _raw_tk = l1.text_input("Ticker", placeholder="e.g. AAPL")
            n_ex = l2.date_input("Expiry", datetime.now().date() + timedelta(days=7))
            n_ty = l3.selectbox("Type", ["Short Put", "Short Call"])
            n_qt = l4.number_input("Qty", value=1, min_value=1)
            l5, l6 = st.columns(2)
            n_st = l5.number_input("Strike", value=None, format="%.1f", placeholder="e.g. 150.5")
            n_op = l6.number_input("Open Price", value=None, format="%.2f", placeholder="e.g. 0.85")
            submitted = st.form_submit_button("🚀 Commit Trade", use_container_width=True, type="primary")
            
            if submitted:
                n_tk = _raw_tk.upper() if _raw_tk else None
                if n_tk and n_st is not None and n_op is not None:
                    comm = round(n_qt * 1.05, 2)
                    net = round((float(n_op) * 100 * n_qt) - comm, 2)
                    stat = "Expired (Win)" if n_ex < datetime.now().date() else "Open / Active"
                    new_row = pd.DataFrame([{"Date": str(datetime.now().date()), "Ticker": n_tk, "Type": n_ty, "Strike": round(n_st, 1), "Expiry": str(n_ex), "Open Price": round(float(n_op), 2), "Close Price": 0.0, "Qty": n_qt, "Commission": comm, "Premium": net, "Status": stat}])
                    st.session_state.journal = pd.concat([df_j.drop(columns=['temp_exp'], errors='ignore'), new_row], ignore_index=True)
                    save_journal(st.session_state.journal)
                    st.rerun()

    st.write("### Trade History")
    
    def refresh_calculations(current_df):
        for col in ["Strike", "Open Price", "Close Price", "Qty", "Commission"]:
            current_df[col] = pd.to_numeric(current_df[col], errors='coerce').fillna(0)
        def update_row(r):
            open_p, close_p = float(r["Open Price"]), float(r["Close Price"])
            p = round(((open_p - close_p) * 100 * int(r["Qty"])) - float(r["Commission"]), 2)
            try: ex_d = pd.to_datetime(r["Expiry"]).date()
            except: ex_d = datetime.now().date()
            
            if close_p > 0: s = "Closed (Loss)" if close_p > open_p else "Closed (Win)"
            elif ex_d < datetime.now().date(): s = "Expired (Win)"
            else: s = "Open / Active"
            return pd.Series([p, s])
        current_df[["Premium", "Status"]] = current_df.apply(update_row, axis=1)
        return sort_ledger(current_df)

    edt = st.data_editor(
        st.session_state.journal.drop(columns=['temp_exp'], errors='ignore'), 
        num_rows="dynamic", use_container_width=True, key="ledger_editor_final2",
        column_config={
            "Date": st.column_config.TextColumn("Date", help="YYYY-MM-DD"),
            "Strike": st.column_config.NumberColumn(format="%.2f"),
            "Open Price": st.column_config.NumberColumn(format="%.2f"),
            "Close Price": st.column_config.NumberColumn(format="%.2f"),
            "Commission": st.column_config.NumberColumn(format="$%.2f"),
            "Premium": st.column_config.NumberColumn(format="$%.2f")
        }
    )

    if not edt.equals(st.session_state.journal.drop(columns=['temp_exp'], errors='ignore')):
        updated_df = refresh_calculations(edt)
        st.session_state.journal = updated_df
        save_journal(updated_df)
        st.rerun()

st.markdown(f'<div class="footer-right">Last Synced to GitHub: {st.session_state.last_update}</div>', unsafe_allow_html=True)

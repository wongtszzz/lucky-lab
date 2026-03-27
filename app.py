import streamlit as st
import pandas as pd
import numpy as np
import io
import base64
import yfinance as yf
from datetime import datetime, timedelta
from alpaca.data.historical import OptionHistoricalDataClient, StockHistoricalDataClient
from alpaca.data.requests import OptionChainRequest, StockLatestQuoteRequest, StockSnapshotRequest, StockBarsRequest
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
</style>
""", unsafe_allow_html=True)

st.markdown("### 🧪 Lucky Quants Lab")
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

if 'journal' not in st.session_state or set(st.session_state.journal.columns) != set(COLS): 
    st.session_state.journal = load_journal()
    st.session_state.last_update = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# --- 3. UI TABS ---
tab1, tab2 = st.tabs(["🔍 Strategy Optimizer", "📓 Lucky Ledger"])

# Global variable to pass the market's expected move from left column to right column
market_daily_expected_pct = 0.0

# --- OPTIMIZER (50/50 Market & Strategy Split) ---
with tab1:
    col_market, col_opt = st.columns(2, gap="large")
    
    # --- LEFT SIDE: THE MARKET ORACLE (Expected Move) ---
    with col_market:
        head_col, btn_col = st.columns([3, 1])
        with head_col:
            st.markdown("#### 🔮 Market Oracle")
        with btn_col:
            st.button("🔄 Refresh", use_container_width=True)
            
        st.caption("Calculates tomorrow's expected ± % move based on real-time VIX.")
        
        try:
            def get_yf_close(symbol):
                t = yf.Ticker(symbol)
                df = t.history(period='5d')
                if not df.empty:
                    return float(df['Close'].iloc[-1])
                return 0.0
            
            spy_px = get_yf_close("SPY")
            vix_px = get_yf_close("^VIX")
            
            if spy_px == 0.0 or vix_px == 0.0:
                raise ValueError("Yahoo Timeout")
            
            # THE MATH: Rule of 16 (VIX / sqrt(252))
            market_daily_expected_pct = vix_px / np.sqrt(252)
            daily_expected_dollar = spy_px * (market_daily_expected_pct / 100)
            
            exp_high = spy_px + daily_expected_dollar
            exp_low = spy_px - daily_expected_dollar
            
            # Displaying the Oracle Data cleanly
            m1, m2 = st.columns(2)
            m1.metric("SPY Current Price", f"${spy_px:,.2f}")
            m2.metric("Tomorrow's Move", f"± {market_daily_expected_pct:.2f}%", f"± ${daily_expected_dollar:.2f}", delta_color="off")
            
            m3, m4 = st.columns(2)
            m3.metric("Expected High (Ceiling)", f"${exp_high:,.2f}", "Resistance", delta_color="normal")
            m4.metric("Expected Low (Floor)", f"${exp_low:,.2f}", "Support", delta_color="inverse")
            
            st.info(f"💡 **SPY Baseline:** The broader market is pricing in a **{market_daily_expected_pct:.2f}%** move for tomorrow.")

        except Exception as e:
            # Fallback using Alpaca
            st.caption("*(Yahoo Timeout - Auto-switched to Alpaca ETF Feed)*")
            try:
                req = StockLatestQuoteRequest(symbol_or_symbols=["SPY", "VIXY"], feed=DataFeed.IEX)
                quotes = stock_client.get_stock_latest_quote(req)
                
                spy_px = quotes["SPY"].ask_price if quotes["SPY"].ask_price > 0 else 0.0
                vixy_px = quotes["VIXY"].ask_price if quotes["VIXY"].ask_price > 0 else 0.0
                
                # We use VIXY as a proxy here if Yahoo fails
                proxy_vix = vixy_px * 1.5 
                market_daily_expected_pct = proxy_vix / np.sqrt(252)
                daily_expected_dollar = spy_px * (market_daily_expected_pct / 100)
                
                exp_high = spy_px + daily_expected_dollar
                exp_low = spy_px - daily_expected_dollar
                
                m1, m2 = st.columns(2)
                m1.metric("SPY Current Price", f"${spy_px:,.2f}")
                m2.metric("Tomorrow's Move (Est.)", f"± {market_daily_expected_pct:.2f}%", f"± ${daily_expected_dollar:.2f}", delta_color="off")
                
                m3, m4 = st.columns(2)
                m3.metric("Expected High", f"${exp_high:,.2f}", "Resistance")
                m4.metric("Expected Low", f"${exp_low:,.2f}", "Support", delta_color="inverse")
                
            except:
                st.warning("All market data feeds are currently down.")

    # --- RIGHT SIDE: OPTIONS CHAIN SCANNER ---
    with col_opt:
        st.markdown("#### 🎯 Options Chain Scanner")
        st.caption("Find the best premiums within ±10% of the current price.")
        
        c1, c2, c3 = st.columns(3)
        tk = c1.text_input("Ticker", value="TSM").upper()
        target_ex = c2.date_input("Target Expiry", datetime.now().date() + timedelta(days=30))
        opt_filter = c3.selectbox("Show", ["Puts Only", "Calls Only", "Both"])
        
        if st.button("🔬 Scan Chain", type="primary", use_container_width=True):
            with st.spinner(f"Scanning {tk} live chain and analyzing Beta..."):
                try:
                    # Fetch Latest Price
                    px_req = StockLatestQuoteRequest(symbol_or_symbols=tk, feed=DataFeed.IEX)
                    px = stock_client.get_stock_latest_quote(px_req)[tk].ask_price
                    
                    # PRO FIX: Fetch Beta using Yahoo Finance!
                    try:
                        beta = yf.Ticker(tk).info.get('beta', 1.0)
                        if beta is None: beta = 1.0
                    except:
                        beta = 1.0
                    
                    # Calculate Individual Stock Expected Move (Market Move * Beta)
                    stock_expected_pct = market_daily_expected_pct * beta
                    stock_expected_dollar = px * (stock_expected_pct / 100)
                    
                    # Calculate 30-Day Historical Volatility (HV)
                    end_dt = datetime.now()
                    start_dt = end_dt - timedelta(days=45) 
                    hv = 0.0
                    try:
                        bar_req = StockBarsRequest(symbol_or_symbols=tk, timeframe=TimeFrame.Day, start=start_dt, end=end_dt, feed=DataFeed.IEX)
                        bars = stock_client.get_stock_bars(bar_req)
                        if tk in bars.df.index.levels[0]:
                            closes = bars.df.loc[tk]['close']
                            daily_returns = closes.pct_change().dropna()
                            hv = daily_returns.std() * np.sqrt(252) * 100 
                    except: pass 
                    
                    # Fetch Option Chain
                    chain_req = OptionChainRequest(underlying_symbol=tk, expiration_date=target_ex, feed=OptionsFeed.INDICATIVE)
                    chain = opt_client.get_option_chain(chain_req)
                    
                    res = []
                    for s, d in chain.items():
                        stk_val = float(s[-8:])/1000
                        opt_type = "Put" if "P" in s else "Call"
                        
                        if opt_filter == "Puts Only" and opt_type == "Call": continue
                        if opt_filter == "Calls Only" and opt_type == "Put": continue
                        
                        if px * 0.90 <= stk_val <= px * 1.10:
                            
                            bid = d.latest_quote.bid_price if d.latest_quote else 0.0
                            ask = d.latest_quote.ask_price if d.latest_quote else 0.0
                            mid = (bid + ask) / 2 if (bid + ask) > 0 else 0.0
                            
                            delta = d.greeks.delta if d.greeks and d.greeks.delta is not None else 0.0
                            iv = d.implied_volatility if d.implied_volatility is not None else 0.0
                            roc = (mid / stk_val) * 100 if stk_val > 0 else 0.0
                            
                            res.append({
                                "Type": opt_type,
                                "Strike": stk_val,
                                "Delta": round(delta, 3),
                                "Mid Price": round(mid, 2),
                                "ROC %": round(roc, 2),
                                "IV %": round(iv * 100, 1)
                            })
                            
                    # Display the new individual stock forecasting metrics!
                    st.success(f"**{tk} Price:** ${px:.2f} | **Beta:** {beta:.2f} | **Tomorrow's Est. Move:** ±{stock_expected_pct:.2f}% (±${stock_expected_dollar:.2f})")
                    st.caption("🟢 **Highlighted Rows:** Delta < 15% AND Implied Volatility (IV) > 50%")
                    
                    if res:
                        df_res = pd.DataFrame(res).sort_values(by=["Type", "Strike"], ascending=[False, False])
                        
                        def highlight_golden_trades(row):
                            try:
                                is_golden = (0.0 < abs(float(row['Delta'])) < 0.15) and (float(row['IV %']) > 50.0)
                                if is_golden:
                                    return ['background-color: rgba(39, 174, 96, 0.4); font-weight: bold;'] * len(row)
                            except: pass
                            return [''] * len(row)
                            
                        styled_df = df_res.style.apply(highlight_golden_trades, axis=1).format({
                            "Mid Price": "${:.2f}"
                        })
                        
                        st.dataframe(styled_df, use_container_width=True, hide_index=True)
                    else:
                        st.warning(f"No options found for {tk} expiring on {target_ex}.")
                except Exception as e:
                    st.error(f"Error fetching data: {e}")

# --- LEDGER (100% UNTOUCHED) ---
with tab2:
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
    
    if not this_week_df.empty:
        best_row = this_week_df.loc[this_week_df["Premium"].idxmax()]
        worst_row = this_week_df.loc[this_week_df["Premium"].idxmin()]
        best_str = f"{best_row['Ticker']} (${best_row['Premium']:.0f})"
        worst_str = f"Worst: {worst_row['Ticker']} (${worst_row['Premium']:.0f})"
    else:
        best_str, worst_str = "No trades", "No trades"
    
    r1c1, r1c2 = st.columns(2)
    r1c1.metric("Total Realized 🤑", f"${total_realized:,.2f}", f"Win Rate: {win_rate:.1f}%", delta_color="off")
    r1c2.metric("Active Trades 📈", str(active_count), f"Capital at Risk: ${capital_at_risk:,.0f}", delta_color="off")
    
    r2c1, r2c2 = st.columns(2)
    r2c1.metric("This Week's P&L (Mon-Sun) 📅", f"${weekly_profit:,.2f}", "Based on Expiry Date", delta_color="off")
    r2c2.metric("Top Trade (This Week) 🏆", best_str, worst_str, delta_color="off")

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
                else:
                    st.warning("⚠️ Please fill in the Ticker, Strike, and Open Price before committing.")

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
        num_rows="dynamic", 
        use_container_width=True, 
        key="ledger_editor_v22",
        column_config={
            "Date": st.column_config.TextColumn("Date", help="YYYY-MM-DD"),
            "Strike": st.column_config.NumberColumn(format="%.1f"),
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

import streamlit as st
import pandas as pd
import numpy as np
import io
import base64
from scipy.stats import norm
from datetime import datetime, timedelta
from alpaca.data.historical import OptionHistoricalDataClient, StockHistoricalDataClient
from alpaca.data.requests import OptionChainRequest, StockLatestQuoteRequest
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
    """Custom Multi-Level Sort: 1. Date (Newest first) -> 2. Status (Open -> Win -> Loss)"""
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
        # Ensure it is perfectly sorted before saving to GitHub
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

# --- 3. UI TABS ---
tab1, tab2 = st.tabs(["🔍 Strategy Optimizer", "📓 Lucky Ledger"])

# --- OPTIMIZER ---
with tab1:
    st.write("Calculates short put probabilities using Black-Scholes.")
    c1, c2, c3 = st.columns(3)
    tk = c1.text_input("Ticker", value="TSM").upper()
    sf = c2.slider("Safety %", 70, 99, 90)
    iv_input = c3.slider("IV %", 10, 200, 30) 
    
    if st.button("🔬 Run Analysis", type="primary"):
        with st.spinner("Fetching data..."):
            try:
                px = stock_client.get_stock_latest_quote(StockLatestQuoteRequest(symbol_or_symbols=tk, feed=DataFeed.IEX))[tk].ask_price
                exp = datetime.now() + timedelta(days=(4-datetime.now().weekday()+7)%7 or 7)
                chain = opt_client.get_option_chain(OptionChainRequest(underlying_symbol=tk, expiration_date=exp.date(), feed=OptionsFeed.INDICATIVE))
                res = []
                iv_decimal = iv_input / 100.0
                for s, d in chain.items():
                    stk_val = float(s[-8:])/1000
                    if "P" in s and stk_val < px:
                        d2 = (np.log(px/stk_val) + (0.04 - 0.5 * iv_decimal**2)*(7/365)) / (iv_decimal * np.sqrt(7/365))
                        prob = norm.cdf(d2) * 100
                        if prob >= sf:
                            mid = (d.bid_price + d.ask_price) / 2
                            res.append({"Strike": stk_val, "Safety %": round(prob, 1), "Premium": round(mid, 2), "Est. Income": round(mid*100, 2)})
                st.success(f"**{tk} Price:** ${px:.2f} | **Expiry:** {exp.date()}")
                if res: st.dataframe(pd.DataFrame(res).sort_values("Strike", ascending=False), use_container_width=True)
                else: st.warning("No matches.")
            except Exception as e: st.error(f"Error: {e}")

# --- LEDGER ---
with tab2:
    df_j = st.session_state.journal
    
    # --- METRIC CALCULATIONS ---
    # 1. Realized, Active, and Pro Metrics
    realized_df = df_j[~df_j["Status"].astype(str).str.contains("Open", na=False)]
    total_realized = realized_df["Premium"].sum()
    
    # Calculate Win Rate
    total_closed = len(realized_df)
    wins = len(realized_df[realized_df["Status"].astype(str).str.contains("Win", na=False)])
    win_rate = (wins / total_closed * 100) if total_closed > 0 else 0.0
    
    # Active Trades and Collateral Risk
    active_df = df_j[df_j["Status"].astype(str).str.contains("Open", na=False)]
    active_count = len(active_df)
    capital_at_risk = (pd.to_numeric(active_df["Strike"]) * 100 * pd.to_numeric(active_df["Qty"])).sum()
    
    # 2. Weekly Metrics (Last 7 Days)
    df_j['temp_dt'] = pd.to_datetime(df_j['Date'], errors='coerce')
    week_ago = datetime.now() - timedelta(days=7)
    weekly_df = df_j[df_j['temp_dt'] >= week_ago]
    weekly_profit = weekly_df["Premium"].sum()
    
    if not weekly_df.empty:
        best_row = weekly_df.loc[weekly_df["Premium"].idxmax()]
        worst_row = weekly_df.loc[weekly_df["Premium"].idxmin()]
        best_str = f"{best_row['Ticker']} (+${best_row['Premium']:.0f})"
        worst_str = f"Worst: {worst_row['Ticker']} (${worst_row['Premium']:.0f})"
    else:
        best_str, worst_str = "No trades", "No trades"
    
    # --- UI: 2x2 DASHBOARD ---
    r1c1, r1c2 = st.columns(2)
    r1c1.metric("Total Realized 🤑", f"${total_realized:,.2f}", f"Win Rate: {win_rate:.1f}%", delta_color="off")
    r1c2.metric("Active Trades 📈", str(active_count), f"Capital at Risk: ${capital_at_risk:,.0f}", delta_color="off")
    
    r2c1, r2c2 = st.columns(2)
    r2c1.metric("Weekly Profit (7d) 📅", f"${weekly_profit:,.2f}", "Includes Realized + Unrealized", delta_color="off")
    r2c2.metric("Top Trade (7d) 🏆", best_str, worst_str, delta_color="off")

    with st.expander("➕ Log New Trade"):
        # The Date Input is gone!
        l1, l2, l3, l4 = st.columns(4)
        n_tk = l1.text_input("Ticker", key="new_tk").upper()
        n_ty = l2.selectbox("Type", ["Short Put", "Short Call"])
        n_qt = l3.number_input("Qty", value=1, min_value=1)
        n_ex = l4.date_input("Expiry", datetime.now().date() + timedelta(days=7))
        
        l5, l6 = st.columns(2)
        n_st = l5.number_input("Strike", value=0.0, format="%.1f")
        n_op = l6.number_input("Open Price", value=0.0, format="%.2f")
        
        if st.button("🚀 Commit Trade", use_container_width=True, type="primary"):
            if n_tk:
                comm = round(n_qt * 1.05, 2)
                net = round((float(n_op) * 100 * n_qt) - comm, 2)
                stat = "Expired (Win)" if n_ex < datetime.now().date() else "Open / Active"
                
                # Auto-injects today's date dynamically
                new_row = pd.DataFrame([{"Date": str(datetime.now().date()), "Ticker": n_tk, "Type": n_ty, "Strike": round(n_st, 1), "Expiry": str(n_ex), "Open Price": round(float(n_op), 2), "Close Price": 0.0, "Qty": n_qt, "Commission": comm, "Premium": net, "Status": stat}])
                
                st.session_state.journal = pd.concat([df_j.drop(columns=['temp_dt'], errors='ignore'), new_row], ignore_index=True)
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
        
        # Apply custom sort immediately so the UI table snaps into place
        return sort_ledger(current_df)

    # Note: 'Date' is now visible in the table so you can edit it if you forgot to log a trade yesterday
    edt = st.data_editor(
        st.session_state.journal.drop(columns=['temp_dt'], errors='ignore'), 
        num_rows="dynamic", 
        use_container_width=True, 
        key="ledger_editor_v6",
        column_config={
            "Date": st.column_config.TextColumn("Date", help="YYYY-MM-DD"),
            "Strike": st.column_config.NumberColumn(format="%.1f"),
            "Open Price": st.column_config.NumberColumn(format="%.2f"),
            "Close Price": st.column_config.NumberColumn(format="%.2f"),
            "Commission": st.column_config.NumberColumn(format="$%.2f"),
            "Premium": st.column_config.NumberColumn(format="$%.2f")
        }
    )

    if not edt.equals(st.session_state.journal.drop(columns=['temp_dt'], errors='ignore')):
        updated_df = refresh_calculations(edt)
        st.session_state.journal = updated_df
        save_journal(updated_df)
        st.rerun()

st.markdown(f'<div class="footer-right">Last Synced to GitHub: {st.session_state.last_update}</div>', unsafe_allow_html=True)

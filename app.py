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
    [data-testid="stMetric"] {
        background-color: transparent; 
        padding: 15px; 
        border-radius: 10px; 
        border: 1px solid rgba(128, 128, 128, 0.3);
    }
    .footer-right { position: fixed; bottom: 10px; right: 10px; color: gray; font-size: 0.8em; font-weight: bold; z-index: 1000; }
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
    st.error(f"Missing or incorrect secrets! Please check your Streamlit Secrets. Error: {e}")
    st.stop()

# --- 2. LOGIC & DATA ENGINE (GitHub Backend) ---
FILE_PATH = "lucky_ledger.csv"
COLS = ["Ticker", "Type", "Strike", "Expiry", "Open Price", "Close Price", "Qty", "Commission", "Premium", "Status"]

def calc_ibkr_commission(qty):
    try: return round(float(qty) * 1.05, 2)
    except: return 1.05

def save_journal(df):
    """Pushes the DataFrame directly to GitHub as a CSV"""
    try:
        csv_content = df[COLS].to_csv(index=False)
        commit_message = f"Ledger update: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        try:
            contents = repo.get_contents(FILE_PATH)
            repo.update_file(contents.path, commit_message, csv_content, contents.sha)
        except:
            repo.create_file(FILE_PATH, "Initial ledger creation", csv_content)
            
        st.session_state.last_update = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    except Exception as e:
        st.error(f"Failed to save to GitHub: {e}")

def load_journal():
    """Pulls the CSV file directly from the GitHub repo"""
    try:
        contents = repo.get_contents(FILE_PATH)
        decoded_content = base64.b64decode(contents.content).decode('utf-8')
        df = pd.read_csv(io.StringIO(decoded_content))
        
        for c in COLS:
            if c not in df.columns:
                df[c] = 0.0 if c in ["Open Price", "Close Price", "Premium", "Commission"] else (1 if c == "Qty" else "Unknown")
        
        df['exp_dt'] = pd.to_datetime(df['Expiry'], errors='coerce')
        df['is_open'] = df['Status'].astype(str).str.contains("Open", case=False, na=False)
        df = df.sort_values(by=['is_open', 'exp_dt'], ascending=[False, False])
        return df[COLS].reset_index(drop=True)
    except:
        return pd.DataFrame(columns=COLS)

if 'journal' not in st.session_state: 
    st.session_state.journal = load_journal()
    st.session_state.last_update = datetime.now().strftime("%Y-%m-%d")

# --- 3. UI TABS ---
tab1, tab2 = st.tabs(["🔍 Strategy Optimizer", "📓 Lucky Ledger"])

# --- OPTIMIZER ---
with tab1:
    st.write("Calculates short put probabilities using Black-Scholes.")
    c1, c2, c3 = st.columns([1, 1, 1])
    tk = c1.text_input("Ticker", value="TSM").upper()
    sf = c2.slider("Safety % Target", 70, 99, 90)
    
    # FIXED: Replaced hardcoded 30% IV with a user input slider
    iv_input = c3.slider("Est. Implied Volatility (IV) %", 10, 200, 30) 
    
    if st.button("🔬 Run Analysis", type="primary"):
        with st.spinner("Fetching data from Alpaca..."):
            try:
                px = stock_client.get_stock_latest_quote(StockLatestQuoteRequest(symbol_or_symbols=tk, feed=DataFeed.IEX))[tk].ask_price
                exp = datetime.now() + timedelta(days=(4-datetime.now().weekday()+7)%7 or 7)
                chain = opt_client.get_option_chain(OptionChainRequest(underlying_symbol=tk, expiration_date=exp.date(), feed=OptionsFeed.INDICATIVE))
                
                res = []
                iv_decimal = iv_input / 100.0
                
                for s, d in chain.items():
                    stk_val = float(s[-8:])/1000
                    if "P" in s and stk_val < px:
                        # Black-Scholes Math using user IV
                        d2 = (np.log(px/stk_val) + (0.04 - 0.5 * iv_decimal**2)*(7/365)) / (iv_decimal * np.sqrt(7/365))
                        prob = norm.cdf(d2) * 100
                        
                        if prob >= sf:
                            mid = (d.bid_price + d.ask_price) / 2
                            res.append({"Strike": stk_val, "Safety %": round(prob, 1), "Premium": round(mid, 2), "Est. Income": round(mid*100, 2)})
                
                st.success(f"**{tk} Current Price:** ${px:.2f} | **Target Expiry:** {exp.date()}")
                if res:
                    st.dataframe(pd.DataFrame(res).sort_values("Strike", ascending=False), use_container_width=True)
                else:
                    st.warning("No options found meeting your safety criteria. Try lowering the Safety % or increasing IV.")
            except Exception as e: 
                st.error(f"API Error: {e}")

# --- LEDGER ---
with tab2:
    df_j = st.session_state.journal
    total_prem = df_j["Premium"].sum()
    active_count = len(df_j[df_j["Status"].astype(str).str.contains("Open", na=False)])
    
    m1, m2 = st.columns(2)
    m1.metric("**Total Premium** 🤑", f"${total_prem:,.2f} (~HKD {(total_prem*7.8):,.2f})")
    m2.metric("**Active Trades** 📈", active_count)

    with st.expander("➕ Log New Trade"):
        l1, l2, l3, l4 = st.columns(4)
        n_tk = l1.text_input("Ticker", value="", placeholder="e.g. AAPL").upper()
        n_ty = l2.selectbox("Type", ["Short Put", "Short Call"])
        n_qt = l3.number_input("Qty", value=1, min_value=1)
        n_ex = l4.date_input("Expiry", datetime.now().date())
        
        l5, l6 = st.columns(2)
        n_st = l5.number_input("Strike", value=None, placeholder="150.5", step=0.5, format="%.1f")
        n_op = l6.number_input("Open Price", value=None, placeholder="0.59", step=0.01, format="%.2f")
        
        if st.button("🚀 Commit Trade", use_container_width=True, type="primary"):
            if n_st is not None and n_op is not None and n_tk != "":
                comm = calc_ibkr_commission(n_qt)
                net = round((float(n_op) * 100 * n_qt) - comm, 2)
                stat = "Expired (Win)" if n_ex < datetime.now().date() else "Open / Running"
                
                new_row = pd.DataFrame([{"Ticker": n_tk, "Type": n_ty, "Strike": round(n_st, 1), "Expiry": str(n_ex), "Open Price": round(float(n_op), 2), "Close Price": 0.0, "Qty": n_qt, "Commission": comm, "Premium": net, "Status": stat}])
                st.session_state.journal = pd.concat([df_j, new_row], ignore_index=True)
                save_journal(st.session_state.journal)
                st.rerun()

    st.write("### Trade History")
    edt = st.data_editor(
        st.session_state.journal, 
        num_rows="dynamic", 
        use_container_width=True, 
        column_config={
            "Strike": st.column_config.NumberColumn(format="%.1f"),
            "Open Price": st.column_config.NumberColumn(format="%.2f"),
            "Close Price": st.column_config.NumberColumn(format="%.2f"),
            "Commission": st.column_config.NumberColumn(format="$%.2f"),
            "Premium": st.column_config.NumberColumn(format="$%.2f")
        }
    )

    def refresh_calculations(current_df):
        current_df["Strike"] = pd.to_numeric(current_df["Strike"], errors='coerce').fillna(0).round(1)
        current_df["Open Price"] = pd.to_numeric(current_df["Open Price"], errors='coerce').fillna(0).round(2)
        current_df["Close Price"] = pd.to_numeric(current_df["Close Price"], errors='coerce').fillna(0).round(2)
        current_df["Qty"] = pd.to_numeric(current_df["Qty"], errors='coerce').fillna(1)
        current_df["Commission"] = current_df["Qty"].apply(calc_ibkr_commission)
        
        def update_row(r):
            open_p, close_p, qty, comm = float(r["Open Price"]), float(r["Close Price"]), int(r["Qty"]), float(r["Commission"])
            p = round(((open_p - close_p) * 100 * qty) - comm, 2)
            try: ex_d = datetime.strptime(str(r["Expiry"]), "%Y-%m-%d").date()
            except: ex_d = datetime.now().date()
            
            if close_p > 0: s = "Closed"
            else: s = "Expired (Win)" if ex_d < datetime.now().date() else "Open / Running"
            return pd.Series([p, s])
        
        current_df[["Premium", "Status"]] = current_df.apply(update_row, axis=1)
        return current_df

    if not edt.equals(st.session_state.journal):
        st.session_state.journal = refresh_calculations(edt)
        save_journal(st.session_state.journal)
        st.rerun()

# --- TIMESTAMP FOOTER ---
st.markdown(f'<div class="footer-right">Last Synced to GitHub: {st.session_state.last_update}</div>', unsafe_allow_html=True)

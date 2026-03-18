import streamlit as st
import pandas as pd
import numpy as np
import os
import shutil
from scipy.stats import norm
from datetime import datetime, timedelta
from alpaca.data.historical import OptionHistoricalDataClient, StockHistoricalDataClient
from alpaca.data.requests import OptionChainRequest, StockLatestQuoteRequest
from alpaca.data.enums import OptionsFeed, DataFeed

# --- 1. CONFIG & STYLING ---
st.set_page_config(page_title="Lucky Quants Lab", page_icon="🧪", layout="wide")

st.markdown("""
    <style>
    .block-container {padding-top: 1rem; padding-bottom: 0rem;}
    .stMetric { background-color: #f0f2f6; padding: 5px 15px; border-radius: 10px; border: 1px solid #dcdcdc; }
    div[data-testid="stExpander"] { border: 1px solid #e6e9ef; border-radius: 10px; }
    hr {margin: 0.5em 0px;}
    .footer { position: fixed; bottom: 10px; right: 10px; color: gray; font-size: 0.7em; }
    </style>
    """, unsafe_allow_html=True)

h1, h2 = st.columns([2, 1])
h1.markdown("### 🧪 Lucky Quants Lab")
if 'last_refresh' not in st.session_state: 
    st.session_state.last_refresh = datetime.now().strftime("%H:%M:%S")
h2.markdown(f"<p style='text-align: right; color: gray; font-size: 0.8em; padding-top: 15px;'>Refreshed: {st.session_state.last_refresh}</p>", unsafe_allow_html=True)
st.divider()

try:
    API_KEY = st.secrets["ALPACA_KEY"]
    SECRET_KEY = st.secrets["ALPACA_SECRET"]
    opt_client = OptionHistoricalDataClient(API_KEY, SECRET_KEY)
    stock_client = StockHistoricalDataClient(API_KEY, SECRET_KEY)
except:
    st.error("Alpaca Keys Missing.")
    st.stop()

# --- 2. PERMANENT STORAGE & AUTO-RESTORE LOGIC ---
DB_FILE = "lucky_ledger.csv"
BACKUP_FILE = "lucky_ledger_backup.csv"

def save_data(df):
    df.to_csv(DB_FILE, index=False)
    shutil.copy2(DB_FILE, BACKUP_FILE)
    st.session_state.last_backup = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def apply_custom_sort(df):
    if df.empty: return df
    df = df.copy()
    df['Expiry_dt'] = pd.to_datetime(df['Expiry'], errors='coerce')
    df['is_open'] = df['Status'].astype(str).str.contains("Open", case=False, na=False)
    df = df.sort_values(by=['is_open', 'Expiry_dt'], ascending=[False, False])
    return df.drop(columns=['Expiry_dt', 'is_open'])

def load_data():
    cols = ["Ticker", "Type", "Strike", "Expiry", "Open Price", "Close Price", "Qty", "Premium", "Status"]
    if not os.path.exists(DB_FILE) and os.path.exists(BACKUP_FILE):
        shutil.copy2(BACKUP_FILE, DB_FILE)
    if os.path.exists(DB_FILE):
        try:
            df = pd.read_csv(DB_FILE)
            rename_map = {"Total Premium Collected": "Premium", "Premium (Total)": "Premium", "Premium (total)": "Premium"}
            df = df.rename(columns=rename_map)
            for c in cols:
                if c not in df.columns:
                    df[c] = 0.0 if c in ["Open Price", "Close Price", "Premium"] else (1 if c == "Qty" else "Unknown")
            if 'last_backup' not in st.session_state:
                st.session_state.last_backup = datetime.fromtimestamp(os.path.getmtime(DB_FILE)).strftime("%Y-%m-%d %H:%M:%S")
            return apply_custom_sort(df[cols])
        except:
            if os.path.exists(BACKUP_FILE):
                shutil.copy2(BACKUP_FILE, DB_FILE)
                return load_data()
    return pd.DataFrame(columns=cols)

if 'journal_data' not in st.session_state:
    st.session_state.journal_data = load_data()
if 'last_backup' not in st.session_state:
    st.session_state.last_backup = "No backup yet"

# --- 3. TABS ---
tab1, tab2 = st.tabs(["🔍 Strategy Optimizer", "📓 Lucky Ledger"])

# --- TAB 1: STRATEGY OPTIMIZER ---
with tab1:
    c1, c2 = st.columns([1, 2])
    t_scan = c1.text_input("Ticker", value="TSM", key="opt_tk_r3").upper()
    safety_target = c2.slider("Safety %", 70, 99, 90, key="opt_sf_r3")
    if st.button("🔬 Run Analysis", key="opt_btn_r3"):
        with st.spinner("Analyzing..."):
            try:
                price_data = stock_client.get_stock_latest_quote(StockLatestQuoteRequest(symbol_or_symbols=t_scan, feed=DataFeed.IEX))
                curr_price = price_data[t_scan].ask_price
                expiry = datetime.now() + timedelta(days=(4 - datetime.now().weekday() + 7) % 7 or 7)
                chain = opt_client.get_option_chain(OptionChainRequest(underlying_symbol=t_scan, expiration_date=expiry.date(), feed=OptionsFeed.INDICATIVE))
                results = []
                for sym, data in chain.items():
                    strike_val = float(sym[-8:]) / 1000
                    if "P" in sym and strike_val < curr_price:
                        iv, t_years = 0.30, 7/365
                        d2 = (np.log(curr_price/strike_val) + (0.04 - 0.5*iv**2)*t_years) / (iv*np.sqrt(t_years))
                        prob_otm = norm.cdf(d2) * 100
                        if prob_otm >= safety_target:
                            mid = (data.bid_price + data.ask_price) / 2
                            results.append({"Strike": strike_val, "Safety %": round(prob_otm, 1), "Premium": round(mid, 2), "Est. Income": round(mid * 100, 2)})
                st.write(f"**{t_scan} Price:** ${curr_price:.2f}")
                st.dataframe(pd.DataFrame(results).sort_values("Strike", ascending=False), use_container_width=True)
            except Exception as e: st.error(f"Error: {e}")

# --- TAB 2: LUCKY LEDGER ---
with tab2:
    # Summary Metrics
    raw_val = pd.to_numeric(st.session_state.journal_data["Premium"], errors='coerce').fillna(0).sum()
    active_count = len(st.session_state.journal_data[st.session_state.journal_data["Status"].astype(str).str.contains("Open", na=False)])
    
    m1, m2 = st.columns(2)
    m1.metric(label="**Total Premium Collected** 🤑", value=f"{int(round(raw_val)):,} (~HKD {int(round(raw_val * 7.8)):,})")
    m2.metric(label="**Active Trades** 📈", value=active_count)

    with st.expander("➕ Log New Trade", expanded=True):
        l1, l2, l3, l4 = st.columns(4)
        t_log = l1.text_input("Ticker", value="TSM", key="log_tk_r3").upper()
        type_log = l2.selectbox("Type", ["Short Put", "Short Call"], key="log_ty_r3")
        qty_log = l3.number_input("Qty", min_value=1, value=1, key="log_q_r3")
        exp_log = l4.date_input("Expiry", value=datetime.now().date(), key="log_ex_r3")
        
        l5, l6 = st.columns(2)
        stk_log = l5.number_input("Strike", value=None, step=0.5, format="%g", key="log_st_r3")
        op_log = l6.number_input("Open Price (Sell)", value=None, step=0.01, format="%.2f", key="log_op_r3")
        
        if st.button("🚀 Commit Trade", use_container_width=True, key="log_cmt_r3"):
            if stk_log and op_log is not None:
                net = round((float(op_log) * 100 * qty_log) - max(1.05, 0.70 * qty_log), 2)
                today = datetime.now().date()
                status = "Expired (Win)" if exp_log < today else "Open / Running"
                
                new_row = {"Ticker": t_log, "Type": type_log, "Strike": stk_log, "Expiry": exp_log.strftime("%Y-%m-%d"),
                           "Open Price": op_log, "Close Price": 0.00, "Qty": qty_log, "Premium": net, "Status": status}
                st.session_state.journal_data = pd.concat([st.session_state.journal_data, pd.DataFrame([new_row])], ignore_index=True)
                st.session_state.journal_data = apply_custom_sort(st.session_state.journal_data)
                save_data(st.session_state.journal_data)
                st.rerun()

    st.write("### History")
    edited_df = st.data_editor(st.session_state.journal_data, num_rows="dynamic", use_container_width=True, key="editor_r3")
    
    if not edited_df.equals(st.session_state.journal_data):
        df = edited_df.copy()
        df["Open Price"] = pd.to_numeric(df["Open Price"], errors='coerce').fillna(0)
        df["Close Price"] = pd.to_numeric(df["Close Price"], errors='coerce').fillna(0)
        df["Qty"] = pd.to_numeric(df["Qty"], errors='coerce').fillna(1)
        today = datetime.now().date()
        
        def refresh_row(r):
            p = round(((r["Open Price"] - r["Close Price"]) * 100 * r["Qty"]) - max(1.05, 0.70 * r["Qty"]), 2)
            try: exp_d = datetime.strptime(str(r["Expiry"]), "%Y-%m-%d").date()
            except: exp_d = today
            if r["Close Price"] > 0: s = "Closed"
            elif exp_d < today: s = "Expired (Win)"
            else: s = "Open / Running"
            return pd.Series([p, s])
            
        df[["Premium", "Status"]] = df.apply(refresh_row, axis=1)
        st.session_state.journal_data = apply_custom_sort(df)
        save_data(st.session_state.journal_data)
        st.rerun()

    if st.button("🔄 Recalculate Everything", key="recalc_r3"):
        st.rerun()

# --- FOOTER TIMESTAMP ---
st.markdown(f'<div class="footer">Last Backup: {st.session_state.last_backup}</div>', unsafe_allow_html=True)

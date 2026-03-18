import streamlit as st
import pandas as pd
import numpy as np
import os
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
    st.error("Alpaca Keys Missing in Secrets.")
    st.stop()

# --- 2. PERMANENT STORAGE & SORTING ---
DB_FILE = "lucky_ledger.csv"

def save_data(df):
    df.to_csv(DB_FILE, index=False)

def apply_custom_sort(df):
    """Tier 1: Open trades (Furthest expiry first). Tier 2: Others (Recent expiry first)."""
    if df.empty: return df
    df = df.copy()
    df['Expiry_dt'] = pd.to_datetime(df['Expiry'], errors='coerce')
    df['is_open'] = df['Status'] == "Open / Running"
    
    # Sort by is_open (True first), then by Expiry_dt
    # For open trades, we want furthest first; for closed, we want most recent first.
    # To keep it simple and consistent: Open at top, then descending by date.
    df = df.sort_values(by=['is_open', 'Expiry_dt'], ascending=[False, False])
    return df.drop(columns=['Expiry_dt', 'is_open'])

def load_data():
    cols = ["Ticker", "Type", "Strike", "Expiry", "Open Price", "Close Price", "Qty", "Premium", "Status"]
    if os.path.exists(DB_FILE):
        try:
            df = pd.read_csv(DB_FILE)
            # Migration handling
            if "Total Premium Collected" in df.columns:
                df = df.rename(columns={"Total Premium Collected": "Premium"})
            for c in cols:
                if c not in df.columns:
                    df[c] = 0.0 if c in ["Open Price", "Close Price", "Premium"] else (1 if c == "Qty" else "")
            return apply_custom_sort(df[cols])
        except: pass
    return pd.DataFrame(columns=cols)

if 'journal_data' not in st.session_state:
    st.session_state.journal_data = load_data()

# --- 3. TABS ---
tab1, tab2 = st.tabs(["🔍 Strategy Optimizer", "📓 Lucky Ledger"])

# --- TAB 1: STRATEGY OPTIMIZER ---
with tab1:
    c1, c2 = st.columns([1, 2])
    t_scan = c1.text_input("Ticker", value="TSM", key="opt_tk_final_v2").upper()
    safety_target = c2.slider("Safety %", 70, 99, 90, key="opt_sf_final_v2")
    if st.button("🔬 Run Analysis", key="opt_btn_final_v2"):
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
    # Summary Metric
    raw_val = pd.to_numeric(st.session_state.journal_data["Premium"], errors='coerce').fillna(0).sum()
    st.metric(label="**Total Premium Collected** 🤑", value=f"{int(round(raw_val)):,} (~HKD {int(round(raw_val * 7.8)):,})")

    with st.expander("➕ Log New Trade", expanded=True):
        l1, l2, l3, l4 = st.columns(4)
        t_log = l1.text_input("Ticker", value="TSM", key="log_tk_final_v2").upper()
        type_log = l2.selectbox("Type", ["Short Put", "Short Call"], key="log_ty_final_v2")
        qty_log = l3.number_input("Qty", min_value=1, value=1, key="log_q_final_v2")
        exp_log = l4.date_input("Expiry", value=datetime.now().date(), key="log_ex_final_v2")
        
        l5, l6, l7 = st.columns(3)
        stk_log = l5.number_input("Strike", value=None, step=0.5, format="%g", key="log_st_final_v2")
        op_log = l6.number_input("Open Price (Sell)", value=None, step=0.01, format="%.2f", key="log_op_final_v2")
        cl_log = l7.number_input("Close Price (Buy Back)", value=0.00, step=0.01, format="%.2f", key="log_cl_final_v2")
        
        if st.button("🚀 Commit Trade", use_container_width=True, key="log_cmt_final_v2"):
            if stk_log and op_log is not None:
                net = round(((float(op_log) - float(cl_log)) * 100 * qty_log) - max(1.05, 0.70 * qty_log), 2)
                today = datetime.now().date()
                if cl_log > 0: status = "Closed"
                elif exp_log < today: status = "Expired (Win)"
                else: status = "Open / Running"
                
                new_row = {
                    "Ticker": t_log, "Type": type_log, "Strike": stk_log, "Expiry": exp_log.strftime("%Y-%m-%d"),
                    "Open Price": op_log, "Close Price": cl_log, "Qty": qty_log, "Premium": net, "Status": status
                }
                st.session_state.journal_data = pd.concat([st.session_state.journal_data, pd.DataFrame([new_row])], ignore_index=True)
                st.session_state.journal_data = apply_custom_sort(st.session_state.journal_data)
                save_data(st.session_state.journal_data)
                st.rerun()

    st.write("### History")
    edited_df = st.data_editor(st.session_state.journal_data, num_rows="dynamic", use_container_width=True, key="editor_final_v2")
    
    if not edited_df.equals(st.session_state.journal_data):
        st.session_state.journal_data = edited_df
        save_data(edited_df)

    if st.button("🔄 Recalculate Everything", key="recalc_final_v2"):
        df = st.session_state.journal_data.copy()
        df["Open Price"] = pd.to_numeric(df["Open Price"], errors='coerce').fillna(0)
        df["Close Price"] = pd.to_numeric(df["Close Price"], errors='coerce').fillna(0)
        df["Qty"] = pd.to_numeric(df["Qty"], errors='coerce').fillna(1)
        
        today = datetime.now().date()
        def up_row(r):
            p = round(((r["Open Price"] - r["Close Price"]) * 100 * r["Qty"]) - max(1.05, 0.70 * r["Qty"]), 2)
            try: exp_d = datetime.strptime(str(r["Expiry"]), "%Y-%m-%d").date()
            except: exp_d = today
            if r["Close Price"] > 0: s = "Closed"
            elif exp_d < today: s = "Expired (Win)"
            else: s = "Open / Running"
            return pd.Series([p, s])

        df[["Premium", "Status"]] = df.apply(up_row, axis=1)
        st.session_state.journal_data = apply_custom_sort(df)
        save_data(st.session_state.journal_data)
        st.session_state.last_refresh = datetime.now().strftime("%H:%M:%S")
        st.rerun()

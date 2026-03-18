import streamlit as st
import pandas as pd
import numpy as np
import os, shutil
from scipy.stats import norm
from datetime import datetime, timedelta
from alpaca.data.historical import OptionHistoricalDataClient, StockHistoricalDataClient
from alpaca.data.requests import OptionChainRequest, StockLatestQuoteRequest
from alpaca.data.enums import OptionsFeed, DataFeed

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

# Branding Header
st.markdown("### 🧪 Lucky Quants Lab")
st.divider()

try:
    API_KEY, SECRET_KEY = st.secrets["ALPACA_KEY"], st.secrets["ALPACA_SECRET"]
    opt_client = OptionHistoricalDataClient(API_KEY, SECRET_KEY)
    stock_client = StockHistoricalDataClient(API_KEY, SECRET_KEY)
except:
    st.error("Alpaca Keys Missing."); st.stop()

# --- 2. LOGIC & DATA ENGINE ---
DB, BKP = "lucky_ledger.csv", "lucky_ledger_backup.csv"
COLS = ["Ticker", "Type", "Strike", "Expiry", "Open Price", "Close Price", "Qty", "Commission", "Premium", "Status"]

def calc_ibkr_commission(qty):
    """Calculates IBKR Tiered Commission strictly as 1.05 per contract"""
    try:
        return round(float(qty) * 1.05, 2)
    except:
        return 1.05

def save_and_backup(df):
    df[COLS].to_csv(DB, index=False)
    shutil.copy2(DB, BKP)
    st.session_state.last_update = datetime.now().strftime("%Y-%m-%d")

def load_and_clean():
    if not os.path.exists(DB) and os.path.exists(BKP): shutil.copy2(BKP, DB)
    if os.path.exists(DB):
        try:
            df = pd.read_csv(DB)
            for c in COLS:
                if c not in df.columns:
                    df[c] = 0.0 if c in ["Open Price", "Close Price", "Premium", "Commission"] else (1 if c == "Qty" else "Unknown")
            df['exp_dt'] = pd.to_datetime(df['Expiry'], errors='coerce')
            df['is_open'] = df['Status'].astype(str).str.contains("Open", case=False, na=False)
            df = df.sort_values(by=['is_open', 'exp_dt'], ascending=[False, False])
            return df[COLS].reset_index(drop=True)
        except:
            return pd.DataFrame(columns=COLS)
    return pd.DataFrame(columns=COLS)

if 'journal' not in st.session_state: 
    st.session_state.journal = load_and_clean()
    st.session_state.last_update = datetime.now().strftime("%Y-%m-%d")

# --- 3. UI TABS ---
tab1, tab2 = st.tabs(["🔍 Strategy Optimizer", "📓 Lucky Ledger"])

# --- OPTIMIZER (Unchanged) ---
with tab1:
    c1, c2 = st.columns([1, 2])
    tk = c1.text_input("Ticker", value="TSM", key="opt_tk").upper()
    sf = c2.slider("Safety %", 70, 99, 90, key="opt_sf")
    if st.button("🔬 Run Analysis", key="opt_btn"):
        try:
            px = stock_client.get_stock_latest_quote(StockLatestQuoteRequest(symbol_or_symbols=tk, feed=DataFeed.IEX))[tk].ask_price
            exp = datetime.now() + timedelta(days=(4-datetime.now().weekday()+7)%7 or 7)
            chain = opt_client.get_option_chain(OptionChainRequest(underlying_symbol=tk, expiration_date=exp.date(), feed=OptionsFeed.INDICATIVE))
            res = []
            for s, d in chain.items():
                stk_val = float(s[-8:])/1000
                if "P" in s and stk_val < px:
                    d2 = (np.log(px/stk_val) + (0.04 - 0.5*0.3**2)*(7/365)) / (0.3*np.sqrt(7/365))
                    prob = norm.cdf(d2) * 100
                    if prob >= sf:
                        mid = (d.bid_price + d.ask_price) / 2
                        res.append({"Strike": stk_val, "Safety %": round(prob, 1), "Premium": round(mid, 2), "Est. Income": round(mid*100, 2)})
            st.write(f"**{tk} Price:** ${px:.2f}")
            st.dataframe(pd.DataFrame(res).sort_values("Strike", ascending=False), use_container_width=True)
        except Exception as e: st.error(f"Error: {e}")

# --- LEDGER ---
with tab2:
    df_j = st.session_state.journal
    total_prem = df_j["Premium"].sum()
    active_count = len(df_j[df_j["Status"].astype(str).str.contains("Open", na=False)])
    
    m1, m2 = st.columns(2)
    m1.metric("**Total Premium** 🤑", f"{total_prem:,.2f} (~HKD {(total_prem*7.8):,.2f})")
    m2.metric("**Active Trades** 📈", active_count)

    with st.expander("➕ Log New Trade"):
        if st.button("🔄 Reset Form", key="reset_btn"):
            st.session_state.log_tk = ""
            st.session_state.log_st = None
            st.session_state.log_op = None
            st.rerun()

        l1, l2, l3, l4 = st.columns(4)
        n_tk = l1.text_input("Ticker", value="TSM", key="log_tk").upper()
        n_ty = l2.selectbox("Type", ["Short Put", "Short Call"], key="log_ty")
        n_qt = l3.number_input("Qty", 1, key="log_qty")
        n_ex = l4.date_input("Expiry", datetime.now().date(), key="log_ex")
        
        l5, l6 = st.columns(2)
        n_st = l5.number_input("Strike", value=None, placeholder="Strike", step=0.1, key="log_st", format="%.1f")
        n_op = l6.number_input("Open Price", value=None, placeholder="0.59", step=0.01, key="log_op", format="%.2f")
        
        if st.button("🚀 Commit Trade", use_container_width=True):
            if n_st is not None and n_op is not None and n_tk != "":
                comm = calc_ibkr_commission(n_qt)
                net = round((float(n_op) * 100 * n_qt) - comm, 2)
                stat = "Expired (Win)" if n_ex < datetime.now().date() else "Open / Running"
                
                new_row = pd.DataFrame([{"Ticker": n_tk, "Type": n_ty, "Strike": round(n_st, 1), "Expiry": str(n_ex), "Open Price": round(float(n_op), 2), "Close Price": 0.0, "Qty": n_qt, "Commission": comm, "Premium": net, "Status": stat}])
                st.session_state.journal = pd.concat([df_j, new_row], ignore_index=True)
                save_and_backup(st.session_state.journal)
                st.rerun()

    st.write("### History")
    edt = st.data_editor(
        st.session_state.journal, 
        num_rows="dynamic", 
        use_container_width=True, 
        key="ledger_editor_v17",
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
            # Calculation: (Open - Close) * 100 * Qty - Total Commission
            p = round(((open_p - close_p) * 100 * qty) - comm, 2)
            
            try: ex_d = datetime.strptime(str(r["Expiry"]), "%Y-%m-%d").date()
            except: ex_d = datetime.now().date()
            
            # Logic: If Close is 0, status depends on Expiry
            if close_p > 0:
                s = "Closed"
            else:
                s = "Expired (Win)" if ex_d < datetime.now().date() else "Open / Running"
            
            return pd.Series([p, s])
        
        current_df[["Premium", "Status"]] = current_df.apply(update_row, axis=1)
        return current_df

    # Auto-save if editor changes
    if not edt.equals(st.session_state.journal):
        st.session_state.journal = refresh_calculations(edt)
        save_and_backup(st.session_state.journal)
        st.rerun()

    # Refresh Button
    if st.button("🔄 Refresh & Recalculate"):
        st.session_state.journal = refresh_calculations(st.session_state.journal)
        save_and_backup(st.session_state.journal)
        st.rerun()

# --- TIMESTAMP FOOTER ---
st.markdown(f'<div class="footer-right">Last Updated: {st.session_state.last_update}</div>', unsafe_allow_html=True)

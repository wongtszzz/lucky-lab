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
st.markdown("<style>.stMetric { background-color: #f0f2f6; padding: 5px 15px; border-radius: 10px; border: 1px solid #dcdcdc; } .footer { position: fixed; bottom: 10px; right: 10px; color: gray; font-size: 0.7em; }</style>", unsafe_allow_html=True)

try:
    API_KEY, SECRET_KEY = st.secrets["ALPACA_KEY"], st.secrets["ALPACA_SECRET"]
    opt_client = OptionHistoricalDataClient(API_KEY, SECRET_KEY)
    stock_client = StockHistoricalDataClient(API_KEY, SECRET_KEY)
except:
    st.error("Alpaca Keys Missing."); st.stop()

# --- 2. DATA ENGINE ---
DB, BKP = "lucky_ledger.csv", "lucky_ledger_backup.csv"
COLS = ["Ticker", "Type", "Strike", "Expiry", "Open Price", "Close Price", "Qty", "Premium", "Status"]

def save_and_backup(df):
    # Ensure we only save the specific 9 columns to prevent future corruption
    df[COLS].to_csv(DB, index=False)
    shutil.copy2(DB, BKP)
    st.session_state.last_backup = datetime.now().strftime("%H:%M:%S")

def load_and_clean():
    if not os.path.exists(DB) and os.path.exists(BKP): shutil.copy2(BKP, DB)
    if os.path.exists(DB):
        try:
            raw_df = pd.read_csv(DB)
            # FORCE REMOVE DUPLICATE COLUMNS BY NAME
            df = raw_df.loc[:, ~raw_df.columns.duplicated()].copy()
            
            # FORCE RENAME VARIANTS
            df = df.rename(columns={"Total Premium Collected": "Premium", "Premium (Total)": "Premium", "Premium (total)": "Premium"})
            
            # NUCLEAR FIX: If "Premium" is still a DataFrame, force it to the first occurrence only
            if hasattr(df, "Premium") and isinstance(df["Premium"], pd.DataFrame):
                premium_values = df["Premium"].iloc[:, 0]
                df = df.drop(columns="Premium")
                df["Premium"] = premium_values

            # Ensure every single required column exists as a 1D series
            for c in COLS:
                if c not in df.columns:
                    df[c] = 0.0 if c in ["Open Price", "Close Price", "Premium"] else (1 if c == "Qty" else "Unknown")
            
            # Robust Sorting
            df['is_open'] = df['Status'].astype(str).str.contains("Open", case=False, na=False)
            df['exp_dt'] = pd.to_datetime(df['Expiry'], errors='coerce')
            df = df.sort_values(by=['is_open', 'exp_dt'], ascending=[False, False])
            
            return df[COLS].reset_index(drop=True)
        except:
            return pd.DataFrame(columns=COLS)
    return pd.DataFrame(columns=COLS)

if 'journal' not in st.session_state: st.session_state.journal = load_and_clean()
if 'last_refresh' not in st.session_state: st.session_state.last_refresh = datetime.now().strftime("%H:%M:%S")

# --- 3. UI TABS ---
tab1, tab2 = st.tabs(["🔍 Strategy Optimizer", "📓 Lucky Ledger"])

with tab1:
    c1, c2 = st.columns([1, 2])
    tk = c1.text_input("Ticker", value="TSM", key="opt_tk_final").upper()
    sf = c2.slider("Safety %", 70, 99, 90, key="opt_sf_final")
    if st.button("🔬 Run Analysis", key="opt_run_final"):
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

with tab2:
    # RE-VALIDATE DATA IN SESSION STATE TO PREVENT CRASH
    df_display = st.session_state.journal.copy()
    
    # Force 'Premium' to be numeric and 1D for the metric calculation
    premium_series = pd.to_numeric(pd.Series(df_display["Premium"].values.flatten()), errors='coerce').fillna(0)
    total_prem = premium_series.sum()
    active_count = len(df_display[df_display["Status"].astype(str).str.contains("Open", na=False)])
    
    m1, m2 = st.columns(2)
    m1.metric("**Total Premium** 🤑", f"{int(round(total_prem)):,} (~HKD {int(round(total_prem*7.8)):,})")
    m2.metric("**Active Trades** 📈", active_count)

    with st.expander("➕ Log New Trade"):
        l1, l2, l3, l4 = st.columns(4)
        n_tk = l1.text_input("Ticker", value="TSM", key="n_tk").upper()
        n_ty = l2.selectbox("Type", ["Short Put", "Short Call"], key="n_ty")
        n_qt = l3.number_input("Qty", 1, key="n_qt")
        n_ex = l4.date_input("Expiry", datetime.now().date(), key="n_ex")
        l5, l6 = st.columns(2)
        n_st = l5.number_input("Strike", 0.0, step=0.5, key="n_st")
        n_op = l6.number_input("Open Price", 0.0, step=0.01, key="n_op")
        
        if st.button("🚀 Commit Trade", use_container_width=True):
            net = round((n_op * 100 * n_qt) - max(1.05, 0.70 * n_qt), 2)
            stat = "Expired (Win)" if n_ex < datetime.now().date() else "Open / Running"
            new_row = pd.DataFrame([{"Ticker": n_tk, "Type": n_ty, "Strike": n_st, "Expiry": str(n_ex), "Open Price": n_op, "Close Price": 0.0, "Qty": n_qt, "Premium": net, "Status": stat}])
            st.session_state.journal = pd.concat([st.session_state.journal, new_row], ignore_index=True)
            save_and_backup(st.session_state.journal); st.rerun()

    st.write("### History")
    edt = st.data_editor(st.session_state.journal, num_rows="dynamic", use_container_width=True, key="ledger_edt_v3")
    
    if not edt.equals(st.session_state.journal):
        edt["Open Price"] = pd.to_numeric(edt["Open Price"], errors='coerce').fillna(0)
        edt["Close Price"] = pd.to_numeric(edt["Close Price"], errors='coerce').fillna(0)
        
        def refresh_row(r):
            p = round(((r["Open Price"] - r["Close Price"]) * 100 * r["Qty"]) - max(1.05, 0.70 * r["Qty"]), 2)
            try: ex_d = datetime.strptime(str(r["Expiry"]), "%Y-%m-%d").date()
            except: ex_d = datetime.now().date()
            s = "Closed" if r["Close Price"] > 0 else ("Expired (Win)" if ex_d < datetime.now().date() else "Open / Running")
            return pd.Series([p, s])

        edt[["Premium", "Status"]] = edt.apply(refresh_row, axis=1)
        st.session_state.journal = edt
        save_and_backup(edt); st.rerun()

# --- FOOTER ---
st.markdown(f'<div class="footer">Last Backup: {st.session_state.get("last_backup", "Initial")}</div>', unsafe_allow_html=True)

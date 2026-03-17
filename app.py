import streamlit as st
from alpaca.data.historical import OptionHistoricalDataClient
from alpaca.data.requests import OptionChainRequest, OptionLatestQuoteRequest, OptionBarsRequest
from alpaca.data.timeframe import TimeFrame
from datetime import datetime, timedelta
import pandas as pd

# --- 1. CONFIG & AUTH ---
st.set_page_config(page_title="Lucky Lab", page_icon="🧪", layout="wide")
try:
    API_KEY, SECRET_KEY = st.secrets["ALPACA_KEY"], st.secrets["ALPACA_SECRET"]
    opt_client = OptionHistoricalDataClient(API_KEY, SECRET_KEY)
except:
    st.error("Alpaca Keys Missing."); st.stop()

# --- 2. SESSION STATE & COLUMN MIGRATION ---
# Defining the final target columns
final_cols = ["Ticker", "Type", "Strike", "Expiry", "Premium (Total)", "Qty", "Total Premium Collected"]

if 'journal_data' not in st.session_state:
    st.session_state.journal_data = pd.DataFrame(columns=final_cols)
else:
    # SAFETY SHIELD: If the user has old data with "Total Profit", rename it to avoid the KeyError
    if "Total Profit" in st.session_state.journal_data.columns:
        st.session_state.journal_data = st.session_state.journal_data.rename(
            columns={"Total Profit": "Total Premium Collected"}
        )
    # Ensure all required columns exist
    for col in final_cols:
        if col not in st.session_state.journal_data.columns:
            st.session_state.journal_data[col] = None

# --- 3. UI ---
st.title("🧪 Lucky Lab: Options Ledger")

# Calculate Net Metric safely
try:
    raw_profits = pd.to_numeric(st.session_state.journal_data["Total Premium Collected"], errors='coerce').fillna(0)
    total_net = raw_profits.sum()
except:
    total_net = 0.0

st.metric("Total Net Received (After IBKR Fees)", f"${total_net:,.2f}")

with st.expander("➕ Log New Trade", expanded=True):
    c1, c2, c3, c4 = st.columns(4)
    t_input = c1.text_input("Ticker", value="TSM").upper()
    strat = c2.selectbox("Strategy", ["Short Put", "Short Call"])
    qty = c3.number_input("Qty", min_value=1, value=1)
    exp_date = c4.date_input("Expiry Date", value=datetime(2026, 2, 27).date())
    
    # STRIKE: 0.5 step, Starts Empty, %g format hides .0
    strike = st.number_input("Strike Price", value=None, step=0.5, format="%g", placeholder="Enter Strike (e.g. 345)")
    
    if st.button("🚀 Commit & Calculate"):
        if strike is None:
            st.error("Please enter a strike price.")
        else:
            try:
                flag = "P" if strat == "Short Put" else "C"
                strike_code = f"{int(round(strike * 1000)):08d}"
                exp_code = exp_date.strftime('%y%m%d')
                sym = f"{t_input}{exp_code}{flag}{strike_code}"
                
                raw_price = 0.0
                
                # Fetch Logic
                try:
                    chain = opt_client.get_option_chain(OptionChainRequest(underlying_symbol=t_input, expiration_date=exp_date))
                    if sym in chain: raw_price = (chain[sym].bid_price + chain[sym].ask_price) / 2
                except: pass
                
                if raw_price == 0:
                    try:
                        lq = opt_client.get_option_latest_quote(OptionLatestQuoteRequest(symbol_or_symbols=sym))
                        if sym in lq: raw_price = (lq[sym].bid_price + lq[sym].ask_price) / 2
                    except: pass
                
                if raw_price == 0:
                    # Look back 60 days for expired contracts
                    res = opt_client.get_option_bars(OptionBarsRequest(symbol_or_symbols=sym, timeframe=TimeFrame.Day, 
                                                                       start=datetime.now()-timedelta(days=60), end=datetime.now()))
                    if sym in res.data: raw_price = res.data[sym][-1].close

                if raw_price > 0:
                    cash_premium = round(float(raw_price) * 100, 2)
                    # IBKR Tiered Calculation
                    comm = max(1.05, 0.70 * qty)
                    net_received = (cash_premium * qty) - comm
                    
                    display_strike = int(strike) if strike % 1 == 0 else strike
                    
                    new_row = {
                        "Ticker": t_input, "Type": strat, "Strike": display_strike, 
                        "Expiry": exp_date.strftime("%Y-%m-%d"),
                        "Premium (Total)": cash_premium, 
                        "Qty": int(qty),
                        "Total Premium Collected": round(net_received, 2)
                    }
                    st.session_state.journal_data = pd.concat([st.session_state.journal_data, pd.DataFrame([new_row])], ignore_index=True)
                    st.rerun()
                else:
                    st.error(f"Could not fetch price for {sym}. Check your ticker/expiry.")
            except Exception as e:
                st.error(f"Error: {e}")

# --- 4. TABLE ---
st.write("### Trade History")
st.session_state.journal_data = st.data_editor(st.session_state.journal_data, num_rows="dynamic", use_container_width=True)

if st.button("🗑️ Reset Ledger"):
    st.session_state.journal_data = pd.DataFrame(columns=final_cols)
    st.rerun()

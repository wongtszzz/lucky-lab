import streamlit as st
from alpaca.data.historical import OptionHistoricalDataClient, StockHistoricalDataClient
from alpaca.data.requests import OptionChainRequest, StockLatestQuoteRequest, OptionBarsRequest
from alpaca.data.enums import DataFeed
from alpaca.data.timeframe import TimeFrame
import numpy as np
from scipy.stats import norm
import pandas as pd
from datetime import datetime, timedelta

# --- 1. CONFIG & BRANDING ---
st.set_page_config(page_title="Lucky Lab", page_icon="🧪", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 10px; border: 1px solid #e1e4e8; }
    h1 { color: #1e3a8a; font-family: 'Helvetica Neue', sans-serif; }
    [data-testid="stExpander"] { background-color: #ffffff; border-radius: 10px; border: 1px solid #e1e4e8; }
    input { caret-color: #1e3a8a; }
    </style>
""", unsafe_allow_html=True)

st.title("🧪 Lucky Lab: Options Quant")

# --- 2. AUTHENTICATION ---
try:
    API_KEY = st.secrets["ALPACA_KEY"]
    SECRET_KEY = st.secrets["ALPACA_SECRET"]
    stock_client = StockHistoricalDataClient(API_KEY, SECRET_KEY)
    opt_client = OptionHistoricalDataClient(API_KEY, SECRET_KEY)
except Exception as e:
    st.error("⚠️ Alpaca Keys Missing. Update Streamlit Secrets.")
    st.stop()

# --- 3. CREATE TABS ---
tab1, tab2 = st.tabs(["🔍 Strategy Optimizer", "📓 Lucky Ledger"])

# --- TAB 1: STRATEGY OPTIMIZER ---
with tab1:
    st.subheader("Naked Put Scanner")
    col_a, col_b, col_c = st.columns(3)
    ticker_scan = col_a.text_input("Ticker", value="SPY").upper()
    safety_threshold = col_b.slider("Min Safety %", 70, 99, 90)
    min_vol = col_c.number_input("Min Volume", value=0)

    if st.button("🔬 Run Lab Analysis"):
        with st.spinner("Analyzing..."):
            try:
                price_data = stock_client.get_stock_latest_quote(StockLatestQuoteRequest(symbol_or_symbols=ticker_scan, feed=DataFeed.IEX))
                curr = price_data[ticker_scan].ask_price
                today = datetime.now()
                expiry = today + timedelta(days=(4 - today.weekday() + 7) % 7 or 7)
                chain = opt_client.get_option_chain(OptionChainRequest(underlying_symbol=ticker_scan, expiration_date=expiry.date()))
                
                res = []
                for sym, data in chain.items():
                    strike_val = float(sym[-8:]) / 1000
                    if "P" in sym and strike_val < curr:
                        mid = (data.bid_price + data.ask_price) / 2
                        res.append({"Strike": round(strike_val, 1), "Premium": mid, "Vol": getattr(data, 'volume', 0)})
                st.dataframe(pd.DataFrame(res), use_container_width=True)
            except Exception as e:
                st.error(f"Scanner Error: {e}")

# --- TAB 2: LUCKY LEDGER ---
with tab2:
    st.subheader("📓 The Lucky Ledger")

    # IBKR TIERED 1.05 MINIMUM
    MIN_COMMISSION = 1.05 
    
    if 'journal_data' not in st.session_state:
        st.session_state.journal_data = pd.DataFrame(columns=["Ticker", "Type", "Strike", "Expiry", "Premium", "Qty", "Commission", "Total Profit"])

    # Metrics display
    profits = pd.to_numeric(st.session_state.journal_data["Total Profit"], errors='coerce').fillna(0)
    st.metric("Net Profit", f"${profits.sum():,.2f}")
    st.divider()

    with st.expander("➕ Log New Trade", expanded=True):
        c1, c2, c3 = st.columns(3)
        t_input = c1.text_input("Ticker", value="TSM").upper()
        strat = c2.selectbox("Strategy", ["Short Put", "Short Call"])
        qty = c3.number_input("Qty", min_value=1, value=1)

        c4, c5 = st.columns(2)
        exp_date = c4.date_input("Expiry Date", value=datetime(2026, 2, 27).date())
        
        # --- FIXED STRIKE SETTINGS ---
        # value=None (starts empty), step=0.1 (+/- increment), format="%.1f" (1 decimal place)
        strike = c5.number_input("Strike Price", value=None, step=0.1, format="%.1f", placeholder="Enter Strike (e.g. 345.0)")
        
        if st.button("🚀 Fetch & Commit"):
            if strike is None:
                st.error("Please enter a strike price.")
            else:
                try:
                    # Formatting for Alpaca API (OSI Format)
                    flag = "P" if strat == "Short Put" else "C"
                    strike_code = f"{int(round(strike * 1000)):08d}"
                    expiry_code = exp_date.strftime('%y%m%d')
                    sym = f"{t_input}{expiry_code}{flag}{strike_code}"

                    # API Call
                    chain = opt_client.get_option_chain(OptionChainRequest(underlying_symbol=t_input, expiration_date=exp_date))
                    
                    if sym not in chain:
                        st.error(f"Contract {sym} not found. Check if {exp_date} has a strike at {strike}.")
                    else:
                        data = chain[sym]
                        mid_price = (data.bid_price + data.ask_price) / 2
                        if mid_price == 0: mid_price = getattr(data, 'last_price', 0.01)
                        
                        # IBKR Tiered Logic
                        base_calc = (0.70 * qty)
                        final_comm = max(MIN_COMMISSION, base_calc)
                        
                        # Profit Logic
                        cash_premium = round(mid_price * 100, 2)
                        net_profit = (cash_premium * qty) - final_comm
                        
                        new_row = {
                            "Ticker": t_input, "Type": strat, "Strike": round(strike, 1), 
                            "Expiry": exp_date.strftime("%Y-%m-%d"),
                            "Premium": cash_premium, "Qty": int(qty),
                            "Commission": round(final_comm, 2),
                            "Total Profit": round(net_profit, 2)
                        }
                        st.session_state.journal_data = pd.concat([st.session_state.journal_data, pd.DataFrame([new_row])], ignore_index=True)
                        st.rerun()
                except Exception as e:
                    st.error(f"API Error: {e}")

    # History Table
    st.write("### Trade History")
    # Ensuring the dataframe display also respects 1 decimal place for Strike
    st.session_state.journal_data["Strike"] = pd.to_numeric(st.session_state.journal_data["Strike"]).round(1)
    st.session_state.journal_data = st.data_editor(st.session_state.journal_data, num_rows="dynamic", use_container_width=True)

    if st.button("🗑️ Reset Ledger"):
        st.session_state.journal_data = pd.DataFrame(columns=["Ticker", "Type", "Strike", "Expiry", "Premium", "Qty", "Commission", "Total Profit"])
        st.rerun()

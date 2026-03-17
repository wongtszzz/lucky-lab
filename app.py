import streamlit as st
import pandas as pd
import numpy as np
from scipy.stats import norm
from datetime import datetime, timedelta
from alpaca.data.historical import OptionHistoricalDataClient, StockHistoricalDataClient
from alpaca.data.requests import OptionChainRequest, StockLatestQuoteRequest
from alpaca.data.enums import OptionsFeed, DataFeed

# --- 1. BRANDING & CONFIG ---
st.set_page_config(page_title="Lucky Quants Lab", page_icon="🧪", layout="wide")

# Sidebar Branding
st.sidebar.markdown("# Lucky Quants Lab 🧪")

try:
    API_KEY = st.secrets["ALPACA_KEY"]
    SECRET_KEY = st.secrets["ALPACA_SECRET"]
    opt_client = OptionHistoricalDataClient(API_KEY, SECRET_KEY)
    stock_client = StockHistoricalDataClient(API_KEY, SECRET_KEY)
except:
    st.error("Alpaca Keys Missing in Secrets.")
    st.stop()

# --- 2. SESSION STATE ---
if 'journal_data' not in st.session_state:
    st.session_state.journal_data = pd.DataFrame(columns=["Ticker", "Type", "Strike", "Expiry", "Premium (Total)", "Qty", "Total Premium Collected"])

# --- 3. TABS ---
tab1, tab2 = st.tabs(["🔍 Strategy Optimizer", "📓 Lucky Ledger"])

# --- TAB 1: STRATEGY OPTIMIZER (Untouched) ---
with tab1:
    st.subheader("Naked Put Scanner")
    c1, c2, c3 = st.columns(3)
    t_scan = c1.text_input("Ticker to Scan", value="TSM").upper()
    safety_target = c2.slider("Min Safety % (OTM)", 70, 99, 90)
    
    if st.button("🔬 Run Lab Analysis"):
        with st.spinner(f"Analyzing {t_scan}..."):
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
                            results.append({"Strike": strike_val, "Safety %": round(prob_otm, 1), "Premium (Per Share)": round(mid, 2), "Est. Income": round(mid * 100, 2)})
                
                df_res = pd.DataFrame(results).sort_values("Strike", ascending=False)
                st.write(f"**Current {t_scan} Price:** ${curr_price:.2f}")
                st.dataframe(df_res, use_container_width=True)
            except Exception as e:
                st.error(f"Scanner Error: {e}")

# --- TAB 2: LUCKY LEDGER (Optimized for Pure Calc) ---
with tab2:
    st.subheader("📓 Trade Ledger")
    
    # Recalculate Metric on every run
    total_net = pd.to_numeric(st.session_state.journal_data["Total Premium Collected"], errors='coerce').fillna(0).sum()
    st.metric("Total Net Received (After Fees)", f"${total_net:,.2f}")

    with st.expander("➕ Log New Trade", expanded=True):
        l1, l2, l3, l4 = st.columns(4)
        ticker_log = l1.text_input("Ticker", value="TSM").upper()
        strat = l2.selectbox("Type", ["Short Put", "Short Call"])
        qty = l3.number_input("Qty", min_value=1, value=1)
        exp = l4.date_input("Expiry", value=datetime.now().date())
        
        l5, l6 = st.columns(2)
        strike = l5.number_input("Strike Price", value=None, step=0.5, format="%g", placeholder="Enter Strike (e.g. 345)")
        price_per_share = l6.number_input("Price per Share", value=None, step=0.01, format="%.2f", placeholder="Enter Fill (e.g. 0.59)")
        
        if st.button("🚀 Commit & Calculate"):
            if strike is None or price_per_share is None:
                st.error("Please enter both Strike and Price per Share.")
            else:
                # Core Math Logic
                cash_premium = round(float(price_per_share) * 100, 2)
                comm = max(1.05, 0.70 * qty)
                net_total = (cash_premium * qty) - comm
                
                display_strike = int(strike) if strike % 1 == 0 else strike
                
                new_row = {
                    "Ticker": ticker_log, "Type": strat, "Strike": display_strike, 
                    "Expiry": exp.strftime("%Y-%m-%d"),
                    "Premium (Total)": cash_premium, "Qty": int(qty),
                    "Total Premium Collected": round(net_total, 2)
                }
                st.session_state.journal_data = pd.concat([st.session_state.journal_data, pd.DataFrame([new_row])], ignore_index=True)
                st.rerun()

    st.write("### History")
    # Data editor for reviewing/tweaking entries
    st.session_state.journal_data = st.data_editor(st.session_state.journal_data, num_rows="dynamic", use_container_width=True)

    # --- REFRESH / RECALCULATE LOGIC ---
    if st.button("🔄 Refresh & Recalculate"):
        # We ensure the columns are numeric and re-sum everything to fix any manually edited cell errors
        df = st.session_state.journal_data.copy()
        
        # Recalculate 'Total Premium Collected' for every row based on Qty and Premium (Total)
        # This fixes any manual math errors in the table
        df["Premium (Total)"] = pd.to_numeric(df["Premium (Total)"], errors='coerce').fillna(0)
        df["Qty"] = pd.to_numeric(df["Qty"], errors='coerce').fillna(1)
        
        # Re-apply IBKR Fees logic to all rows
        df["Total Premium Collected"] = df.apply(
            lambda row: round((row["Premium (Total)"] * row["Qty"]) - max(1.05, 0.70 * row["Qty"]), 2), 
            axis=1
        )
        
        st.session_state.journal_data = df
        st.success("Calculations refreshed and verified!")
        st.rerun()

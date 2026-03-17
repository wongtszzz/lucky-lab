import streamlit as st
from alpaca.data.historical import OptionHistoricalDataClient
from alpaca.data.requests import OptionChainRequest, OptionLatestQuoteRequest
from alpaca.data.enums import OptionsFeed
from datetime import datetime
import pandas as pd

# --- 1. CONFIG & AUTH ---
st.set_page_config(page_title="Lucky Lab", page_icon="🧪", layout="wide")
try:
    API_KEY, SECRET_KEY = st.secrets["ALPACA_KEY"], st.secrets["ALPACA_SECRET"]
    opt_client = OptionHistoricalDataClient(API_KEY, SECRET_KEY)
except:
    st.error("Alpaca Keys Missing."); st.stop()

# --- 2. SESSION STATE ---
final_cols = ["Ticker", "Type", "Strike", "Expiry", "Premium (Total)", "Qty", "Total Premium Collected"]
if 'journal_data' not in st.session_state:
    st.session_state.journal_data = pd.DataFrame(columns=final_cols)

# --- 3. UI ---
st.title("🧪 Lucky Lab: Options Ledger")

total_net = pd.to_numeric(st.session_state.journal_data["Total Premium Collected"], errors='coerce').fillna(0).sum()
st.metric("Total Net Received (After IBKR Fees)", f"${total_net:,.2f}")

with st.expander("➕ Log New Trade", expanded=True):
    c1, c2, c3, c4 = st.columns(4)
    t_input = c1.text_input("Ticker", value="TSM").upper()
    strat = c2.selectbox("Strategy", ["Short Put", "Short Call"])
    qty = c3.number_input("Qty", min_value=1, value=1)
    exp_date = c4.date_input("Expiry Date", value=datetime.now().date())
    
    c5, c6 = st.columns(2)
    # STRIKE: 0.5 step, %g format hides .0, Starts Empty
    strike = c5.number_input("Strike Price", value=None, step=0.5, format="%g", placeholder="Enter Strike (e.g. 345)")
    
    # MANUAL PRICE: This is now your primary backup
    manual_price = c6.number_input("Manual Price (Per Share)", value=None, step=0.01, format="%.2f", placeholder="Enter Price (e.g. 0.59)")
    
    if st.button("🚀 Commit & Calculate"):
        if strike is None:
            st.error("Please enter a strike price.")
        else:
            final_price = 0.0
            
            # 1. Try to Fetch if manual is empty
            if manual_price is None or manual_price == 0:
                try:
                    # Attempting to fetch indicative data
                    chain = opt_client.get_option_chain(OptionChainRequest(underlying_symbol=t_input, expiration_date=exp_date, feed=OptionsFeed.INDICATIVE))
                    flag = "P" if strat == "Short Put" else "C"
                    strike_code = f"{int(round(strike * 1000)):08d}"
                    sym = f"{t_input}{exp_date.strftime('%y%m%d')}{flag}{strike_code}"
                    
                    if sym in chain:
                        final_price = (chain[sym].bid_price + chain[sym].ask_price) / 2
                except:
                    pass # Silently fail to Step 2
            else:
                # 2. Use your Manual Entry
                final_price = manual_price

            if final_price > 0:
                # --- CALCULATION ENGINE ---
                # Premium is (Price * 100)
                cash_premium = round(float(final_price) * 100, 2)
                
                # IBKR Tiered Fees: ~$0.70/contract with $1.05 absolute minimum
                comm = max(1.05, 0.70 * qty)
                
                # Net = (Premium * Qty) - Fees
                net_received = (cash_premium * qty) - comm
                
                display_strike = int(strike) if strike % 1 == 0 else strike
                
                new_row = {
                    "Ticker": t_input, 
                    "Type": strat, 
                    "Strike": display_strike, 
                    "Expiry": exp_date.strftime("%Y-%m-%d"),
                    "Premium (Total)": cash_premium, 
                    "Qty": int(qty),
                    "Total Premium Collected": round(net_received, 2)
                }
                st.session_state.journal_data = pd.concat([st.session_state.journal_data, pd.DataFrame([new_row])], ignore_index=True)
                st.rerun()
            else:
                st.warning("⚠️ Data fetch failed. Please enter the 'Manual Price (Per Share)' to finish the log.")

# --- 4. TABLE ---
st.write("### Trade History")
st.session_state.journal_data = st.data_editor(st.session_state.journal_data, num_rows="dynamic", use_container_width=True)

if st.button("🗑️ Reset Ledger"):
    st.session_state.journal_data = pd.DataFrame(columns=final_cols)
    st.rerun()

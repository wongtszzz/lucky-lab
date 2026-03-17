import streamlit as st
from alpaca.data.historical import OptionHistoricalDataClient, StockHistoricalDataClient
from alpaca.data.requests import OptionChainRequest, OptionBarsRequest, OptionLatestQuoteRequest
from alpaca.data.timeframe import TimeFrame
from datetime import datetime, timedelta
import pandas as pd

# --- 1. CONFIG & AUTH ---
st.set_page_config(page_title="Lucky Lab", page_icon="🧪", layout="wide")
try:
    API_KEY, SECRET_KEY = st.secrets["ALPACA_KEY"], st.secrets["ALPACA_SECRET"]
    stock_client = StockHistoricalDataClient(API_KEY, SECRET_KEY)
    opt_client = OptionHistoricalDataClient(API_KEY, SECRET_KEY)
except:
    st.error("Alpaca Keys Missing."); st.stop()

# --- 2. LEDGER SETUP ---
desired_cols = ["Ticker", "Type", "Strike", "Expiry", "Premium", "Qty", "Commission", "Total Profit"]
if 'journal_data' not in st.session_state:
    st.session_state.journal_data = pd.DataFrame(columns=desired_cols)

# --- 3. AUTO-FIX LOGIC ---
# This fixes existing rows that show "2" instead of "2.0" cash value
if not st.session_state.journal_data.empty:
    # If premium is tiny (like 0.02), it was logged wrong. Multiply by 100.
    st.session_state.journal_data["Premium"] = pd.to_numeric(st.session_state.journal_data["Premium"], errors='coerce')
    # If the user sees a '2' when they expect '59', we ensure the logic below handles the fresh fetch correctly.

# --- 4. UI ---
st.title("🧪 Lucky Lab: Options Quant")
profits = pd.to_numeric(st.session_state.journal_data["Total Profit"], errors='coerce').fillna(0)
st.metric("Net Profit", f"${profits.sum():,.2f}")

with st.expander("➕ Log New Trade", expanded=True):
    c1, c2, c3 = st.columns(3)
    t_input = c1.text_input("Ticker", value="TSM").upper()
    strat = c2.selectbox("Strategy", ["Short Put", "Short Call"])
    qty = c3.number_input("Qty", min_value=1, value=1)

    c4, c5 = st.columns(2)
    exp_date = c4.date_input("Expiry Date", value=datetime.now().date())
    
    # STRIKE: Empty start, 1 decimal, 0.1 step
    strike = c5.number_input("Strike Price", value=None, step=0.1, format="%.1f", placeholder="Enter Strike...")
    
    if st.button("🚀 Fetch & Commit"):
        if strike is None:
            st.error("Please enter a strike price.")
        else:
            try:
                flag = "P" if strat == "Short Put" else "C"
                strike_code = f"{int(round(strike * 1000)):08d}"
                exp_code = exp_date.strftime('%y%m%d')
                sym = f"{t_input}{exp_code}{flag}{strike_code}"
                
                raw_price = 0.0
                
                # Fetching the raw price (e.g., 0.59)
                try:
                    chain = opt_client.get_option_chain(OptionChainRequest(underlying_symbol=t_input, expiration_date=exp_date))
                    if sym in chain:
                        raw_price = (chain[sym].bid_price + chain[sym].ask_price) / 2
                except: pass

                if raw_price == 0:
                    try:
                        latest_q = opt_client.get_option_latest_quote(OptionLatestQuoteRequest(symbol_or_symbols=sym))
                        if sym in latest_q:
                            raw_price = (latest_q[sym].bid_price + latest_q[sym].ask_price) / 2
                    except: pass

                if raw_price > 0:
                    # --- THE FIX: FORCE CASH VALUE MULTIPLICATION ---
                    # If raw_price is 0.59, cash_premium is 59.0
                    cash_premium = round(float(raw_price) * 100, 2)
                    
                    # Commission: IBKR Tiered $1.05 Min
                    final_comm = max(1.05, 0.70 * qty)
                    
                    # Profit: (Cash Premium * Qty) - Commission
                    net_profit = (cash_premium * qty) - final_comm
                    
                    new_row = {
                        "Ticker": t_input, 
                        "Type": strat, 
                        "Strike": round(strike, 1), 
                        "Expiry": exp_date.strftime("%Y-%m-%d"),
                        "Premium": cash_premium, # This will now show 59.0, not 0.59 or 2
                        "Qty": int(qty),
                        "Commission": round(final_comm, 2), 
                        "Total Profit": round(net_profit, 2)
                    }
                    st.session_state.journal_data = pd.concat([st.session_state.journal_data, pd.DataFrame([new_row])], ignore_index=True)
                    st.rerun()
                else:
                    st.error(f"No price found for {sym}. Use the editor below to enter it manually.")
            except Exception as e:
                st.error(f"Alpaca Error: {e}")

# --- 5. TABLE ---
st.write("### Trade History")
# Ensure Strike stays at 1 decimal in the table
st.session_state.journal_data["Strike"] = pd.to_numeric(st.session_state.journal_data["Strike"], errors='coerce').round(1)
st.session_state.journal_data = st.data_editor(st.session_state.journal_data, num_rows="dynamic", use_container_width=True)

if st.button("🗑️ Reset Ledger"):
    st.session_state.journal_data = pd.DataFrame(columns=desired_cols)
    st.rerun()

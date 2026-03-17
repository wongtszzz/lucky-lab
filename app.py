import streamlit as st
from alpaca.data.historical import OptionHistoricalDataClient, StockHistoricalDataClient
from alpaca.data.requests import OptionChainRequest, StockLatestQuoteRequest
from alpaca.data.enums import DataFeed
import numpy as np
from scipy.stats import norm
import pandas as pd
from datetime import datetime, timedelta
import re

# --- 1. CONFIG & BRANDING ---
st.set_page_config(page_title="Lucky Lab", page_icon="🧪", layout="wide")

st.html("""
    <style>
    .main { background-color: #f5f7f9; }
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 10px; border: 1px solid #e1e4e8; }
    h1 { color: #1e3a8a; font-family: 'Helvetica Neue', sans-serif; }
    [data-testid="stExpander"] { background-color: #ffffff; border-radius: 10px; border: 1px solid #e1e4e8; }
    </style>
""")

st.title("🧪 Lucky Lab: Options Quant")

# --- 2. AUTHENTICATION ---
try:
    API_KEY = st.secrets["ALPACA_KEY"]
    SECRET_KEY = st.secrets["ALPACA_SECRET"]
    stock_client = StockHistoricalDataClient(API_KEY, SECRET_KEY)
    opt_client = OptionHistoricalDataClient(API_KEY, SECRET_KEY)
except Exception as e:
    st.error("⚠️ Lucky Lab Keys Missing. Add ALPACA_KEY and ALPACA_SECRET to Streamlit Secrets.")
    st.stop()

tab1, tab2 = st.tabs(["🔍 Strategy Optimizer", "📓 Lucky Ledger"])

# --- TAB 1: STRATEGY OPTIMIZER ---
with tab1:
    st.subheader("Naked Put Scanner")
    col_a, col_b, col_c = st.columns([1, 1, 1])
    ticker_scan = col_a.text_input("Ticker Symbol", value="SPY", key="scan_tick").upper()
    safety_threshold = col_b.slider("Minimum Safety %", 70, 99, 90)
    min_vol = col_c.number_input("Min Volume", value=0)

    if st.button("🔬 Run Lab Analysis"):
        with st.spinner(f"Analyzing {ticker_scan}..."):
            try:
                price_data = stock_client.get_stock_latest_quote(StockLatestQuoteRequest(symbol_or_symbols=ticker_scan, feed=DataFeed.IEX))
                current_price = price_data[ticker_scan].ask_price
                st.metric(f"{ticker_scan} Live Ask", f"${current_price:.2f}")

                today = datetime.now()
                expiry = today + timedelta(days=(4 - today.weekday() + 7) % 7 or 7)
                chain = opt_client.get_option_chain(OptionChainRequest(underlying_symbol=ticker_scan, expiration_date=expiry.date()))
                
                results = []
                for symbol, data in chain.items():
                    # Extract strike from symbol (last 8 digits)
                    strike_from_sym = float(symbol[-8:]) / 1000
                    
                    if "P" in symbol and strike_from_sym < current_price:
                        iv = getattr(data, 'implied_volatility', 0.18) or 0.18
                        t_years = max((expiry - today).days, 1) / 365
                        d2 = (np.log(current_price/strike_from_sym) + (0.042 - 0.5*iv**2)*t_years) / (iv*np.sqrt(t_years))
                        prob_otm = norm.cdf(d2) * 100
                        
                        if prob_otm >= safety_threshold and (getattr(data, 'volume', 0) or 0) >= min_vol:
                            mid = (data.bid_price + data.ask_price) / 2
                            m_req = max((0.20*current_price - (current_price-strike_from_sym) + mid)*100, (0.10*strike_from_sym)*100)
                            ann_roc = (mid*100/m_req) * (365/max((expiry-today).days, 1)) * 100
                            results.append({
                                "Strike": strike_from_sym, "Safety %": round(prob_otm, 1),
                                "Premium": f"${mid:.2f}", "Ann. ROC %": round(ann_roc, 1),
                                "Volume": getattr(data, 'volume', 0)
                            })
                if results:
                    st.dataframe(pd.DataFrame(results).sort_values("Ann. ROC %", ascending=False), use_container_width=True)
            except Exception as e:
                st.error(f"Lab Error: {e}")

# --- TAB 2: LUCKY LEDGER ---
with tab2:
    st.subheader("📓 The Lucky Ledger")

    if 'journal_data' not in st.session_state:
        st.session_state.journal_data = pd.DataFrame(columns=["Date", "Ticker", "Type", "Strike", "Expiry", "Premium", "Qty", "Total Credit"])

    # 1. TOP METRICS
    m1, m2 = st.columns(2)
    overall_p = st.session_state.journal_data["Total Credit"].astype(float).sum() if not st.session_state.journal_data.empty else 0.0
    m1.metric("Overall Profit", f"${overall_p:,.2f}")
    m2.metric("Last 7 Days", "Tracking...") # Simple placeholder for brevity

    # 2. ENTRY FORM
    with st.expander("➕ Log New Trade", expanded=True):
        c1, c2, c3 = st.columns(3)
        new_ticker = c1.text_input("Ticker", value="SPY", key="log_tick").upper()
        strategy = c2.selectbox("Strategy", options=["Short Put", "Short Call"], index=0)
        qty = c3.number_input("Qty", min_value=1, value=1)

        c4, c5 = st.columns(2)
        expiry_date = c4.date_input("Expiry Date", value=datetime.now() + timedelta(days=7))
        target_strike = c5.number_input("Target Strike", value=0.0, step=0.5)
        
        if st.button("🚀 Fetch & Commit"):
            try:
                chain = opt_client.get_option_chain(OptionChainRequest(underlying_symbol=new_ticker, expiration_date=expiry_date))
                flag = "P" if strategy == "Short Put" else "C"
                found = False
                
                for symbol, data in chain.items():
                    # Extract strike from symbol to compare
                    strike_from_sym = float(symbol[-8:]) / 1000
                    if flag in symbol and abs(strike_from_sym - target_strike) < 0.1:
                        p_val = (data.bid_price + data.ask_price) / 2
                        if p_val == 0: p_val = getattr(data, 'last_price', 0.05)
                        
                        new_row = {
                            "Date": datetime.now().strftime("%Y-%m-%d"), "Ticker": new_ticker,
                            "Type": strategy, "Strike": strike_from_sym, "Expiry": expiry_date.strftime("%Y-%m-%d"),
                            "Premium": float(p_val), "Qty": int(qty), "Total Credit": round(float(p_val) * qty * 100, 2)
                        }
                        st.session_state.journal_data = pd.concat([st.session_state.journal_data, pd.DataFrame([new_row])], ignore_index=True)
                        found = True
                        st.rerun()
                if not found: st.error("Strike not found for this date.")
            except Exception as e:
                st.error(f"Fetch failed: {e}")

    st.write("### Trade History")
    edited = st.data_editor(st.session_state.journal_data, num_rows="dynamic", use_container_width=True)
    st.session_state.journal_data = edited

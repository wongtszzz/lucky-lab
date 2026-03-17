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
    st.error("⚠️ Lucky Lab Keys Missing. Add ALPACA_KEY and ALPACA_SECRET to Streamlit Secrets.")
    st.stop()

# --- 3. CREATE TABS ---
tab1, tab2 = st.tabs(["🔍 Strategy Optimizer", "📓 Lucky Ledger"])

# --- TAB 1: STRATEGY OPTIMIZER ---
with tab1:
    st.subheader("Naked Put Scanner")
    col_a, col_b, col_c = st.columns([1, 1, 1])
    ticker_scan = col_a.text_input("Ticker Symbol", value="SPY", key="scan_ticker_input").upper()
    safety_threshold = col_b.slider("Minimum Safety %", 70, 99, 90, key="safety_slider")
    min_vol = col_c.number_input("Min Volume", value=0, key="vol_input")

    if st.button("🔬 Run Lab Analysis", key="run_scan_btn"):
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
                                "Strike": round(strike_from_sym, 1),
                                "Safety %": round(prob_otm, 1),
                                "Premium": f"${mid:.2f}", 
                                "Ann. ROC %": round(ann_roc, 1),
                                "Volume": getattr(data, 'volume', 0)
                            })
                if results:
                    st.dataframe(pd.DataFrame(results).sort_values("Ann. ROC %", ascending=False), use_container_width=True)
                else:
                    st.warning("No matches found.")
            except Exception as e:
                st.error(f"Scanner Error: {e}")

# --- TAB 2: LUCKY LEDGER ---
with tab2:
    st.subheader("📓 The Lucky Ledger")

    desired_cols = ["Ticker", "Type", "Strike", "Expiry", "Premium", "Qty", "Commission", "Total Profit"]
    
    if 'journal_data' not in st.session_state:
        st.session_state.journal_data = pd.DataFrame(columns=desired_cols)
    else:
        # Maintenance: strip old "Date" column if it persists
        if "Date" in st.session_state.journal_data.columns:
            st.session_state.journal_data = st.session_state.journal_data.drop(columns=["Date"])

    # 1. TOP METRICS
    numeric_profit = pd.to_numeric(st.session_state.journal_data["Total Profit"], errors='coerce').fillna(0)
    overall_p = numeric_profit.sum()
    
    m1, m2 = st.columns(2)
    m1.metric("Net Profit (After Fees)", f"${overall_p:,.2f}")
    m2.metric("Portfolio Status", "Online" if overall_p >= 0 else "Pending Recovery")
    st.divider()

    # 2. ENTRY FORM
    with st.expander("➕ Log New Trade", expanded=True):
        c1, c2, c3 = st.columns(3)
        new_ticker = c1.text_input("Ticker", value="SPY", key="ledger_ticker_input").upper()
        strategy = c2.selectbox("Strategy", options=["Short Put", "Short Call"], index=0, key="strat_select")
        qty = c3.number_input("Qty", min_value=1, value=1, key="qty_input")

        c4, c5 = st.columns(2)
        expiry_date = c4.date_input("Expiry Date", value=datetime.now().date(), key="expiry_picker")
        target_strike = c5.number_input("Target Strike", value=None, step=0.1, format="%.1f", placeholder="Enter Strike...", key="strike_input")
        
        if st.button("🚀 Fetch & Commit", key="commit_btn"):
            if target_strike is None:
                st.error("Please enter a strike price.")
            else:
                try:
                    is_expired = expiry_date < datetime.now().date()
                    flag = "P" if strategy == "Short Put" else "C"
                    strike_str = f"{int(round(target_strike, 1) * 1000):08d}"
                    formatted_expiry = expiry_date.strftime("%y%m%d")
                    opt_symbol = f"{new_ticker}{formatted_expiry}{flag}{strike_str}"
                    p_val = 0.0

                    if is_expired:
                        end_dt = datetime.combine(expiry_date, datetime.now().time())
                        start_dt = end_dt - timedelta(days=7)
                        req = OptionBarsRequest(symbol_or_symbols=opt_symbol, timeframe=TimeFrame.Day, start=start_dt, end=end_dt)
                        res = opt_client.get_option_bars(req)
                        if opt_symbol in res.data and len(res.data[opt_symbol]) > 0:
                            p_val = res.data[opt_symbol][-1].close
                    else:
                        chain = opt_client.get_option_chain(OptionChainRequest(underlying_symbol=new_ticker, expiration_date=expiry_date))
                        if opt_symbol in chain:
                            data = chain[opt_symbol]
                            p_val = (data.bid_price + data.ask_price) / 2
                            if p_val == 0: p_val = getattr(data, 'last_price', 0.05)

                    if p_val > 0:
                        # --- IBKR TIERED CALCULATION ---
                        # Premium in dollars per contract (e.g., 0.59 -> 59)
                        premium_received = round(p_val * 100, 2)
                        
                        # Commission logic
                        base = 0.65 if p_val >= 0.10 else (0.50 if p_val >= 0.05 else 0.25)
                        order_comm = max(1.00, (base + 0.045) * qty)
                        
                        # Total Profit = (Premium * Qty) - Commission
                        net_profit = (premium_received * qty) - order_comm
                        
                        new_row = {
                            "Ticker": new_ticker,
                            "Type": strategy, 
                            "Strike": round(target_strike, 1), 
                            "Expiry": expiry_date.strftime("%Y-%m-%d"),
                            "Premium": premium_received, # Now showing raw 59, 110, etc.
                            "Qty": int(qty),
                            "Commission": round(order_comm, 2),
                            "Total Profit": round(net_profit, 2)
                        }
                        st.session_state.journal_data = pd.concat([st.session_state.journal_data, pd.DataFrame([new_row])], ignore_index=True)
                        st.rerun()
                    else:
                        st.error(f"Could not find price for {opt_symbol}")
                except Exception as e:
                    st.error(f"Error: {e}")

    # 3. HISTORY TABLE
    st.write("### Trade History")
    st.session_state.journal_data = st.data_editor(st.session_state.journal_data, num_rows="dynamic", use_container_width=True, key="ledger_editor")

    if st.button("🗑️ Reset Ledger"):
        st.session_state.journal_data = pd.DataFrame(columns=desired_cols)
        st.rerun()

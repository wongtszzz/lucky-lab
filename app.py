import streamlit as st
import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import norm

# --- Page Configuration ---
st.set_page_config(page_title="Short Put Analyzer", layout="wide")

st.title("📉 Short Put Options Analyzer")
st.markdown("""
This tool calculates the **Greeks** and **Probability of Profit** for selling put options. 
Enter your trade details in the sidebar to see the analysis.
""")

# --- Sidebar Inputs ---
st.sidebar.header("Trade Parameters")
S = st.sidebar.number_input("Current Stock Price ($)", value=100.0, step=1.0)
K = st.sidebar.number_input("Strike Price ($)", value=95.0, step=1.0)
premium = st.sidebar.number_input("Premium Collected ($)", value=2.50, step=0.10)
T_days = st.sidebar.number_input("Days to Expiration", value=30, step=1, min_value=1)
r_input = st.sidebar.number_input("Risk-Free Rate (%)", value=4.5, step=0.1) 
sigma_input = st.sidebar.number_input("Implied Volatility (%)", value=30.0, step=1.0) 

# Convert percentages and days for Black-Scholes math
r = r_input / 100
sigma = sigma_input / 100
T = T_days / 365.0

# --- Black-Scholes Math & Greeks ---
# Intermediate calculations d1 and d2
d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
d2 = d1 - sigma * np.sqrt(T)

# Normal distribution functions
N_d1 = norm.cdf(d1)
N_d2 = norm.cdf(d2)
N_neg_d2 = norm.cdf(-d2)
pdf_d1 = norm.pdf(d1)

# Calculate Greeks from the perspective of the SELLER (Short Put)
# We calculate the standard long put greeks first, then invert them
short_delta = -(norm.cdf(d1) - 1)
short_gamma = -(pdf_d1 / (S * sigma * np.sqrt(T)))
short_theta = -((- (S * pdf_d1 * sigma) / (2 * np.sqrt(T)) + r * K * np.exp(-r * T) * N_neg_d2) / 365)
short_vega = -((S * pdf_d1 * np.sqrt(T)) / 100)

# Trade Metrics
prob_profit = N_d2 * 100  # Probability stock stays above strike
breakeven = K - premium
max_profit = premium * 100
max_loss = (K - premium) * 100

# --- Dashboard Layout ---
st.divider()
col1, col2, col3, col4 = st.columns(4)
col1.metric("Max Profit", f"${max_profit:.2f}", help="Total premium kept if stock stays above strike.")
col2.metric("Max Risk", f"${max_loss:.2f}", help="Total loss if the stock price goes to zero.")
col3.metric("Breakeven", f"${breakeven:.2f}", help="The stock price where you stop losing money.")
col4.metric("Prob. of Profit", f"{prob_profit:.1f}%", help="Theoretical chance the option expires worthless.")

st.subheader("Position Greeks")
g1, g2, g3, g4 = st.columns(4)
g1.metric("Delta", f"{short_delta:.4f}", help="Price sensitivity. How much you make if the stock goes up $1.")
g2.metric("Gamma", f"{short_gamma:.4f}", help="How much your Delta changes for every $1 the stock moves.")
g3.metric("Theta", f"{short_theta:.4f}", help="Time decay. How much profit you gain per day just by waiting.")
g4.metric("Vega", f"{short_vega:.4f}", help="Volatility risk. How much you lose if Implied Volatility rises 1%.")

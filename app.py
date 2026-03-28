import streamlit as st
import pandas as pd
import numpy as np
import io
import base64
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
from github import Github

# --- 1. CONFIG & API ---
st.set_page_config(page_title="Lucky Quants Lab", page_icon="🧪", layout="wide")

st.markdown("""
<style>
    [data-testid="metric-container"] {
        background-color: rgba(28, 131, 225, 0.05); 
        border: 1px solid rgba(128, 128, 128, 0.2);
        border-radius: 12px;
        padding: 15px;
        height: 140px; 
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        text-align: center;
        margin-bottom: 15px;
    }
    [data-testid="stMetricValue"] { font-size: 2rem !important; font-weight: 800 !important; }
    [data-testid="stMetricDelta"] { font-size: 1rem !important; color: #888888 !important; justify-content: center !important; }
    [data-testid="stMetricDelta"] > svg { display: none; }
    .footer-right { position: fixed; bottom: 10px; right: 10px; color: gray; font-size: 0.8em; z-index: 1000; }
    
    .creed-box {
        background-color: rgba(128, 128, 128, 0.05); 
        border: 1px solid rgba(128, 128, 128, 0.2);
        border-left: 5px solid #2962FF; 
        border-radius: 8px;
        padding: 15px 20px;
        margin-bottom: 25px;
    }
    .creed-title {
        font-weight: 800;
        font-size: 1.1em;
        margin-bottom: 10px;
        color: #2962FF;
        letter-spacing: 0.5px;
    }
    .creed-text {
        font-size: 0.95em;
        line-height: 1.6;
    }
</style>
""", unsafe_allow_html=True)

st.markdown("### 🧪 Lucky Quants Lab | Pre-Market War Room")
st.divider()

# API Connections (Stripped out Alpaca to maximize speed; using yfinance for macro data)
try:
    GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]
    GITHUB_REPO = st.secrets["GITHUB_REPO"]
    gh = Github(GITHUB_TOKEN)
    repo = gh.get_repo(GITHUB_REPO)
except Exception as e:
    st.error(f"Secrets Error. Check Streamlit Settings. {e}")
    st.stop()

# --- 2. LOGIC & DATA ENGINE ---
FILE_PATH = "lucky_ledger.csv"
COLS = ["Date", "Ticker", "Type", "Strike", "Expiry", "Open Price", "Close Price", "Qty", "Commission", "Premium", "Status"]

def sort_ledger(df):
    if df.empty: return df
    df['temp_date'] = pd.to_datetime(df['Date'], errors='coerce')
    
    def rank_status(s):
        s = str(s)
        if "Open" in s: return 1
        if "Win" in s: return 2
        if "Loss" in s: return 3
        return 4
        
    df['status_rank'] = df['Status'].apply(rank_status)
    df = df.sort_values(by=['temp_date', 'status_rank'], ascending=[False, True])
    df['Date'] = df['temp_date'].dt.strftime('%Y-%m-%d')
    return df.drop(columns=['temp_date', 'status_rank']).reset_index(drop=True)

def save_journal(df):
    try:
        df_sorted = sort_ledger(df)
        csv_content = df_sorted[COLS].to_csv(index=False)
        commit_message = f"Ledger Auto-Sync: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        try:
            contents = repo.get_contents(FILE_PATH)
            repo.update_file(contents.path, commit_message, csv_content, contents.sha)
        except:
            repo.create_file(FILE_PATH, "Initial commit", csv_content)
        st.session_state.last_update = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    except Exception as e:
        st.error(f"GitHub Sync Failed: {e}")

def load_journal():
    try:
        contents = repo.get_contents(FILE_PATH)
        decoded_content = base64.b64decode(contents.content).decode('utf-8')
        df = pd.read_csv(io.StringIO(decoded_content))
        
        for c in COLS:
            if c not in df.columns:
                if c == "Date": df[c] = datetime.now().strftime("%Y-%m-%d")
                else: df[c] = 0.0 if c in ["Open Price", "Close Price", "Premium", "Commission"] else (1 if c == "Qty" else "Unknown")
        return sort_ledger(df[COLS])
    except Exception as e:
        if "404" in str(e): return pd.DataFrame(columns=COLS)
        else:
            st.error(f"⚠️ Emergency Stop: Could not connect to GitHub. Error: {e}")
            st.stop()

if 'journal' not in st.session_state or set(st.session_state.journal.columns) != set(COLS): 
    st.session_state.journal = load_journal()
    st.session_state.last_update = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# Global variable for the macro VIX
if 'current_vix' not in st.session_state:
    st.session_state.current_vix = 20.0

# --- 3. UI TABS ---
tab1, tab_chart, tab2 = st.tabs(["⚡ Macro & Safe Zones", "📈 Technical Battlefield", "📓 Lucky Ledger"])

# --- TAB 1: MACRO & IDEA GENERATION (LIGHTNING FAST) ---
with tab1:
    col_market, col_calc = st.columns(2, gap="large")
    
    with col_market:
        head_col, btn_col = st.columns([3, 1])
        with head_col:
            st.markdown("#### 🌍 Market Temperature")
        with btn_col:
            st.button("🔄 Refresh", use_container_width=True)
            
        st.caption("Live baseline metrics for the broader market.")
        
        try:
            def get_yf_metrics(symbol):
                t = yf.Ticker(symbol)
                df = t.history(period='5d')
                if len(df) >= 2:
                    prev = float(df['Close'].iloc[-2])
                    curr = float(df['Close'].iloc[-1])
                    pct = ((curr - prev) / prev) * 100
                    return curr, pct
                return 0.0, 0.0
            
            spy_px, spy_pct = get_yf_metrics("SPY")
            qqq_px, qqq_pct = get_yf_metrics("QQQ")
            vix_px, vix_pct = get_yf_metrics("^VIX")
            
            st.session_state.current_vix = vix_px if vix_px > 0 else 20.0
            
            m1, m2 = st.columns(2)
            m1.metric("S&P 500 (SPY)", f"${spy_px:,.2f}", f"{spy_pct:+.2f}%")
            m2.metric("Nasdaq (QQQ)", f"${qqq_px:,.2f}", f"{qqq_pct:+.2f}%")
            
            market_daily_expected_pct = st.session_state.current_vix / np.sqrt(252)
            
            m3, m4 = st.columns(2)
            m3.metric("Volatility (VIX)", f"{vix_px:,.2f}", f"{vix_pct:+.2f}%", delta_color="inverse")
            m4.metric("SPY 1-Day Exp. Move", f"± {market_daily_expected_pct:.2f}%", "Rule of 16 Baseline", delta_color="off")
            
            if vix_px > 25:
                st.warning("🚨 **High Volatility:** The VIX is elevated. Premiums are rich, but market conditions are dangerous. Size down your trades.")
            elif vix_px < 15:
                st.info("📉 **Low Volatility:** The market is calm. Premiums are cheap. Be careful not to over-leverage just to chase yield.")
            else:
                st.success("⚖️ **Normal Volatility:** Market is in a standard operating range.")

        except Exception as e:
            st.error(f"Error fetching market data: {e}")

    with col_calc:
        st.markdown("#### 🛡️ Safe Zone Calculator")
        st.caption("Instantly calculates your mathematical floor and ceiling for any ticker.")
        
        c1, c2 = st.columns(2)
        calc_tk = c1.text_input("Ticker", value="TSLA", key="calc_tk").upper()
        calc_ex = c2.date_input("Target Expiry", datetime.now().date() + timedelta(days=7))
        
        if st.button("🧮 Calculate Safe Zones", type="primary", use_container_width=True):
            with st.spinner(f"Crunching quant math for {calc_tk}..."):
                try:
                    yf_tk = yf.Ticker(calc_tk)
                    hist_df = yf_tk.history(period='5d')
                    
                    if hist_df.empty:
                        st.error("Invalid Ticker or No Data Found.")
                    else:
                        px = float(hist_df['Close'].iloc[-1])
                        
                        # Get Beta
                        try:
                            beta = yf_tk.info.get('beta', 1.0)
                            if beta is None: beta = 1.0
                        except:
                            beta = 1.0
                            
                        # Days to Expiry Math
                        days_to_exp = (calc_ex - datetime.now().date()).days
                        if days_to_exp <= 0: days_to_exp = 1 
                        
                        # THE QUANT FORMULA
                        stock_iv_proxy = st.session_state.current_vix * beta
                        exp_move_pct = (stock_iv_proxy / 100) * np.sqrt(days_to_exp / 365)
                        exp_move_dollar = px * exp_move_pct
                        
                        safe_put_floor = px - exp_move_dollar
                        safe_call_ceiling = px + exp_move_dollar
                        
                        st.markdown(f"### **{calc_tk} Current Price: ${px:.2f}**")
                        st.write(f"**Beta:** {beta:.2f} | **Timeframe:** {days_to_exp} Days | **Expected Swing:** ± {exp_move_pct*100:.1f}% (± ${exp_move_dollar:.2f})")
                        
                        # Big visual output for the trader
                        t1, t2 = st.columns(2)
                        with t1:
                            st.info(f"🟢 **SAFE PUT FLOOR**\n# **${safe_put_floor:.2f}**\n*Do not sell puts above this price.*")
                        with t2:
                            st.error(f"🔴 **SAFE CALL CEILING**\n# **${safe_call_ceiling:.2f}**\n*Do not sell calls below this price.*")
                            
                        st.caption("💡 *Take these numbers to your broker (Futu/IBKR) and look for the highest Premium/ROC sitting OUTSIDE these zones!*")
                except Exception as e:
                    st.error(f"Calculation Error: {e}")

# --- TAB 2: CHART ANALYSIS (UNCHANGED) ---
with tab_chart:
    st.markdown("#### 📈 Technical Battlefield")
    st.caption("Visualize 1-Year trends, multiple EMAs, ATR Volatility, and Keltner Channels.")
    
    chart_col1, chart_col2 = st.columns([1, 4])
    
    with chart_col1:
        chart_tk = st.text_input("Ticker to Chart", value="SPY", key="chart_tk2").upper()
        
        st.write("**Indicator Toggles**")
        show_ema_fast = st.checkbox("Show 20 & 50 EMA", value=True)
        show_ema_slow = st.checkbox("Show 100 & 200 EMA", value=False)
        show_kc = st.checkbox("Show Keltner Channels (KC)", value=True)
        show_sr = st.checkbox("Show Support/Resistance", value=True)
        
        draw_btn = st.button("📊 Draw Chart", use_container_width=True, type="primary")
        st.write("---")
        atr_placeholder = st.empty()
        
    with chart_col2:
        if draw_btn:
            with st.spinner(f"Crunching technicals and generating chart for {chart_tk}..."):
                try:
                    ticker_data = yf.Ticker(chart_tk)
                    df_chart = ticker_data.history(period="1y")
                    
                    if df_chart.empty:
                        st.error(f"Could not pull chart data for {chart_tk}.")
                    else:
                        df_chart['EMA_20'] = df_chart['Close'].ewm(span=20, adjust=False).mean()
                        df_chart['EMA_50'] = df_chart['Close'].ewm(span=50, adjust=False).mean()
                        df_chart['EMA_100'] = df_chart['Close'].ewm(span=100, adjust=False).mean()
                        df_chart['EMA_200'] = df_chart['Close'].ewm(span=200, adjust=False).mean()
                        
                        high_low = df_chart['High'] - df_chart['Low']
                        high_close = np.abs(df_chart['High'] - df_chart['Close'].shift())
                        low_close = np.abs(df_chart['Low'] - df_chart['Close'].shift())
                        ranges = pd.concat([high_low, high_close, low_close], axis=1)
                        true_range = np.max(ranges, axis=1)
                        df_chart['ATR_14'] = true_range.rolling(14).mean()
                        
                        current_atr = df_chart['ATR_14'].iloc[-1]
                        atr_placeholder.metric("14-Day ATR", f"${current_atr:.2f}", help="The average dollar amount this stock moves per day.")
                        
                        df_chart['KC_Upper'] = df_chart['EMA_20'] + (2 * df_chart['ATR_14'])
                        df_chart['KC_Lower'] = df_chart['EMA_20'] - (2 * df_chart['ATR_14'])
                        
                        c_ema20 = df_chart['EMA_20'].iloc[-1]
                        c_ema50 = df_chart['EMA_50'].iloc[-1]
                        c_ema100 = df_chart['EMA_100'].iloc[-1]
                        c_ema200 = df_chart['EMA_200'].iloc[-1]
                        c_kcu = df_chart['KC_Upper'].iloc[-1]
                        c_kcl = df_chart['KC_Lower'].iloc[-1]
                        
                        resistance = df_chart['High'].max()
                        support = df_chart['Low'].min()
                        current_close = df_chart['Close'].iloc[-1]
                        
                        bull_color = '#26A69A' 
                        bear_color = '#EF5350' 
                        vol_colors = [bull_color if row['Close'] >= row['Open'] else bear_color for index, row in df_chart.iterrows()]
                        
                        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                                            vertical_spacing=0.03, subplot_titles=(f'{chart_tk} Price Action', 'Volume'),
                                            row_width=[0.2, 0.7]) 

                        fig.add_trace(go.Candlestick(
                            x=df_chart.index, open=df_chart['Open'], high=df_chart['High'],
                            low=df_chart['Low'], close=df_chart['Close'], name=f'Price: ${current_close:.2f}',
                            increasing_line_color=bull_color, decreasing_line_color=bear_color
                        ), row=1, col=1)

                        if show_ema_fast:
                            fig.add_trace(go.Scatter(x=df_chart.index, y=df_chart['EMA_20'], mode='lines', name=f'20 EMA: ${c_ema20:.2f}', line=dict(color='#2962FF', width=1.5)), row=1, col=1)
                            fig.add_trace(go.Scatter(x=df_chart.index, y=df_chart['EMA_50'], mode='lines', name=f'50 EMA: ${c_ema50:.2f}', line=dict(color='#FF6D00', width=1.5)), row=1, col=1)

                        if show_ema_slow:
                            fig.add_trace(go.Scatter(x=df_chart.index, y=df_chart['EMA_100'], mode='lines', name=f'100 EMA: ${c_ema100:.2f}', line=dict(color='#9C27B0', width=1.5)), row=1, col=1)
                            fig.add_trace(go.Scatter(x=df_chart.index, y=df_chart['EMA_200'], mode='lines', name=f'200 EMA: ${c_ema200:.2f}', line=dict(color='#212121', width=2)), row=1, col=1)

                        if show_kc:
                            fig.add_trace(go.Scatter(x=df_chart.index, y=df_chart['KC_Upper'], mode='lines', name=f'KC Upper: ${c_kcu:.2f}', line=dict(color='rgba(128, 128, 128, 0.5)', width=1, dash='dot')), row=1, col=1)
                            fig.add_trace(go.Scatter(x=df_chart.index, y=df_chart['KC_Lower'], mode='lines', name=f'KC Lower: ${c_kcl:.2f}', line=dict(color='rgba(128, 128, 128, 0.5)', width=1, dash='dot'), fill='tonexty', fillcolor='rgba(128, 128, 128, 0.05)'), row=1, col=1)

                        if show_sr:
                            fig.add_trace(go.Scatter(x=df_chart.index, y=[resistance] * len(df_chart), mode='lines', name=f'Resist: ${resistance:.2f}', line=dict(color=bear_color, width=2, dash='dash')), row=1, col=1)
                            fig.add_trace(go.Scatter(x=df_chart.index, y=[support] * len(df_chart), mode='lines', name=f'Support: ${support:.2f}', line=dict(color=bull_color, width=2, dash='dash')), row=1, col=1)

                        fig.add_trace(go.Bar(
                            x=df_chart.index, y=df_chart['Volume'], name='Volume', marker_color=vol_colors, marker_line_width=0
                        ), row=2, col=1)

                        fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])], showgrid=False, zeroline=False)
                        fig.update_yaxes(showgrid=True, gridcolor='rgba(128,128,128,0.1)', zeroline=False)

                        fig.update_layout(
                            title=f"{chart_tk} Technical Analysis | Current Price: ${current_close:.2f}",
                            template="plotly_white", height=750, margin=dict(l=0, r=0, t=60, b=0),
                            showlegend=True, legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, traceorder="normal"),
                            xaxis_rangeslider_visible=False, bargap=0.1, hovermode="x unified" 
                        )
                        st.plotly_chart(fig, use_container_width=True)
                except Exception as e:
                    st.error(f"Error generating chart: {e}")
        else:
            st.info("👈 Use the toggles to clean up the chart, then click 'Draw Chart'.")

# --- TAB 3: LEDGER (UNCHANGED) ---
with tab2:
    st.markdown("""
    <div class="creed-box">
        <div class="creed-title">🧠 The Quants Creed</div>
        <div class="creed-text">
            <b>1. Hope is not a strategy.</b> Cut your losses mechanically.<br>
            <b>2. Watch the clock.</b> Beware of Market-on-Close (MOC) volatility and the notorious Friday Flush.
        </div>
    </div>
    """, unsafe_allow_html=True)

    df_j = st.session_state.journal
    realized_df = df_j[~df_j["Status"].astype(str).str.contains("Open", na=False)]
    total_realized = realized_df["Premium"].sum()
    total_closed = len(realized_df)
    wins = len(realized_df[realized_df["Status"].astype(str).str.contains("Win", na=False)])
    win_rate = (wins / total_closed * 100) if total_closed > 0 else 0.0
    active_df = df_j[df_j["Status"].astype(str).str.contains("Open", na=False)]
    active_count = len(active_df)
    capital_at_risk = (pd.to_numeric(active_df["Strike"]) * 100 * pd.to_numeric(active_df["Qty"])).sum()
    
    today = datetime.now().date()
    start_of_week = today - timedelta(days=today.weekday()) 
    end_of_week = start_of_week + timedelta(days=6) 
    
    df_j['temp_exp'] = pd.to_datetime(df_j['Expiry'], errors='coerce').dt.date
    this_week_df = df_j[(df_j['temp_exp'] >= start_of_week) & (df_j['temp_exp'] <= end_of_week)]
    weekly_profit = this_week_df["Premium"].sum()
    
    if not this_week_df.empty:
        best_row = this_week_df.loc[this_week_df["Premium"].idxmax()]
        worst_row = this_week_df.loc[this_week_df["Premium"].idxmin()]
        best_str = f"{best_row['Ticker']} (${best_row['Premium']:.0f})"
        worst_str = f"Worst: {worst_row['Ticker']} (${worst_row['Premium']:.0f})"
    else:
        best_str, worst_str = "No trades", "No trades"
    
    r1c1, r1c2 = st.columns(2)
    r1c1.metric("Total Realized 🤑", f"${total_realized:,.2f}", f"Win Rate: {win_rate:.1f}%", delta_color="off")
    r1c2.metric("Active Trades 📈", str(active_count), f"Capital at Risk: ${capital_at_risk:,.0f}", delta_color="off")
    
    r2c1, r2c2 = st.columns(2)
    r2c1.metric("This Week's P&L (Mon-Sun) 📅", f"${weekly_profit:,.2f}", "Based on Expiry Date", delta_color="off")
    r2c2.metric("Top Trade (This Week) 🏆", best_str, worst_str, delta_color="off")

    with st.expander("➕ Log New Trade", expanded=True):
        with st.form("new_trade_form", clear_on_submit=True):
            l1, l2, l3, l4 = st.columns(4)
            _raw_tk = l1.text_input("Ticker", placeholder="e.g. AAPL")
            n_ex = l2.date_input("Expiry", datetime.now().date() + timedelta(days=7))
            n_ty = l3.selectbox("Type", ["Short Put", "Short Call"])
            n_qt = l4.number_input("Qty", value=1, min_value=1)
            
            l5, l6 = st.columns(2)
            n_st = l5.number_input("Strike", value=None, format="%.1f", placeholder="e.g. 150.5")
            n_op = l6.number_input("Open Price", value=None, format="%.2f", placeholder="e.g. 0.85")
            
            submitted = st.form_submit_button("🚀 Commit Trade", use_container_width=True, type="primary")
            
            if submitted:
                n_tk = _raw_tk.upper() if _raw_tk else None
                if n_tk and n_st is not None and n_op is not None:
                    comm = round(n_qt * 1.05, 2)
                    net = round((float(n_op) * 100 * n_qt) - comm, 2)
                    stat = "Expired (Win)" if n_ex < datetime.now().date() else "Open / Active"
                    new_row = pd.DataFrame([{"Date": str(datetime.now().date()), "Ticker": n_tk, "Type": n_ty, "Strike": round(n_st, 1), "Expiry": str(n_ex), "Open Price": round(float(n_op), 2), "Close Price": 0.0, "Qty": n_qt, "Commission": comm, "Premium": net, "Status": stat}])
                    st.session_state.journal = pd.concat([df_j.drop(columns=['temp_exp'], errors='ignore'), new_row], ignore_index=True)
                    save_journal(st.session_state.journal)
                    st.rerun()
                else:
                    st.warning("⚠️ Please fill in the Ticker, Strike, and Open Price before committing.")

    st.write("### Trade History")
    
    def refresh_calculations(current_df):
        for col in ["Strike", "Open Price", "Close Price", "Qty", "Commission"]:
            current_df[col] = pd.to_numeric(current_df[col], errors='coerce').fillna(0)
        
        def update_row(r):
            open_p, close_p = float(r["Open Price"]), float(r["Close Price"])
            p = round(((open_p - close_p) * 100 * int(r["Qty"])) - float(r["Commission"]), 2)
            try: ex_d = pd.to_datetime(r["Expiry"]).date()
            except: ex_d = datetime.now().date()
            
            if close_p > 0: s = "Closed (Loss)" if close_p > open_p else "Closed (Win)"
            elif ex_d < datetime.now().date(): s = "Expired (Win)"
            else: s = "Open / Active"
            return pd.Series([p, s])
        
        current_df[["Premium", "Status"]] = current_df.apply(update_row, axis=1)
        return sort_ledger(current_df)

    edt = st.data_editor(
        st.session_state.journal.drop(columns=['temp_exp'], errors='ignore'), 
        num_rows="dynamic", use_container_width=True, key="ledger_editor_final",
        column_config={
            "Date": st.column_config.TextColumn("Date", help="YYYY-MM-DD"),
            "Strike": st.column_config.NumberColumn(format="%.2f"),
            "Open Price": st.column_config.NumberColumn(format="%.2f"),
            "Close Price": st.column_config.NumberColumn(format="%.2f"),
            "Commission": st.column_config.NumberColumn(format="$%.2f"),
            "Premium": st.column_config.NumberColumn(format="$%.2f")
        }
    )

    if not edt.equals(st.session_state.journal.drop(columns=['temp_exp'], errors='ignore')):
        updated_df = refresh_calculations(edt)
        st.session_state.journal = updated_df
        save_journal(updated_df)
        st.rerun()

st.markdown(f'<div class="footer-right">Last Synced to GitHub: {st.session_state.last_update}</div>', unsafe_allow_html=True)

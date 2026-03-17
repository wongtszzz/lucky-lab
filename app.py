with tab2:
    st.subheader("🧪 The Lucky Ledger")

    # --- 1. DASHBOARD METRICS ---
    if 'journal_data' not in st.session_state:
        # Initializing with a sample row to show formatting
        st.session_state.journal_data = pd.DataFrame(columns=["Date", "Ticker", "Strike", "Premium", "Qty", "Total Credit"])

    if not st.session_state.journal_data.empty:
        # Convert Date column to datetime to handle math
        df_metrics = st.session_state.journal_data.copy()
        df_metrics['Date'] = pd.to_datetime(df_metrics['Date'])
        
        # Calculations
        overall_profit = df_metrics["Total Credit"].sum()
        
        # Weekly Profit (Last 7 Days)
        seven_days_ago = datetime.now() - timedelta(days=7)
        weekly_profit = df_metrics[df_metrics['Date'] >= seven_days_ago]["Total Credit"].sum()

        # Display Metrics
        m1, m2 = st.columns(2)
        m1.metric("Overall Profit", f"${overall_profit:,.2f}", help="Total premium banked since day one.")
        m2.metric("Last 7 Days", f"${weekly_profit:,.2f}", delta=f"{weekly_profit:,.2f}", help="Sum of premiums logged in the last week.")
        st.divider()

    # --- 2. QUICK ENTRY FORM ---
    with st.expander("➕ Log New Trade", expanded=True):
        c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
        new_ticker = c1.text_input("Ticker", value="SPY", key="journal_ticker").upper()
        weeks_out = c2.selectbox("Weeks to Expiry", options=[1, 2, 3, 4, 5], index=0)
        qty = c3.number_input("Qty (Contracts)", min_value=1, value=1)
        
        # Calculate target Friday
        target_expiry = datetime.now() + timedelta(days=(4 - datetime.now().weekday() + (7 * weeks_out)) % (7 * weeks_out) or (7 * weeks_out))
        
        if st.button("🔍 Fetch & Stage Trade"):
            try:
                # Get Price
                price_data = stock_client.get_stock_latest_quote(StockLatestQuoteRequest(symbol_or_symbols=new_ticker, feed=DataFeed.IEX))
                current_p = price_data[new_ticker].ask_price
                
                # Fetch Chain
                chain_req = OptionChainRequest(underlying_symbol=new_ticker, expiration_date=target_expiry.date())
                chain = opt_client.get_option_chain(chain_req)
                
                # Auto-find a 'Safe' Strike (~95% of current price)
                best_strike = 0
                best_premium = 0
                for strike, data in chain.items():
                    if data.type == 'put' and data.strike < (current_p * 0.96):
                        best_strike = data.strike
                        best_premium = (data.bid_price + data.ask_price) / 2
                        break
                
                st.session_state.staged_trade = {
                    "Date": datetime.now().strftime("%Y-%m-%d"),
                    "Ticker": new_ticker,
                    "Strike": best_strike,
                    "Premium": best_premium,
                    "Qty": qty,
                    "Total Credit": round(best_premium * qty * 100, 2)
                }
                st.info(f"Staged: {new_ticker} ${best_strike}P Expiring {target_expiry.date()}")
            except Exception as e:
                st.error(f"Error fetching data: {e}")

    # --- 3. THE ADD BUTTON & TABLE ---
    if 'staged_trade' in st.session_state:
        if st.button("📥 Commit Trade to Ledger"):
            new_row = pd.DataFrame([st.session_state.staged_trade])
            st.session_state.journal_data = pd.concat([st.session_state.journal_data, new_row], ignore_index=True)
            del st.session_state.staged_trade
            st.rerun()

    edited_df = st.data_editor(
        st.session_state.journal_data, 
        num_rows="dynamic", 
        use_container_width=True,
        column_config={
            "Date": st.column_config.DateColumn(),
            "Total Credit": st.column_config.NumberColumn(format="$ %.2f"),
            "Premium": st.column_config.NumberColumn(format="$ %.2f")
        }
    )
    st.session_state.journal_data = edited_df

if st.button("🔍 Fetch & Stage Trade"):
            try:
                # 1. Calculate the target Friday
                target_expiry = datetime.now() + timedelta(days=(4 - datetime.now().weekday() + (7 * weeks_out)) % (7 * weeks_out) or (7 * weeks_out))
                
                # 2. Get Live Stock Price
                price_data = stock_client.get_stock_latest_quote(StockLatestQuoteRequest(symbol_or_symbols=new_ticker, feed=DataFeed.IEX))
                curr_p = price_data[new_ticker].ask_price
                
                # 3. Get Option Chain
                chain = opt_client.get_option_chain(OptionChainRequest(underlying_symbol=new_ticker, expiration_date=target_expiry.date()))
                
                # 4. Filter for Puts and find a 'Safe' Strike
                # Alpaca Symbols for puts look like 'AAPL260320P00150000' (The 'P' is the key)
                staged_found = False
                for symbol, data in chain.items():
                    # Check if symbol contains 'P' (Put) and strike is ~5% below current price
                    if "P" in symbol and data.strike < (curr_p * 0.95):
                        p_val = (data.bid_price + data.ask_price) / 2
                        
                        # Fallback if bid/ask is 0
                        if p_val == 0: p_val = data.last_price or 0.05
                        
                        st.session_state.staged = {
                            "Date": datetime.now().strftime("%Y-%m-%d"),
                            "Ticker": new_ticker,
                            "Strike": data.strike,
                            "Premium": p_val,
                            "Qty": qty,
                            "Total Credit": round(p_val * qty * 100, 2)
                        }
                        st.info(f"Staged: {new_ticker} ${data.strike}P | Total: ${st.session_state.staged['Total Credit']}")
                        staged_found = True
                        break
                
                if not staged_found:
                    st.warning("No safe puts found for this date. Try a different ticker or timeframe.")
                    
            except Exception as e:
                st.error(f"Fetch failed: {e}")

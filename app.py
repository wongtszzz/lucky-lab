if st.button("🚀 Fetch & Commit"):
            try:
                # 1. Determine if this is a Historical or Live request
                is_expired = expiry_date < datetime.now().date()
                flag = "P" if strategy == "Short Put" else "C"
                
                # Construct the Alpaca Option Symbol (e.g., SPY260320P00500000)
                # Strike needs to be 8 digits: 5 digits for dollars, 3 for cents
                strike_str = f"{int(target_strike * 1000):08d}"
                formatted_expiry = expiry_date.strftime("%y%m%d")
                opt_symbol = f"{new_ticker}{formatted_expiry}{flag}{strike_str}"

                p_val = 0.0

                if is_expired:
                    # --- HISTORICAL PATH ---
                    from alpaca.data.requests import OptionBarsRequest
                    from alpaca.data.timeframe import TimeFrame
                    
                    # Fetch the last price from the day it expired
                    end_dt = datetime.combine(expiry_date, datetime.max.time())
                    start_dt = end_dt - timedelta(days=1)
                    
                    req = OptionBarsRequest(symbol_or_symbols=opt_symbol, timeframe=TimeFrame.Day, start=start_dt, end=end_dt)
                    bars = opt_client.get_option_bars(req)
                    
                    if opt_symbol in bars.data and not bars.data[opt_symbol].empty:
                        # Use the 'close' price of the last trading day as the premium
                        p_val = bars.data[opt_symbol].iloc[-1].close
                    else:
                        st.error(f"Could not find historical data for {opt_symbol}. Check if the strike was valid.")
                else:
                    # --- LIVE PATH ---
                    chain = opt_client.get_option_chain(OptionChainRequest(underlying_symbol=new_ticker, expiration_date=expiry_date))
                    if opt_symbol in chain:
                        data = chain[opt_symbol]
                        p_val = (data.bid_price + data.ask_price) / 2
                        if p_val == 0: p_val = getattr(data, 'last_price', 0.05)
                
                if p_val > 0:
                    new_row = {
                        "Date": datetime.now().strftime("%Y-%m-%d"), 
                        "Ticker": new_ticker,
                        "Type": strategy, 
                        "Strike": target_strike, 
                        "Expiry": expiry_date.strftime("%Y-%m-%d"),
                        "Premium": float(p_val), 
                        "Qty": int(qty), 
                        "Total Credit": round(float(p_val) * qty * 100, 2)
                    }
                    st.session_state.journal_data = pd.concat([st.session_state.journal_data, pd.DataFrame([new_row])], ignore_index=True)
                    st.success(f"Successfully logged {strategy} at ${p_val}!")
                    st.rerun()
                elif not is_expired:
                    st.error("Strike not found in live chain.")

            except Exception as e:
                st.error(f"Lab Error: {e}")

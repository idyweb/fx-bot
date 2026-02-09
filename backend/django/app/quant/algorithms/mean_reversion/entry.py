"""
Aegis SMC Entry Algorithm - v2.0

The "Triple Threat" Entry System:
1. HTF Bias Filter (H4 Break of Structure)
2. Liquidity Sweep (Stop Hunt Detection)
3. Displacement + FVG (The Entry Zone)

This module implements a professional ICT/SMC entry strategy that requires
context before entry, not just pattern recognition.

Engineering Standard: O(n) complexity, Guard Clauses for early exit.
"""
import pandas as pd
import logging
import os
from dotenv import load_dotenv
from google import genai

from app.utils.arithmetics import (
    calculate_order_size_usd, calculate_commission, 
    get_price_at_pnl, convert_usd_to_lots
)
from app.utils.api.data import fetch_data_pos, symbol_info_tick
from app.utils.api.order import send_market_order
from app.utils.account import have_open_positions_in_symbol
from app.utils.market import is_market_open
from app.quant.indicators.mean_reversion import get_smc_setup
from app.quant.algorithms.mean_reversion.bias import get_market_bias, bias_confirms_signal
from app.quant.algorithms.mean_reversion.config import (
    PAIRS, MAIN_TIMEFRAME, SL_PNL_MULTIPLIER, TP_PNL_MULTIPLIER,
    LEVERAGE, DEVIATION, CAPITAL_PER_TRADE, AI_ENABLED, AI_MODEL
)
from app.utils.db.create import create_trade
from app.utils.notifications import send_telegram_notification

load_dotenv()
logger = logging.getLogger(__name__)
ai_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


def get_ai_approval(pair: str, data_snapshot: str, setup_details: dict) -> str:
    """
    The Agentic Vibe-Check with enhanced context.
    
    Now receives structured setup details from the SMC engine.
    """
    if not AI_ENABLED:
        logger.info(f"[AI] Bypass: Automatically approving {pair}")
        return "GO"

    try:
        system_instruction = (
            "Role: World-Class SMC Forex Analyst & Risk Controller. "
            "Primary Objective: Capital preservation. $50k annual growth target. "
            
            "Execution Framework: "
            "1. Liquidity Check: The system has detected a liquidity sweep. Verify it looks valid. "
            "2. Displacement: Was the move away from the sweep violent and energetic? "
            "3. FVG Validation: Is the Fair Value Gap fresh and in a high-probability zone? "
            "4. Market Regime: Is price in a clear trend or a valid reversal? Reject consolidation. "

            "Decision Logic: "
            "- Respond 'GO' ONLY if all criteria are met and the setup is 'textbook'. "
            "- Respond 'STOP' if there is ANY ambiguity, news-induced noise, or choppy action. "
            
            "Constraint: You are an execution engine. Output exactly ONE word: 'GO' or 'STOP'."
        )
        
        prompt = f"""
[CONTEXT]
Pair: {pair}
Setup Type: {setup_details.get('setup_type', 'UNKNOWN')}
Sweep Level: {setup_details.get('sweep_level', 'N/A')}
Entry Price: {setup_details.get('entry_price', 'N/A')}

[OHLC DATA (Recent 10 Bars)]
{data_snapshot}

[CRITERIA CHECK REQUEST]
- Liquidity Sweep: DETECTED (confirmed by code)
- Displacement Strength: ?
- FVG Quality: ?
- Trend Alignment: ?

Decision (GO/STOP)?"""
        
        response = ai_client.models.generate_content(
            model=AI_MODEL,
            contents=prompt,
            config=genai.types.GenerateContentConfig(system_instruction=system_instruction)
        )
        
        decision = response.text.strip().upper()
        # Sanitize response
        if "GO" in decision:
            decision = "GO"
        else:
            decision = "STOP"
        
        logger.info(f"[AI] {pair} Analysis -> {decision}")
        return decision
        
    except Exception as e:
        logger.warning(f"[AI Error] {e} -> Bypass Activated: Defaulting to GO")
        return "GO"


def entry_algorithm():
    """
    Main entry algorithm implementing the "Triple Threat" SMC strategy.
    
    Flow:
    1. Skip if market closed or position exists.
    2. Get HTF Bias (H4 BOS).
    3. Fetch M15 data and run SMC setup detection.
    4. Validate setup against HTF bias.
    5. Get AI approval.
    6. Execute trade.
    """
    try:
        for pair in PAIRS:
            # Guard Clause 1: Position or Market Check
            if have_open_positions_in_symbol(pair):
                continue
            if not is_market_open(pair):
                continue
            
            # Guard Clause 2: Margin Level Safety Check
            from app.utils.api.data import account_info
            acc = account_info()
            
            # Logic: Only enforce the 500% rule if we are actually using margin.
            # If margin is 0, we have 100% of our buying power available.
            if acc is not None and acc.get('margin', 0) > 0 and acc.get('margin_level', 9999) < 500:
                logger.warning(f"⚠️ High Risk: Margin Level at {acc.get('margin_level', 0):.1f}%. Skipping {pair}.")
                continue

            # Step 1: Get Higher Timeframe Bias
            htf_bias = get_market_bias(pair, htf_timeframe='H4', bars=100)
            logger.info(f"[Entry] {pair} HTF Bias: {htf_bias}")

            # Step 2: Fetch M15 Data (need more bars for sweep detection)
            df = fetch_data_pos(pair, MAIN_TIMEFRAME, 30)
            if df is None or df.empty:
                continue
            
            # Step 3: Run SMC Setup Detection
            setup = get_smc_setup(df, sweep_lookback=20, displacement_threshold=1.5)
            
            # Guard Clause 2: No valid setup found
            if setup is None:
                continue
            
            setup_type = setup['setup_type']  # 'BULLISH' or 'BEARISH'
            logger.info(f"[Entry] {pair} SMC Setup Detected: {setup_type}")
            
            # Step 4: Validate against HTF Bias
            if not bias_confirms_signal(htf_bias, setup_type):
                logger.info(f"[Entry] {pair} Skipped: {setup_type} signal conflicts with {htf_bias} bias.")
                continue
            
            # Step 5: Get AI Approval
            ai_decision = get_ai_approval(pair, df.tail(10).to_string(), setup)
            if ai_decision != "GO":
                logger.info(f"[Entry] {pair} Skipped: AI said STOP.")
                continue

            # Step 6: Execute Trade
            order_type = 'BUY' if setup_type == 'BULLISH' else 'SELL'
            tick_info = symbol_info_tick(pair)
            
            if tick_info is None or tick_info.empty:
                continue

            last_tick_price = tick_info['ask'].iloc[0] if order_type == 'BUY' else tick_info['bid'].iloc[0]
            price_decimals = len(str(last_tick_price).split('.')[-1])
            
            order_capital = CAPITAL_PER_TRADE
            order_size_usd = calculate_order_size_usd(order_capital, LEVERAGE)
            order_volume_lots = convert_usd_to_lots(pair, order_size_usd, order_type)
            
            if isinstance(order_volume_lots, (pd.Series, pd.DataFrame)):
                order_volume_lots = order_volume_lots.iloc[0] if not order_volume_lots.empty else 0.0

            # Guard Clause 3: Minimum lot size
            if order_volume_lots < 0.01:
                logger.info(f"[Entry] {pair} Skipped: Lot size {order_volume_lots} < 0.01 minimum.")
                continue

            commission = calculate_commission(order_size_usd, pair)
            
            # Calculate SL and TP
            point = tick_info.get('point', 0.00001)
            
            # Dynamic Min Dist: Max of (50 points, 2x Spread)
            # This protects against "Invalid Stops" during high volatility
            ask = tick_info['ask'].iloc[0]
            bid = tick_info['bid'].iloc[0]
            current_spread = ask - bid
            
            min_dist = max(50 * point, current_spread * 2)

            sl_price, _ = get_price_at_pnl(
                order_capital * SL_PNL_MULTIPLIER, last_tick_price, 
                order_size_usd, LEVERAGE, order_type, commission
            )
            tp_price, _ = get_price_at_pnl(
                order_capital * TP_PNL_MULTIPLIER, last_tick_price, 
                order_size_usd, LEVERAGE, order_type, commission
            )

            # Enforce Minimum Distance
            if order_type == 'BUY':
                if last_tick_price - sl_price < min_dist:
                    sl_price = last_tick_price - min_dist
                if tp_price - last_tick_price < min_dist:
                    tp_price = last_tick_price + min_dist
            else: # SELL
                if sl_price - last_tick_price < min_dist:
                    sl_price = last_tick_price + min_dist
                if last_tick_price - tp_price < min_dist:
                    tp_price = last_tick_price - min_dist

            order = send_market_order(
                symbol=pair, volume=order_volume_lots, order_type=order_type,
                sl=round(sl_price, price_decimals), tp=round(tp_price, price_decimals),
                deviation=DEVIATION, type_filling="ORDER_FILLING_FOK",
                position_size_usd=order_size_usd, commission=commission, 
                capital=order_capital, leverage=LEVERAGE
            )

            if order is not None:
                # TELEGRAM ALERT with full SMC v2.1 details
                inducement_status = "✅ SWEPT" if setup.get('inducement', {}).get('swept') else "⚠️ Not found"
                displacement_status = "✅ YES" if setup.get('displacement_found') else "⚠️ Weak"
                
                msg = (
                    f"🚀 *Aegis SMC v2.1 Trade Executed*\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"🔹 *Pair:* `{pair}`\n"
                    f"🔹 *Action:* `{order_type}`\n"
                    f"🔹 *Lots:* `{order_volume_lots}`\n"
                    f"🔹 *Entry:* `{last_tick_price}`\n"
                    f"🚩 *Stop Loss:* `{round(sl_price, price_decimals)}`\n"
                    f"🎯 *Take Profit:* `{round(tp_price, price_decimals)}`\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"📊 *HTF Bias:* `{htf_bias}`\n"
                    f"🎯 *Sweep Level:* `{setup.get('sweep_level', 'N/A')}`\n"
                    f"🔥 *Displacement:* {displacement_status}\n"
                    f"🪤 *Inducement:* {inducement_status}\n"
                    f"📍 *FVG Midpoint:* `{setup.get('fvg_midpoint', 'N/A')}`\n"
                    f"🤖 _AI Analysis: APPROVED_"
                )
                send_telegram_notification(msg)
                
                create_trade(
                    order, pair, order_capital, order_size_usd, LEVERAGE, 
                    commission, order_type, 'Exness', 'FOREX', 'AEGIS_SMC_V2.1', 
                    MAIN_TIMEFRAME, order_volume_lots, sl_price, tp_price
                )
                
                logger.info(f"[Entry] {pair} TRADE EXECUTED: {order_type} @ {last_tick_price} | Sweep: {setup.get('sweep_level')} | Inducement: {inducement_status}")

    except Exception as e:
        logger.error(f"Error in Aegis SMC v2.1 loop: {e}")
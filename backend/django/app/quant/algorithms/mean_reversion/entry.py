import pandas as pd
import logging
import os
import traceback
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
from app.quant.indicators.mean_reversion import smc_signals 
from app.quant.algorithms.mean_reversion.config import (
    PAIRS, MAIN_TIMEFRAME, SL_PNL_MULTIPLIER, TP_PNL_MULTIPLIER,
    LEVERAGE, DEVIATION, CAPITAL_PER_TRADE, AI_ENABLED, AI_MODEL
)
from app.utils.db.create import create_trade
from app.utils.notifications import send_telegram_notification

load_dotenv()
logger = logging.getLogger(__name__)
ai_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

def get_ai_approval(pair, data_snapshot, signal_type):
    """The Agentic Vibe-Check."""
    if not AI_ENABLED:
        logger.info(f"AI Bypass: Automatically approving {pair}")
        return "GO"

    try:
        system_instruction = (
            "You are a conservative Forex Sniper. Your goal is to protect capital. "
            "Analyze the market structure and 15m price action provided. "
            "Only approve high-probability setups with clear displacement and FVG retests. "
            "If the market looks choppy, consolidated, or uncertain, reply 'STOP'. "
            "If the setup is clean and aligns with trend or clear reversal, reply 'GO'. "
            "Reply strictly with only one word: 'GO' or 'STOP'."
        )
        
        prompt = f"Analyze {pair} ({signal_type}). OHLC Data:\n{data_snapshot}\nDecision:"
        
        response = ai_client.models.generate_content(
            model=AI_MODEL,
            contents=prompt,
            config=genai.types.GenerateContentConfig(system_instruction=system_instruction)
        )
        
        decision = response.text.strip().upper()
        # Sanitize response
        if "GO" in decision: decision = "GO"
        else: decision = "STOP"
        
        logger.info(f"[AI] {pair} Analysis -> {decision}")
        return decision
        
    except Exception as e:
        logger.error(f"[AI Error] {e} -> Defaulting to STOP")
        return "STOP"

def entry_algorithm():
    try:
        for pair in PAIRS:            
            if have_open_positions_in_symbol(pair) or not is_market_open(pair):
                continue

            df = fetch_data_pos(pair, MAIN_TIMEFRAME, 15)
            if df is None or df.empty:
                continue
            
            df['smc_signal'] = smc_signals(df)
            last_signal_row = df.iloc[-2]

            if last_signal_row['smc_signal'] in ['BULLISH_FVG', 'BEARISH_FVG']:
                signal_type = last_signal_row['smc_signal']
                ai_decision = get_ai_approval(pair, df.tail(5).to_string(), signal_type)
                
                if ai_decision != "GO":
                    continue

                order_type = 'BUY' if last_signal_row['smc_signal'] == 'BULLISH_FVG' else 'SELL'
                tick_info = symbol_info_tick(pair)
                if tick_info is None or tick_info.empty: continue

                last_tick_price = tick_info['ask'].iloc[0] if order_type == 'BUY' else tick_info['bid'].iloc[0]
                price_decimals = len(str(last_tick_price).split('.')[-1])
                
                order_capital = CAPITAL_PER_TRADE
                order_size_usd = calculate_order_size_usd(order_capital, LEVERAGE)
                order_volume_lots = convert_usd_to_lots(pair, order_size_usd, order_type)
                
                if isinstance(order_volume_lots, (pd.Series, pd.DataFrame)):
                    order_volume_lots = order_volume_lots.iloc[0] if not order_volume_lots.empty else 0.0

                if order_volume_lots < 0.01: continue

                commission = calculate_commission(order_size_usd, pair)
                
                # Calculate SL and TP
                sl_price, _ = get_price_at_pnl(order_capital * SL_PNL_MULTIPLIER, commission, order_size_usd, LEVERAGE, last_tick_price, order_type)
                tp_price, _ = get_price_at_pnl(order_capital * TP_PNL_MULTIPLIER, commission, order_size_usd, LEVERAGE, last_tick_price, order_type)

                order = send_market_order(
                    symbol=pair, volume=order_volume_lots, order_type=order_type,
                    sl=round(sl_price, price_decimals), tp=round(tp_price, price_decimals),
                    deviation=DEVIATION, type_filling="ORDER_FILLING_FOK",
                    position_size_usd=order_size_usd, commission=commission, capital=order_capital, leverage=LEVERAGE
                )

                if order is not None:
                    # TELEGRAM ALERT
                    msg = (
                        f"🚀 *Aegis SMC Trade Executed*\n"
                        f"━━━━━━━━━━━━━━━\n"
                        f"🔹 *Pair:* `{pair}`\n"
                        f"🔹 *Action:* `{order_type}`\n"
                        f"🔹 *Lots:* `{order_volume_lots}`\n"
                        f"🔹 *Entry:* `{last_tick_price}`\n"
                        f"🚩 *Stop Loss:* `{round(sl_price, price_decimals)}`\n"
                        f"🎯 *Take Profit:* `{round(tp_price, price_decimals)}`\n"
                        f"━━━━━━━━━━━━━━━\n"
                        f"🤖 _AI Analysis: APPROVED_"
                    )
                    send_telegram_notification(msg)
                    
                    create_trade(order, pair, order_capital, order_size_usd, LEVERAGE, commission, order_type, 'Exness', 'FOREX', 'AEGIS_SMC', MAIN_TIMEFRAME, order_volume_lots, sl_price, tp_price)

    except Exception as e:
        logger.error(f"Error in Aegis SMC loop: {e}")
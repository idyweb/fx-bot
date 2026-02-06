import pandas as pd
import requests
import logging
import os
import traceback
from dotenv import load_dotenv
from google import genai

from app.utils.arithmetics import (
    calculate_order_size_usd, calculate_commission, 
    get_price_at_pnl, get_pnl_at_price, convert_usd_to_lots
)
from app.utils.constants import MT5Timeframe
from app.utils.api.data import fetch_data_pos, symbol_info_tick
from app.utils.api.order import send_market_order
from app.utils.account import have_open_positions_in_symbol
from app.utils.market import is_market_open

from app.quant.indicators.mean_reversion import smc_signals 
from app.quant.algorithms.mean_reversion.config import (
    PAIRS, MAIN_TIMEFRAME, SL_PNL_MULTIPLIER, 
    LEVERAGE, DEVIATION, CAPITAL_PER_TRADE
)
from app.utils.db.create import create_trade

load_dotenv()
logger = logging.getLogger(__name__)

# Initialize the AI Context Agent
ai_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

def get_ai_approval(pair, data_snapshot):
    """The Agentic Vibe-Check: Final gatekeeper before execution."""
    try:
        prompt = f"Analyze {pair} M15 action: {data_snapshot}. Is this a high-probability reversal? Reply strictly 'GO' or 'STOP'."
        response = ai_client.models.generate_content(model="gemini-2.5-flash-lite", contents=prompt)
        return response.text.strip().upper()
    except Exception as e:
        logger.error(f"AI Agent Error: {e}")
        return "STOP" # Safety first: reject trade if AI fails

def entry_algorithm():
    try:
        for pair in PAIRS:            
            # 1. Basic Infrastructure Checks
            if have_open_positions_in_symbol(pair):
                continue

            if not is_market_open(pair):
                continue
                
            # 2. Fetch Fresh Data
            df = fetch_data_pos(pair, MAIN_TIMEFRAME, 15)
            if df is None or df.empty:
                continue
            
            # 3. Apply SMC Math (FVG detection)
            df['smc_signal'] = smc_signals(df)
            last_signal_row = df.iloc[-2] # Current completed candle

            # 4. Check for SMC Signal
            if last_signal_row['smc_signal'] in ['BULLISH_FVG', 'BEARISH_FVG']:
                logger.info(f"SMC Signal found for {pair}: {last_signal_row['smc_signal']}. Requesting AI approval...")
                
                # 5. Agentic Step: Get AI 'Go/No-Go'
                ai_decision = get_ai_approval(pair, df.tail(5).to_string())
                
                if ai_decision != "GO":
                    logger.info(f"AI Agent rejected {pair} trade.")
                    continue

                # 6. Execution Prep (Institutional Logic)
                order_type = 'BUY' if last_signal_row['smc_signal'] == 'BULLISH_FVG' else 'SELL'
                tick_info = symbol_info_tick(pair)
                if tick_info is None or tick_info.empty:
                    continue

                last_tick_price = tick_info['ask'].iloc[0] if order_type == 'BUY' else tick_info['bid'].iloc[0]
                price_decimals = len(str(last_tick_price).split('.')[-1])
                
                # Calculate size and SL
                order_capital = CAPITAL_PER_TRADE
                order_size_usd = calculate_order_size_usd(order_capital, LEVERAGE)
                order_volume_lots = convert_usd_to_lots(pair, order_size_usd, order_type)
                
                if isinstance(order_volume_lots, (pd.Series, pd.DataFrame)):
                    order_volume_lots = order_volume_lots.iloc[0] if not order_volume_lots.empty else 0.0

                if order_volume_lots < 0.01:
                    logger.error(f"Order volume too low for {pair}: {order_volume_lots}")
                    continue

                commission = calculate_commission(order_size_usd, pair)
                sl_price, _ = get_price_at_pnl(
                    desired_pnl=order_capital * SL_PNL_MULTIPLIER,
                    commission=commission,
                    order_size_usd=order_size_usd,
                    leverage=LEVERAGE,
                    entry_price=last_tick_price,
                    type=order_type
                )

                # 7. Execute Market Order
                order = send_market_order(
                    symbol=pair,
                    volume=order_volume_lots,
                    order_type=order_type,
                    sl=round(sl_price, price_decimals),
                    deviation=DEVIATION,
                    type_filling="ORDER_FILLING_FOK",
                    position_size_usd=order_size_usd,
                    commission=commission,
                    capital=order_capital,
                    leverage=LEVERAGE
                )

                # 8. Log Success to Database for Weekly Reviews
                if order is not None:
                    create_trade(
                        order, pair, order_capital, order_size_usd, 
                        LEVERAGE, commission, order_type, 'Exness',
                        'FOREX', 'AEGIS_SMC', MAIN_TIMEFRAME, order_volume_lots,
                        sl_price, None
                    )
                    logger.info(f"Aegis SMC Trade Executed for {pair}")
        
    except Exception as e:
        logger.error(f"Critical Exception in Aegis SMC loop: {e}\n{traceback.format_exc()}")
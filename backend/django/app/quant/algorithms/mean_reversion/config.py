from app.utils.constants import CRYPTOCURRENCIES, TIMEZONE, MT5Timeframe
import os


PAIRS = [
    # Crypto
    'BTCUSDm', 'ETHUSDm', 'BNBUSDm', 'SOLUSDm', 'HBARUSDm',
    # Forex
    'EURUSDm', 'EURGBPm', 'USDJPYm', 'USDCADm', 'USDCHFm', 'AUDUSDm', 'NZDUSDm',
    # Commodities
    'XAUUSDm', 'XAUEURm', 'XAGUSDm', 'XNGUSDm', 'USOILm', 'UKOILm'
]
MAIN_TIMEFRAME = MT5Timeframe.M15

TP_PNL_MULTIPLIER = 0.6   # Target profit = 60% of capital (1:3 risk:reward)
SL_PNL_MULTIPLIER = -0.2  # Max loss = 20% of capital (e.g., $2 on $10)


# Risk Management (Loaded from .env)
# Default to SAFE values if env variables are missing
LEVERAGE = int(os.getenv('RISK_LEVERAGE', 200))
DEVIATION = 20
CAPITAL_PER_TRADE = float(os.getenv('RISK_CAPITAL_PER_TRADE', 2.0)) # Default $2 margin per trade

# Partial Close Settings
PARTIAL_CLOSE_ENABLED = True
PARTIAL_CLOSE_TRIGGER = 0.30      # Trigger at +30% profit
PARTIAL_CLOSE_PERCENTAGE = 0.50   # Close 50% of position
PARTIAL_CLOSE_MIN_LOTS = 0.02     # Minimum lots required to partial close (can't split 0.01)

# AI Agent Settings
AI_ENABLED = True                 # Set to False to bypass AI check
AI_MODEL = "gemini-2.5-flash-lite"

# "Breathing Room" Trailing Logic
# 1. Early: Move to BE quickly (10% profit -> 1% lock)
# 2. Mid:  Give room to breathe (20% -> 10%, 40% -> 25%)
# 3. Late: Tighten up near TP (55% -> 45%)
TRAILING_STOP_STEPS = [
    {'trigger_pnl_multiplier': 0.10, 'new_sl_pnl_multiplier': 0.01}, # Move to tiny profit/BE
    {'trigger_pnl_multiplier': 0.20, 'new_sl_pnl_multiplier': 0.10}, # Lock in 10%
    {'trigger_pnl_multiplier': 0.40, 'new_sl_pnl_multiplier': 0.25}, # Lock in 25%
    {'trigger_pnl_multiplier': 0.55, 'new_sl_pnl_multiplier': 0.45}, # Tighten near TP
]
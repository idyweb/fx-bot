from app.utils.constants import CRYPTOCURRENCIES, TIMEZONE, MT5Timeframe

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
LEVERAGE = 200
DEVIATION = 20
CAPITAL_PER_TRADE = 10

# Partial Close Settings
PARTIAL_CLOSE_ENABLED = True
PARTIAL_CLOSE_TRIGGER = 0.30      # Trigger at +30% profit
PARTIAL_CLOSE_PERCENTAGE = 0.50   # Close 50% of position
PARTIAL_CLOSE_MIN_LOTS = 0.02     # Minimum lots required to partial close (can't split 0.01)

# AI Agent Settings
AI_ENABLED = False                 # Set to False to bypass AI check
AI_MODEL = "gemini-2.5-flash-lite"

TRAILING_STOP_STEPS = [
    {'trigger_pnl_multiplier': 4.00, 'new_sl_pnl_multiplier': 3.50},
    {'trigger_pnl_multiplier': 3.50, 'new_sl_pnl_multiplier': 3.00},
    {'trigger_pnl_multiplier': 3.00, 'new_sl_pnl_multiplier': 2.75},
    {'trigger_pnl_multiplier': 2.75, 'new_sl_pnl_multiplier': 2.50},
    {'trigger_pnl_multiplier': 2.50, 'new_sl_pnl_multiplier': 2.25},
    {'trigger_pnl_multiplier': 2.25, 'new_sl_pnl_multiplier': 2.00},
    {'trigger_pnl_multiplier': 2.00, 'new_sl_pnl_multiplier': 1.75},
    {'trigger_pnl_multiplier': 1.75, 'new_sl_pnl_multiplier': 1.50},
    {'trigger_pnl_multiplier': 1.50, 'new_sl_pnl_multiplier': 1.25},
    {'trigger_pnl_multiplier': 1.25, 'new_sl_pnl_multiplier': 1.00},
    {'trigger_pnl_multiplier': 1.00, 'new_sl_pnl_multiplier': 0.75},
    {'trigger_pnl_multiplier': 0.75, 'new_sl_pnl_multiplier': 0.45},
    {'trigger_pnl_multiplier': 0.50, 'new_sl_pnl_multiplier': 0.22},
    {'trigger_pnl_multiplier': 0.25, 'new_sl_pnl_multiplier': 0.12},
    {'trigger_pnl_multiplier': 0.12, 'new_sl_pnl_multiplier': 0.05},
    {'trigger_pnl_multiplier': 0.06, 'new_sl_pnl_multiplier': 0.025},
]
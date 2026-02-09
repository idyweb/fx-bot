from app.utils.constants import CRYPTOCURRENCIES, TIMEZONE, MT5Timeframe
import os


# V3 SAFETY PATCH: Reduced to top 5 high-liquidity pairs only
# This reduces noise and over-trading on thin markets
PAIRS = [
    'EURUSDm',   # Most liquid forex pair
    'GBPUSDm',   # High volatility, good trends
    'XAUUSDm',   # Gold - excellent for SMC
    'BTCUSDm',   # Bitcoin - crypto flagship
    'AUDUSDm',   # Clean trends, low news noise
]

# Timeframe: M15 for execution, H4 for bias (kept as is)
MAIN_TIMEFRAME = MT5Timeframe.M15

# Risk:Reward Multipliers (relative to capital risked)
TP_PNL_MULTIPLIER = 0.6   # Target profit = 60% of capital (1:3 risk:reward)
SL_PNL_MULTIPLIER = -0.2  # Max loss = 20% of capital (e.g., $2 on $10)


# =============================================================================
# V3 SAFETY PARAMETERS
# =============================================================================

# Risk Management (Loaded from .env)
LEVERAGE = int(os.getenv('RISK_LEVERAGE', 200))
DEVIATION = 20

# Dynamic Risk Sizing: Instead of fixed $20, risk 1.5% of current balance
# If balance is $130, risk = $1.95 per trade. If balance grows to $500, risk = $7.50.
RISK_PERCENT_PER_TRADE = float(os.getenv('RISK_PERCENT_PER_TRADE', 1.5))  # 1.5% of balance

# Fallback: If dynamic sizing fails, use this as capital per trade
CAPITAL_PER_TRADE = float(os.getenv('RISK_CAPITAL_PER_TRADE', 2.0))  # Default $2 margin per trade

# Symbol Cooldown: Prevent re-trading the same pair too quickly
# After closing a trade on a symbol, wait this many hours before entering again.
SYMBOL_COOLDOWN_HOURS = float(os.getenv('SYMBOL_COOLDOWN_HOURS', 1.0))  # 1 hour cooldown

# Drawdown Circuit Breaker: If daily realized losses exceed this %, halt trading.
# Sends Telegram alert and stops the bot until next trading day.
DAILY_DRAWDOWN_LIMIT_PERCENT = float(os.getenv('DAILY_DRAWDOWN_LIMIT_PERCENT', 5.0))  # 5% max daily loss


# =============================================================================
# V3.1 ENHANCEMENTS
# =============================================================================

# Trading Session Filter: Only trade during high-liquidity sessions
# SMC works best during London and New York. Asian session (2 AM WAT) has too many fakeouts.
# WAT = West Africa Time (UTC+1)
SESSION_FILTER_ENABLED = True
TRADING_SESSIONS = [
    # London Session (8 AM - 12 PM WAT)
    {'name': 'London', 'start_hour': 8, 'end_hour': 12},
    # New York Session (1 PM - 5 PM WAT)  
    {'name': 'NewYork', 'start_hour': 13, 'end_hour': 17},
]

# HTF Bias Filter: Skip trades when HTF bias is NEUTRAL
# NEUTRAL bias = choppy market = high chance of stop hunts with no follow-through
REJECT_NEUTRAL_BIAS = True

# Minimum Lot Size Floor: MT5 won't accept < 0.01 lots
# If dynamic sizing produces 0.005, we either:
# 1. Use 0.01 (minimum) but warn that risk is higher than intended
# 2. Skip the trade entirely if risk would exceed 3% of balance
MIN_LOT_SIZE = 0.01
MAX_RISK_PERCENT_OVERRIDE = 3.0  # If using min lot means risking > 3%, skip the trade


# =============================================================================
# PARTIAL CLOSE & TRAILING SETTINGS
# =============================================================================

# Partial Close Settings (Works with 3:1 TP)
# At 40% towards 3:1 target = ~1.2:1 RR locked on half the position
PARTIAL_CLOSE_ENABLED = True
PARTIAL_CLOSE_TRIGGER = 0.40      # Trigger at +40% towards TP (approx 1.2:1 RR)
PARTIAL_CLOSE_PERCENTAGE = 0.50   # Close 50% of position
PARTIAL_CLOSE_MIN_LOTS = 0.02     # Minimum lots required to partial close (can't split 0.01)

# AI Agent Settings
AI_ENABLED = True                 # Set to False to bypass AI check
AI_MODEL = "gemini-1.5-flash-8b"

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
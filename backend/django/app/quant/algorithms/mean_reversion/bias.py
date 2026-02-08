"""
Multi-Timeframe Bias Module

Implements Higher Timeframe (HTF) trend detection using Break of Structure (BOS).
This module provides the "Compass" for M15 entries - ensuring trades align with
institutional flow on H4.

Engineering Standard: Use BOS, not EMA (as per user specification).
"""
import pandas as pd
import logging
from app.utils.api.data import fetch_data_pos
from app.quant.indicators.mean_reversion import detect_swing_points

logger = logging.getLogger(__name__)


def detect_bos(df: pd.DataFrame, swing_lookback: int = 3) -> str:
    """
    Detects Break of Structure (BOS) on a given timeframe.
    
    A Bullish BOS: Price breaks above the most recent swing high.
    A Bearish BOS: Price breaks below the most recent swing low.
    
    Args:
        df: OHLC DataFrame.
        swing_lookback: Lookback for swing point detection.
        
    Returns:
        'BULLISH', 'BEARISH', or 'NEUTRAL'.
        
    Complexity: O(n)
    """
    if df is None or len(df) < swing_lookback * 3:
        return 'NEUTRAL'
    
    df = detect_swing_points(df.copy(), lookback=swing_lookback)
    
    # Find the last two swing highs and lows
    swing_highs = df[df['swing_high'].notna()]['swing_high'].tolist()
    swing_lows = df[df['swing_low'].notna()]['swing_low'].tolist()
    
    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return 'NEUTRAL'
    
    last_close = df['close'].iloc[-1]
    last_swing_high = swing_highs[-1]
    last_swing_low = swing_lows[-1]
    
    # Determine BOS
    # Bullish: Current close is above the last swing high
    if last_close > last_swing_high:
        return 'BULLISH'
    
    # Bearish: Current close is below the last swing low
    elif last_close < last_swing_low:
        return 'BEARISH'
    
    return 'NEUTRAL'


def get_market_bias(symbol: str, htf_timeframe: str = 'H4', bars: int = 100) -> str:
    """
    Determines the Higher Timeframe (HTF) market bias for a symbol.
    
    Uses Break of Structure (BOS) on the H4 timeframe to establish directional bias.
    This acts as a filter for M15 entries:
    - If H4 is BULLISH -> Only take BUY signals on M15.
    - If H4 is BEARISH -> Only take SELL signals on M15.
    - If H4 is NEUTRAL -> Can take either (or skip for safety).
    
    Args:
        symbol: Trading pair (e.g., 'BTCUSDm').
        htf_timeframe: Higher timeframe to check ('H4' or 'D1').
        bars: Number of bars to fetch for analysis.
        
    Returns:
        'LONG_ONLY', 'SHORT_ONLY', or 'NEUTRAL'.
        
    Complexity: O(n) where n = bars.
    """
    try:
        # Fetch higher timeframe data
        df = fetch_data_pos(symbol, htf_timeframe, bars)
        
        if df is None or df.empty:
            logger.warning(f"[Bias] No H4 data for {symbol}. Defaulting to NEUTRAL.")
            return 'NEUTRAL'
        
        # Detect BOS
        bos = detect_bos(df, swing_lookback=3)
        
        if bos == 'BULLISH':
            logger.info(f"[Bias] {symbol} H4 is BULLISH -> LONG_ONLY mode.")
            return 'LONG_ONLY'
        elif bos == 'BEARISH':
            logger.info(f"[Bias] {symbol} H4 is BEARISH -> SHORT_ONLY mode.")
            return 'SHORT_ONLY'
        else:
            logger.info(f"[Bias] {symbol} H4 is NEUTRAL -> No directional filter.")
            return 'NEUTRAL'
        
    except Exception as e:
        logger.error(f"[Bias] Error getting market bias for {symbol}: {e}")
        return 'NEUTRAL'


def bias_confirms_signal(bias: str, signal_type: str) -> bool:
    """
    Checks if the HTF bias confirms the M15 signal.
    
    Args:
        bias: 'LONG_ONLY', 'SHORT_ONLY', or 'NEUTRAL'.
        signal_type: 'BULLISH' or 'BEARISH'.
        
    Returns:
        True if bias confirms signal, False otherwise.
    """
    if bias == 'NEUTRAL':
        return True  # No filter, allow any signal
    
    if bias == 'LONG_ONLY' and signal_type == 'BULLISH':
        return True
    
    if bias == 'SHORT_ONLY' and signal_type == 'BEARISH':
        return True
    
    return False

"""
Smart Money Concepts (SMC) Indicator Engine - v2.1

This module implements institutional trading concepts with performance-optimized
vectorized operations:
1. Swing Points - Local highs/lows for structure (vectorized)
2. Liquidity Sweeps - Stop hunts above/below swing points (vectorized)
3. Displacement - High-momentum moves (body > 1.5x ATR)
4. Fair Value Gaps (FVG) - Imbalance zones with mitigation detection
5. Change of Character (CHoCH) - Structure shifts
6. Inducement - Internal sweep before FVG entry

Engineering Standard: O(n) time complexity via pandas vectorization.
"""
import pandas as pd
import pandas_ta as ta
import numpy as np
import logging

logger = logging.getLogger(__name__)


def detect_swing_points(df: pd.DataFrame, lookback: int = 5) -> pd.DataFrame:
    """
    Identifies local swing highs and swing lows using rolling window (vectorized).
    
    A swing high is a candle whose high is the maximum in a window of
    (2 * lookback + 1) candles centered on it.
    
    Args:
        df: OHLC DataFrame.
        lookback: Number of candles on each side to confirm a swing.
        
    Returns:
        DataFrame with 'swing_high' and 'swing_low' columns (price or NaN).
        
    Complexity: O(n) - vectorized rolling window
    """
    df = df.copy()
    window = lookback * 2 + 1
    
    # Rolling max/min centered on each bar
    rolling_high = df['high'].rolling(window=window, center=True).max()
    rolling_low = df['low'].rolling(window=window, center=True).min()
    
    # Mark swing points where the bar equals the rolling extreme
    df['swing_high'] = df['high'].where(df['high'] == rolling_high, np.nan)
    df['swing_low'] = df['low'].where(df['low'] == rolling_low, np.nan)
    
    return df


def detect_liquidity_sweep(df: pd.DataFrame, sweep_lookback: int = 20) -> pd.Series:
    """
    Detects Liquidity Sweeps (Stop Hunts) - VECTORIZED.
    
    A Bullish Sweep: Price wicks BELOW the lowest low of the last `sweep_lookback`
                     candles but CLOSES back inside the range.
    A Bearish Sweep: Price wicks ABOVE the highest high but CLOSES back inside.
    
    Args:
        df: OHLC DataFrame.
        sweep_lookback: Number of candles to look back for swing levels.
        
    Returns:
        Series with 'BULLISH_SWEEP', 'BEARISH_SWEEP', or None.
        
    Complexity: O(n) - vectorized rolling operations
    """
    # Rolling extremes, shifted to exclude current bar
    lowest_low = df['low'].rolling(window=sweep_lookback).min().shift(1)
    highest_high = df['high'].rolling(window=sweep_lookback).max().shift(1)
    
    # Bullish Sweep: Wick below lowest low, close back inside
    bullish_sweep = (df['low'] < lowest_low) & (df['close'] > lowest_low)
    
    # Bearish Sweep: Wick above highest high, close back inside
    bearish_sweep = (df['high'] > highest_high) & (df['close'] < highest_high)
    
    signals = pd.Series(None, index=df.index, dtype=object)
    signals[bullish_sweep] = 'BULLISH_SWEEP'
    signals[bearish_sweep] = 'BEARISH_SWEEP'
    
    return signals


def detect_displacement(df: pd.DataFrame, threshold: float = 1.5, atr_period: int = 14) -> pd.Series:
    """
    Detects Displacement (Violence / Momentum).
    
    A displacement candle has a body size greater than `threshold` times the ATR.
    Uses BODY size (open to close), not full candle (high to low).
    
    Args:
        df: OHLC DataFrame.
        threshold: Multiplier for ATR comparison.
        atr_period: Period for ATR calculation.
        
    Returns:
        Series with 'BULLISH_DISPLACEMENT', 'BEARISH_DISPLACEMENT', or None.
        
    Complexity: O(n)
    """
    df = df.copy()
    
    # Calculate ATR using pandas-ta
    df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=atr_period)
    
    # Calculate Body Size (absolute difference between open and close)
    df['body_size'] = (df['close'] - df['open']).abs()
    
    # Identify Displacement - BODY > threshold * ATR
    is_displaced = df['body_size'] > (df['atr'] * threshold)
    is_bullish = df['close'] > df['open']
    
    signals = pd.Series(None, index=df.index, dtype=object)
    signals[is_displaced & is_bullish] = 'BULLISH_DISPLACEMENT'
    signals[is_displaced & ~is_bullish] = 'BEARISH_DISPLACEMENT'
    
    return signals


def detect_fvg(df: pd.DataFrame) -> pd.DataFrame:
    """
    Detects Fair Value Gaps (FVG) / Imbalances with detailed gap info.
    
    A Bullish FVG: Gap between Candle[i-2] High and Candle[i] Low.
    A Bearish FVG: Gap between Candle[i-2] Low and Candle[i] High.
    
    Args:
        df: OHLC DataFrame.
        
    Returns:
        DataFrame with 'fvg_signal', 'fvg_top', 'fvg_bottom', 'fvg_midpoint' columns.
        
    Complexity: O(n)
    """
    df = df.copy()
    df['fvg_signal'] = None
    df['fvg_top'] = np.nan
    df['fvg_bottom'] = np.nan
    df['fvg_midpoint'] = np.nan

    for i in range(2, len(df)):
        # Bullish FVG: Current Low > High of 2 candles ago
        if df['low'].iloc[i] > df['high'].iloc[i - 2]:
            df.loc[df.index[i], 'fvg_signal'] = 'BULLISH_FVG'
            df.loc[df.index[i], 'fvg_top'] = df['low'].iloc[i]
            df.loc[df.index[i], 'fvg_bottom'] = df['high'].iloc[i - 2]
            df.loc[df.index[i], 'fvg_midpoint'] = df['high'].iloc[i - 2] + (df['low'].iloc[i] - df['high'].iloc[i - 2]) * 0.5
        
        # Bearish FVG: Current High < Low of 2 candles ago
        elif df['high'].iloc[i] < df['low'].iloc[i - 2]:
            df.loc[df.index[i], 'fvg_signal'] = 'BEARISH_FVG'
            df.loc[df.index[i], 'fvg_top'] = df['low'].iloc[i - 2]
            df.loc[df.index[i], 'fvg_bottom'] = df['high'].iloc[i]
            df.loc[df.index[i], 'fvg_midpoint'] = df['high'].iloc[i] + (df['low'].iloc[i - 2] - df['high'].iloc[i]) * 0.5

    return df


def is_fvg_mitigated(df: pd.DataFrame, fvg_index: int, fvg_type: str) -> bool:
    """
    Checks if an FVG has been "mitigated" using Consequent Encroachment (CE).
    
    The CE is the 50% midpoint of the FVG. If price has touched this level
    after the FVG formed, the gap is considered mitigated (dead).
    
    Args:
        df: OHLC DataFrame with FVG data.
        fvg_index: Index of the FVG bar.
        fvg_type: 'BULLISH_FVG' or 'BEARISH_FVG'.
        
    Returns:
        True if mitigated, False if still valid.
        
    Complexity: O(k) where k = bars after FVG
    """
    if fvg_index + 1 >= len(df):
        return False  # No subsequent bars to check
    
    if fvg_type == 'BULLISH_FVG':
        gap_top = df['low'].iloc[fvg_index]  # Low of FVG bar
        gap_bottom = df['high'].iloc[fvg_index - 2]  # High of bar 2 ago
        midpoint = gap_bottom + (gap_top - gap_bottom) * 0.5
        
        # Check if any subsequent candle's LOW touched the midpoint
        subsequent_lows = df['low'].iloc[fvg_index + 1:]
        return (subsequent_lows <= midpoint).any()
    
    elif fvg_type == 'BEARISH_FVG':
        gap_top = df['low'].iloc[fvg_index - 2]  # Low of bar 2 ago
        gap_bottom = df['high'].iloc[fvg_index]  # High of FVG bar
        midpoint = gap_bottom + (gap_top - gap_bottom) * 0.5
        
        # Check if any subsequent candle's HIGH touched the midpoint
        subsequent_highs = df['high'].iloc[fvg_index + 1:]
        return (subsequent_highs >= midpoint).any()
    
    return False


def detect_inducement(df: pd.DataFrame, fvg_index: int, fvg_type: str, lookback: int = 8) -> dict:
    """
    Detects Inducement - an internal swing point before the FVG that was swept.
    
    Inducement is a "trap" where retail traders are lured in early, stopped out,
    and then the real institutional move begins.
    
    Args:
        df: OHLC DataFrame with swing points.
        fvg_index: Index of the FVG bar.
        fvg_type: 'BULLISH_FVG' or 'BEARISH_FVG'.
        lookback: Bars to look back from FVG for internal swing.
        
    Returns:
        Dict with 'found', 'level', 'swept' keys.
        
    Complexity: O(lookback)
    """
    if fvg_index < lookback:
        return {'found': False, 'level': None, 'swept': False}
    
    # Get the window before the FVG
    start_idx = max(0, fvg_index - lookback)
    window = df.iloc[start_idx:fvg_index]
    
    if fvg_type == 'BULLISH_FVG':
        # Look for internal swing LOW before bullish FVG
        if window['swing_low'].notna().any():
            internal_low = window['swing_low'].dropna().iloc[-1]  # Most recent
            internal_low_idx = window[window['swing_low'] == internal_low].index[-1]
            
            # Check if this low was swept (price went below it)
            # Look at bars between internal low and FVG
            sweep_window = df.loc[internal_low_idx:df.index[fvg_index]]
            swept = (sweep_window['low'] < internal_low).any()
            
            return {
                'found': True,
                'level': internal_low,
                'swept': swept
            }
    
    elif fvg_type == 'BEARISH_FVG':
        # Look for internal swing HIGH before bearish FVG
        if window['swing_high'].notna().any():
            internal_high = window['swing_high'].dropna().iloc[-1]
            internal_high_idx = window[window['swing_high'] == internal_high].index[-1]
            
            # Check if this high was swept
            sweep_window = df.loc[internal_high_idx:df.index[fvg_index]]
            swept = (sweep_window['high'] > internal_high).any()
            
            return {
                'found': True,
                'level': internal_high,
                'swept': swept
            }
    
    return {'found': False, 'level': None, 'swept': False}


def detect_choch(df: pd.DataFrame, swing_lookback: int = 5) -> pd.Series:
    """
    Detects Change of Character (CHoCH) - Market Structure Shift.
    
    A Bullish CHoCH: In a downtrend, price closes ABOVE the most recent Lower High.
    A Bearish CHoCH: In an uptrend, price closes BELOW the most recent Higher Low.
    
    Args:
        df: OHLC DataFrame.
        swing_lookback: Lookback for swing point detection.
        
    Returns:
        Series with 'BULLISH_CHOCH', 'BEARISH_CHOCH', or None.
        
    Complexity: O(n)
    """
    df = detect_swing_points(df.copy(), lookback=swing_lookback)
    signals = pd.Series(None, index=df.index, dtype=object)
    
    # Forward fill swing points to get "current" structure levels
    last_swing_high = df['swing_high'].ffill()
    last_swing_low = df['swing_low'].ffill()
    
    # Bullish CHoCH: Close breaks above last swing high
    bullish_choch = df['close'] > last_swing_high.shift(1)
    signals[bullish_choch] = 'BULLISH_CHOCH'
    
    # Bearish CHoCH: Close breaks below last swing low
    bearish_choch = df['close'] < last_swing_low.shift(1)
    signals[bearish_choch] = 'BEARISH_CHOCH'
    
    return signals


def get_smc_setup(df: pd.DataFrame, sweep_lookback: int = 20, displacement_threshold: float = 1.5) -> dict:
    """
    Master function: Analyzes a DataFrame for a complete SMC v2.1 setup.
    
    The "Triple Threat" Setup with Inducement:
    1. Liquidity Sweep (stop hunt)
    2. Inducement (internal swing swept)
    3. Displacement (violence)
    4. Fair Value Gap (entry zone) - NOT mitigated
    
    Args:
        df: OHLC DataFrame (should have at least 30+ bars).
        sweep_lookback: Lookback for liquidity sweep detection.
        displacement_threshold: ATR multiplier for displacement.
        
    Returns:
        Dictionary with setup details or None if no valid setup.
        
    Complexity: O(n)
    """
    if df is None or len(df) < sweep_lookback + 10:
        return None
    
    # Run all detectors
    df = detect_swing_points(df.copy(), lookback=5)
    sweep_signals = detect_liquidity_sweep(df, sweep_lookback)
    displacement_signals = detect_displacement(df, displacement_threshold)
    df = detect_fvg(df)
    
    # Look for valid setups in the last 10 bars
    recent_bars = 10
    
    for i in range(len(df) - 1, max(len(df) - recent_bars - 1, sweep_lookback), -1):
        fvg_signal = df['fvg_signal'].iloc[i]
        
        if fvg_signal is None:
            continue
        
        fvg_type = fvg_signal  # 'BULLISH_FVG' or 'BEARISH_FVG'
        
        # Check 1: Is FVG mitigated?
        if is_fvg_mitigated(df, i, fvg_type):
            logger.info(f"[SMC] FVG at bar {i} is mitigated - skipping")
            continue
        
        # Check 2: Look for preceding sweep (within 5 bars before FVG)
        sweep_found = False
        sweep_bar = None
        for j in range(max(0, i - 5), i):
            if sweep_signals.iloc[j] is not None:
                sweep_direction = 'BULLISH' if sweep_signals.iloc[j] == 'BULLISH_SWEEP' else 'BEARISH'
                fvg_direction = 'BULLISH' if fvg_type == 'BULLISH_FVG' else 'BEARISH'
                
                # Sweep must align with FVG direction
                if sweep_direction == fvg_direction:
                    sweep_found = True
                    sweep_bar = j
                    break
        
        if not sweep_found:
            continue
        
        # Check 3: Inducement
        inducement = detect_inducement(df, i, fvg_type, lookback=8)
        
        # Check 4: Displacement (within 3 bars of sweep)
        displacement_found = False
        for k in range(sweep_bar, min(sweep_bar + 4, len(df))):
            if displacement_signals.iloc[k] is not None:
                disp_direction = 'BULLISH' if displacement_signals.iloc[k] == 'BULLISH_DISPLACEMENT' else 'BEARISH'
                fvg_direction = 'BULLISH' if fvg_type == 'BULLISH_FVG' else 'BEARISH'
                
                if disp_direction == fvg_direction:
                    displacement_found = True
                    break
        
        # Return setup if all conditions met
        setup_type = 'BULLISH' if fvg_type == 'BULLISH_FVG' else 'BEARISH'
        
        return {
            'setup_type': setup_type,
            'fvg_bar': i,
            'fvg_midpoint': df['fvg_midpoint'].iloc[i],
            'sweep_bar': sweep_bar,
            'sweep_level': df['low'].iloc[sweep_bar] if setup_type == 'BULLISH' else df['high'].iloc[sweep_bar],
            'displacement_found': displacement_found,
            'inducement': inducement,
            'entry_price': df['close'].iloc[-1],
        }
    
    return None


# Legacy function for backward compatibility
def smc_signals(data: pd.DataFrame) -> pd.Series:
    """
    [LEGACY] Simple FVG detection for backward compatibility.
    Use get_smc_setup() for the full "Triple Threat" analysis.
    """
    df = detect_fvg(data)
    return df['fvg_signal'] if 'fvg_signal' in df.columns else pd.Series(None, index=data.index)
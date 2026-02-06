import pandas as pd

def smc_signals(data):
    """
    Calculates SMC signals: Fair Value Gaps (FVG) and Liquidity Sweeps.
    """
    # Ensure DataFrame has OHLC
    if not all(col in data.columns for col in ['open', 'high', 'low', 'close']):
        return pd.Series(0, index=data.index)

    signals = pd.Series(0, index=data.index)

    for i in range(2, len(data)):
        # 1. Detect Bullish FVG (Gap between Candle i-2 High and Candle i Low)
        if data['low'].iloc[i] > data['high'].iloc[i-2]:
            signals.iloc[i] = 'BULLISH_FVG'
            
        # 2. Detect Bearish FVG (Gap between Candle i-2 Low and Candle i High)
        elif data['high'].iloc[i] < data['low'].iloc[i-2]:
            signals.iloc[i] = 'BEARISH_FVG'

    return signals
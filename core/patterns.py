import pandas as pd

def is_pin_bar(candle):
    open_p = candle['open']
    close_p = candle['close']
    high = candle['high']
    low = candle['low']
    total_range = high - low
    if total_range == 0:
        return False
    body = abs(close_p - open_p)
    upper_shadow = high - max(open_p, close_p)
    lower_shadow = min(open_p, close_p) - low
    return (upper_shadow / total_range > 0.6 or lower_shadow / total_range > 0.6) and (body / total_range < 0.3)

def is_outside_bar(candle, prev_candle):
    """Outside Bar (Внешний бар)"""
    return (candle['high'] > prev_candle['high']) and (candle['low'] < prev_candle['low'])

def is_inside_bar(candle, prev_candle):
    """Inside Bar (Внутренний бар / Инсайд-бар)"""
    return (candle['high'] < prev_candle['high']) and (candle['low'] > prev_candle['low'])

def is_ppr(candle, prev_candle):
    """PPR (Pivot Point Reversal)"""
    is_bearish_ppr = (candle['high'] > prev_candle['high']) and (candle['close'] < prev_candle['open'])
    is_bullish_ppr = (candle['low'] < prev_candle['low']) and (candle['close'] > prev_candle['open'])
    if is_outside_bar(candle, prev_candle):
        return False
    return is_bearish_ppr or is_bullish_ppr

def is_squat(candle, prev_candle=None):
    """Приседающий бар"""
    if prev_candle is None or 'volume' not in candle:
        return False
    spread = candle['high'] - candle['low']
    prev_spread = prev_candle['high'] - prev_candle['low']
    if spread == 0 or prev_spread == 0:
        return False
    return (candle['volume'] > prev_candle['volume']) and (spread < prev_spread)

def analyze_patterns(df: pd.DataFrame, is_historical: bool = False) -> list:
    if len(df) < 2:
        return []
        
    # Анализируем текущий формирующийся бар (df.iloc[-1]) за 5 мин до закрытия
    curr = df.iloc[-1]
    prev = df.iloc[-2]
    
    signals = []
    
    if is_pin_bar(curr):
        signals.append("Pin Bar")
    if is_outside_bar(curr, prev):
        signals.append("Outside Bar")
    elif is_inside_bar(curr, prev):
        signals.append("Inside Bar")
    elif is_ppr(curr, prev):
        signals.append("PPR")
        
    if is_squat(curr, prev):
        signals.append("Squat")
        
    return signals

import pandas as pd
from datetime import datetime, timezone, timedelta

MSK_TZ = timezone(timedelta(hours=3))

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
    return (candle['high'] > prev_candle['high']) and (candle['low'] < prev_candle['low'])

def is_inside_bar(candle, prev_candle):
    return (candle['high'] < prev_candle['high']) and (candle['low'] > prev_candle['low'])

def is_ppr(candle, prev_candle, prev_prev_candle):
    """
    Классический Pivot Point Reversal (ППР):
    1. Медвежий PPR:
       - prev_candle делает High выше, чем prev_prev_candle
       - candle делает High выше, чем prev_candle
       - candle закрывается НИЖЕ Low prev_candle (curr['close'] < prev['low'])
    2. Бычий PPR:
       - prev_candle делает Low ниже, чем prev_prev_candle
       - candle делает Low ниже, чем prev_candle
       - candle закрывается ВЫШЕ High prev_candle (curr['close'] > prev['high'])
    """
    is_bearish_ppr = (
        (prev_candle['high'] > prev_prev_candle['high']) and
        (candle['high'] > prev_candle['high']) and
        (candle['close'] < prev_candle['low'])
    )
    
    is_bullish_ppr = (
        (prev_candle['low'] < prev_prev_candle['low']) and
        (candle['low'] < prev_candle['low']) and
        (candle['close'] > prev_candle['high'])
    )
    
    if is_outside_bar(candle, prev_candle):
        return False
        
    return is_bearish_ppr or is_bullish_ppr

def is_squat(candle, prev_candle=None):
    if prev_candle is None or 'volume' not in candle:
        return False
    spread = candle['high'] - candle['low']
    prev_spread = prev_candle['high'] - prev_candle['low']
    if spread == 0 or prev_spread == 0:
        return False
    return (candle['volume'] > prev_candle['volume']) and (spread < prev_spread)

def analyze_patterns(df: pd.DataFrame, force_current: bool = False) -> list:
    if len(df) < 4:
        return []
        
    now = datetime.now(MSK_TZ)
    
    # Если запуск за 5 и менее минут до конца часа (минута >= 55) или принудительно -> берем текущий бар iloc[-1]
    # Если до конца часа больше 5 минут (минута < 55) -> берем полностью закрытый бар iloc[-2]
    if force_current or now.minute >= 55:
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        prev_prev = df.iloc[-3]
    else:
        curr = df.iloc[-2]
        prev = df.iloc[-3]
        prev_prev = df.iloc[-4]
        
    signals = []
    
    if is_pin_bar(curr):
        signals.append("Pin Bar")
    if is_outside_bar(curr, prev):
        signals.append("Outside Bar")
    elif is_inside_bar(curr, prev):
        signals.append("Inside Bar")
    elif is_ppr(curr, prev, prev_prev):
        signals.append("PPR")
        
    if is_squat(curr, prev):
        signals.append("Squat")
        
    return signals

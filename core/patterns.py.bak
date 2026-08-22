import pandas as pd
from datetime import datetime, timezone, timedelta

MSK_TZ = timezone(timedelta(hours=3))

def is_pin_bar(candle):
    high = float(candle['high'])
    low = float(candle['low'])
    open_p = float(candle['open'])
    close_p = float(candle['close'])
    total_range = high - low
    if total_range == 0:
        return False
    body = abs(close_p - open_p)
    upper_shadow = high - max(open_p, close_p)
    lower_shadow = min(open_p, close_p) - low
    
    # Классический пин-бар: длинный хвост > 60%, маленькое тело < 25%
    is_bull_pin = (lower_shadow / total_range >= 0.60) and (body / total_range <= 0.25)
    is_bear_pin = (upper_shadow / total_range >= 0.60) and (body / total_range <= 0.25)
    
    return is_bull_pin or is_bear_pin

def is_outside_bar(candle, prev_candle):
    return (float(candle['high']) > float(prev_candle['high'])) and (float(candle['low']) < float(prev_candle['low']))

def is_inside_bar(candle, prev_candle):
    return (float(candle['high']) <= float(prev_candle['high'])) and (float(candle['low']) >= float(prev_candle['low']))

def is_ppr(candle, prev_candle, prev_prev_candle):
    """
    Классический Pivot Point Reversal (ППР):
    1. Медвежий PPR:
       - prev_candle делает High выше, чем prev_prev_candle
       - candle закрывается НИЖЕ Low prev_candle
    2. Бычий PPR:
       - prev_candle делает Low ниже, чем prev_prev_candle
       - candle закрывается ВЫШЕ High prev_candle
    """
    c_close = float(candle['close'])
    c_high = float(candle['high'])
    c_low = float(candle['low'])
    
    p_high = float(prev_candle['high'])
    p_low = float(prev_candle['low'])
    
    pp_high = float(prev_prev_candle['high'])
    pp_low = float(prev_prev_candle['low'])

    if is_outside_bar(candle, prev_candle):
        return False

    is_bearish_ppr = (p_high > pp_high) and (c_close < p_low)
    is_bullish_ppr = (p_low < pp_low) and (c_close > p_high)
    
    return is_bearish_ppr or is_bullish_ppr

def is_fakey(curr, prev, prev_prev):
    """
    Fakey: prev_prev и prev формируют Inside Bar, а curr делал ложный пробой и вернулся.
    """
    if is_inside_bar(prev, prev_prev):
        mother_high = float(prev_prev['high'])
        mother_low = float(prev_prev['low'])
        c_close = float(curr['close'])
        c_high = float(curr['high'])
        c_low = float(curr['low'])
        
        # Ложный пробой вверх и возврат
        if c_high > mother_high and c_close < mother_high:
            return True
        # Ложный пробой вниз и возврат
        if c_low < mother_low and c_close > mother_low:
            return True
    return False

def is_squat(candle, prev_candle=None):
    if prev_candle is None or 'volume' not in candle or 'volume' not in prev_candle:
        return False
    spread = float(candle['high']) - float(candle['low'])
    prev_spread = float(prev_candle['high']) - float(prev_candle['low'])
    if spread == 0 or prev_spread == 0:
        return False
    return (float(candle['volume']) > float(prev_candle['volume'])) and (spread < prev_spread * 0.8)

def analyze_patterns(df: pd.DataFrame) -> tuple:
    if len(df) < 21:
        return "-", "🟡", ""

    curr = df.iloc[-2]       # Последняя полностью закрытая свеча
    prev = df.iloc[-3]       # Предыдущая
    prev_prev = df.iloc[-4]  # Пред-предыдущая
    
    close_p = float(curr["close"])

    # SMA 20 для определения тренда/направления
    sma20 = df["close"].astype(float).tail(21).iloc[:-1].mean()
    direction = "🟡" if close_p >= sma20 else "🔴"

    pats = []
    
    if is_fakey(curr, prev, prev_prev):
        pats.append("Fak")
    elif is_ppr(curr, prev, prev_prev):
        pats.append("PPR")
    elif is_pin_bar(curr):
        pats.append("Pin")
    elif is_outside_bar(curr, prev):
        pats.append("Out")
    elif is_inside_bar(curr, prev):
        pats.append("Ins")

    pat_str = "/".join(pats) if pats else "-"

    is_sq = is_squat(curr, prev)
    state_str = "🟦" if is_sq else ""

    return pat_str, direction, state_str

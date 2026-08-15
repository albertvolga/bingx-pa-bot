import pandas as pd

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
    
    is_bull_pin = (lower_shadow / total_range >= 0.55) and (body / total_range <= 0.30)
    is_bear_pin = (upper_shadow / total_range >= 0.55) and (body / total_range <= 0.30)
    return is_bull_pin or is_bear_pin

def is_outside_bar(candle, prev_candle):
    return (float(candle['high']) > float(prev_candle['high'])) and (float(candle['low']) < float(prev_candle['low']))

def is_inside_bar(candle, prev_candle):
    return (float(candle['high']) <= float(prev_candle['high'])) and (float(candle['low']) >= float(prev_candle['low']))

def is_ppr(candle, prev_candle, prev_prev_candle):
    c_close = float(candle['close'])
    p_high = float(prev_candle['high'])
    p_low = float(prev_candle['low'])
    pp_high = float(prev_prev_candle['high'])
    pp_low = float(prev_prev_candle['low'])

    # Единственное исключение: PPR не может быть Внешним баром (Outside Bar)
    if is_outside_bar(candle, prev_candle):
        return False

    is_bearish_ppr = (p_high > pp_high) and (c_close < p_low)
    is_bullish_ppr = (p_low < pp_low) and (c_close > p_high)
    return is_bearish_ppr or is_bullish_ppr

def is_fakey(curr, prev, prev_prev):
    """
    Fakey (Фейки): Внутренний бар (prev относительно prev_prev), 
    за которым следует ложный пробой (curr).
    """
    if is_inside_bar(prev, prev_prev):
        mother_high = float(prev_prev['high'])
        mother_low = float(prev_prev['low'])
        c_close = float(curr['close'])
        c_high = float(curr['high'])
        c_low = float(curr['low'])
        
        if c_high > mother_high and c_close < mother_high:
            return True
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

def analyze_patterns(df: pd.DataFrame) -> list:
    """Проверяет все паттерны параллельно без взаимного блокирования."""
    if len(df) < 4:
        return []

    curr = df.iloc[-1]
    prev = df.iloc[-2]
    prev_prev = df.iloc[-3]
    
    found_patterns = []
    
    # Все проверки идут независимо и сочетаются
    if is_fakey(curr, prev, prev_prev):
        found_patterns.append("Fak")
        
    if is_ppr(curr, prev, prev_prev):
        found_patterns.append("PPR")
        
    if is_pin_bar(curr):
        found_patterns.append("Pin")
        
    if is_outside_bar(curr, prev):
        found_patterns.append("Out")
        
    if is_inside_bar(curr, prev):
        found_patterns.append("Ins")
        
    return found_patterns

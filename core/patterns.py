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
    
    # Пин-бар: длинный хвост более 60% от всей свечи и маленькое тело
    if (upper_shadow / total_range > 0.6 or lower_shadow / total_range > 0.6) and (body / total_range < 0.3):
        return True
    return False

def is_outside_bar(candle, prev_candle):
    """
    Out (Outside Bar): High выше предыдущего High И Low ниже предыдущего Low.
    """
    return (candle['high'] > prev_candle['high']) and (candle['low'] < prev_candle['low'])

def is_ppr(candle, prev_candle):
    """
    PPR (Pivot Point Reversal):
    Медвежий PPR: High > Prev_High, но Close < Prev_Open.
    Бычий PPR: Low < Prev_Low, но Close > Prev_Open.
    """
    is_bearish_ppr = (candle['high'] > prev_candle['high']) and (candle['close'] < prev_candle['open'])
    is_bullish_ppr = (candle['low'] < prev_candle['low']) and (candle['close'] > prev_candle['open'])
    
    if is_outside_bar(candle, prev_candle):
        return False
        
    return is_bearish_ppr or is_bullish_ppr

def is_squat(candle, prev_candle=None):
    """Приседающий бар: рост объема при уменьшении спрэда/диапазона."""
    if prev_candle is None or 'volume' not in candle:
        return False
    spread = candle['high'] - candle['low']
    prev_spread = prev_candle['high'] - prev_candle['low']
    if spread == 0 or prev_spread == 0:
        return False
    return (candle['volume'] > prev_candle['volume']) and (spread < prev_spread)

def analyze_patterns(df: pd.DataFrame, is_historical: bool = False) -> list:
    if len(df) < 3:
        return []
        
    # Берём df.iloc[-2] как ПОСЛЕДНЮЮ ЗАКРЫТУЮ СВЕЧУ,
    # так как df.iloc[-1] — это текущий формирующийся бар на BingX
    curr = df.iloc[-2]
    prev = df.iloc[-3]
    
    signals = []
    
    if is_pin_bar(curr):
        signals.append("Pin Bar")
    if is_outside_bar(curr, prev):
        signals.append("Outside Bar")
    elif is_ppr(curr, prev):
        signals.append("PPR")
        
    if is_squat(curr, prev):
        signals.append("Squat")
        
    return signals

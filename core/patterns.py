import numpy as np
import pandas as pd

def normalize_candles(candles):
    """
    Приводит candles (DataFrame или list) к единому списку словарей dict
    """
    if candles is None:
        return []
    if isinstance(candles, pd.DataFrame):
        if candles.empty:
            return []
        # Приводим имена колонок к нижнему регистру для единообразия
        df = candles.copy()
        df.columns = [str(col).lower() for col in df.columns]
        return df.to_dict('records')
    if isinstance(candles, list):
        if not candles:
            return []
        normalized = []
        for c in candles:
            if isinstance(c, dict):
                normalized.append({str(k).lower(): v for k, v in c.items()})
        return normalized
    return []

def calculate_atr(candles, period=14):
    if len(candles) < period + 1:
        return 0.0
    tr_list = []
    for i in range(-period, 0):
        high = candles[i]['high']
        low = candles[i]['low']
        prev_close = candles[i-1]['close']
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        tr_list.append(tr)
    return float(np.mean(tr_list)) if tr_list else 0.0

def detect_pin_bar(candles):
    if len(candles) < 2:
        return None
    c = candles[-1]
    rng = c['high'] - c['low']
    if rng == 0:
        return None
    body = abs(c['close'] - c['open'])
    upper_tail = c['high'] - max(c['open'], c['close'])
    lower_tail = min(c['open'], c['close']) - c['low']
    
    if lower_tail >= 0.55 * rng and body <= 0.35 * rng:
        return "Pin"
    if upper_tail >= 0.55 * rng and body <= 0.35 * rng:
        return "Pin"
    return None

def detect_inside_bar(candles):
    if len(candles) < 2:
        return None
    mother = candles[-2]
    inside = candles[-1]
    if inside['high'] <= mother['high'] and inside['low'] >= mother['low']:
        return "Ins"
    return None

def detect_fakey(candles):
    if len(candles) < 3:
        return None
    mother = candles[-3]
    inside = candles[-2]
    signal = candles[-1]
    
    is_inside = (inside['high'] <= mother['high']) and (inside['low'] >= mother['low'])
    if not is_inside:
        return None
        
    if signal['low'] < inside['low'] and signal['close'] > inside['high']:
        return "Fak"
    if signal['high'] > inside['high'] and signal['close'] < inside['low']:
        return "Fak"
    return None

def detect_ppr(candles):
    if len(candles) < 3:
        return None
    c2 = candles[-3]
    c1 = candles[-2]
    c0 = candles[-1]
    
    if c1['high'] > c2['high'] and c0['close'] < c1['low']:
        return "PPR"
    if c1['low'] < c2['low'] and c0['close'] > c1['high']:
        return "PPR"
    return None

def detect_ud_bar(candles):
    if len(candles) < 2:
        return None
    prev = candles[-2]
    curr = candles[-1]
    prev_rng = prev['high'] - prev['low']
    if prev_rng == 0:
        return None
        
    if prev['close'] < prev['open'] and curr['close'] > curr['open']:
        if curr['close'] >= prev['high'] and curr['low'] >= (prev['low'] - 0.1 * prev_rng):
            return "UD"
    if prev['close'] > prev['open'] and curr['close'] < curr['open']:
        if curr['close'] <= prev['low'] and curr['high'] <= (prev['high'] + 0.1 * prev_rng):
            return "UD"
    return None

def detect_impossible_pattern(candles, atr_period=14, lookback=20):
    if len(candles) < max(atr_period + 1, lookback):
        return None
    curr = candles[-1]
    rng = curr['high'] - curr['low']
    if rng == 0:
        return None
        
    atr = calculate_atr(candles, period=atr_period)
    upper_tail = curr['high'] - max(curr['open'], curr['close'])
    lower_tail = min(curr['open'], curr['close']) - curr['low']
    
    recent_highs = [c['high'] for c in candles[-lookback-1:-1]]
    recent_lows = [c['low'] for c in candles[-lookback-1:-1]]
    
    if curr['high'] > max(recent_highs) and (upper_tail >= 0.7 * rng) and ((curr['close'] - curr['low']) <= 0.1 * rng) and (rng >= 2.0 * atr):
        return "Imp"
    if curr['low'] < min(recent_lows) and (lower_tail >= 0.7 * rng) and ((curr['high'] - curr['close']) <= 0.1 * rng) and (rng >= 2.0 * atr):
        return "Imp"
    return None

def detect_combo_pin_engulfing(candles):
    if len(candles) < 3:
        return None
    prev = candles[-2]
    curr = candles[-1]
    prev_rng = prev['high'] - prev['low']
    if prev_rng == 0:
        return None
        
    prev_body = abs(prev['close'] - prev['open'])
    prev_lower_tail = min(prev['open'], prev['close']) - prev['low']
    prev_upper_tail = prev['high'] - max(prev['open'], prev['close'])
    
    is_prev_bull_pin = (prev_lower_tail >= 0.55 * prev_rng) and (prev_body <= 0.35 * prev_rng)
    is_prev_bear_pin = (prev_upper_tail >= 0.55 * prev_rng) and (prev_body <= 0.35 * prev_rng)
    
    if is_prev_bull_pin and curr['close'] > prev['high']:
        return "Cmb"
    if is_prev_bear_pin and curr['close'] < prev['low']:
        return "Cmb"
    return None

def validate_pin_m15_structure(m15_candles):
    m15_list = normalize_candles(m15_candles)
    if not m15_list or len(m15_list) < 4:
        return True
    lows = [c['low'] for c in m15_list]
    min_idx = lows.index(min(lows))
    return min_idx <= 2 and m15_list[-1]['close'] > m15_list[min_idx]['low']

def analyze_patterns(candles, m15_candles=None):
    """
    Универсальная функция анализа паттернов с нормализацией входных данных
    """
    candle_list = normalize_candles(candles)
    if not candle_list or len(candle_list) < 3:
        return "-"
        
    cmb = detect_combo_pin_engulfing(candle_list)
    if cmb:
        return cmb
        
    imp = detect_impossible_pattern(candle_list)
    if imp:
        return imp
        
    fak = detect_fakey(candle_list)
    if fak:
        return fak
        
    ppr = detect_ppr(candle_list)
    if ppr:
        return ppr
        
    ud = detect_ud_bar(candle_list)
    if ud:
        return ud
        
    pin = detect_pin_bar(candle_list)
    if pin:
        if m15_candles and not validate_pin_m15_structure(m15_candles):
            pass
        else:
            return pin
            
    ins = detect_inside_bar(candle_list)
    if ins:
        return ins
        
    return "-"

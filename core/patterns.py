import numpy as np
import pandas as pd

def normalize_candles(candles):
    """
    Приводит candles (DataFrame или list) к единому списку словарей dict
    с колонками в нижнем регистре.
    """
    if candles is None:
        return []
    if isinstance(candles, pd.DataFrame):
        if candles.empty:
            return []
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

def calculate_atr(candles: list, period=14):
    """
    Рассчитывает Average True Range (ATR).
    """
    if len(candles) < period + 1:
        return 0.0
    
    df = pd.DataFrame(candles)
    # True Range (TR) = max[(High - Low), abs(High - Prev. Close), abs(Low - Prev. Close)]
    high_low = df['high'] - df['low']
    high_prev_close = abs(df['high'] - df['close'].shift(1))
    low_prev_close = abs(df['low'] - df['close'].shift(1))
    
    tr = pd.DataFrame({'high_low': high_low, 'high_prev_close': high_prev_close, 'low_prev_close': low_prev_close}).max(axis=1)
    
    # ATR - это SMA или EMA True Range. Здесь используем SMA.
    atr = tr.iloc[-period:].mean() # ATR по последним 'period' значениям
    return float(atr) if not pd.isna(atr) else 0.0

def calculate_sma(series, period):
    """
    Рассчитывает Simple Moving Average (SMA).
    """
    return series.rolling(window=period).mean()

def calculate_std(series, period):
    """
    Рассчитывает Standard Deviation (STD).
    """
    return series.rolling(window=period).std()

def calculate_bollinger_bands(candles_df: pd.DataFrame, period=20, num_std=2):
    """
    Рассчитывает Bollinger Bands (BB).
    Возвращает DataFrame с колонками 'middle', 'upper', 'lower'.
    """
    if len(candles_df) < period:
        return pd.DataFrame()
    
    df = candles_df.copy()
    df['middle'] = calculate_sma(df['close'], period)
    df['std'] = calculate_std(df['close'], period)
    df['upper'] = df['middle'] + df['std'] * num_std
    df['lower'] = df['middle'] - df['std'] * num_std
    return df[['middle', 'upper', 'lower']]

def calculate_keltner_channels(candles_df: pd.DataFrame, period_ema=20, period_atr=10, multiplier=2):
    """
    Рассчитывает Keltner Channels (KC).
    Возвращает DataFrame с колонками 'middle', 'upper', 'lower'.
    """
    if len(candles_df) < max(period_ema, period_atr):
        return pd.DataFrame()

    df = candles_df.copy()
    df['ema_close'] = df['close'].ewm(span=period_ema, adjust=False).mean()
    
    # True Range (TR)
    high_low = df['high'] - df['low']
    high_prev_close = abs(df['high'] - df['close'].shift(1))
    low_prev_close = abs(df['low'] - df['close'].shift(1))
    df['tr'] = pd.DataFrame({'high_low': high_low, 'high_prev_close': high_prev_close, 'low_prev_close': low_prev_close}).max(axis=1)
    
    df['atr'] = df['tr'].rolling(window=period_atr).mean()
    
    df['upper'] = df['ema_close'] + df['atr'] * multiplier
    df['lower'] = df['ema_close'] - df['atr'] * multiplier
    df['middle'] = df['ema_close']
    
    return df[['middle', 'upper', 'lower']]

def get_bb_direction_emoji(candles_df: pd.DataFrame) -> str:
    """
    Определяет направление тренда по трем средним линиям Боллинджера.
    🟡🟡🟡 - все 3 вверх, 🔴🔴🔴 - все 3 вниз, ⚪⚪⚪ - смешанное/флэт.
    """
    if len(candles_df) < 480 + 5: # Need enough data for 480 period BB and some slope
        return '⚪⚪⚪'

    periods = [20, 80, 480]
    directions = [] # 1 for up, -1 for down, 0 for flat/mixed

    for p in periods:
        bb = calculate_bollinger_bands(candles_df, period=p, num_std=2)
        if bb.empty or len(bb) < 5: # Need at least 5 points to determine slope
            directions.append(0)
            continue
        
        # Смотрим на наклон последних 5 точек средней линии
        middle_line = bb['middle'].iloc[-5:]
        slope = np.polyfit(np.arange(len(middle_line)), middle_line, 1)[0]
        
        # Определяем направление с учетом небольшой толерантности,
        # чтобы избежать ложных срабатываний на почти горизонтальных линиях.
        # Используем порог, зависящий от среднего значения линии, чтобы быть более адаптивным.
        # Например, 0.01% от средней цены за период.
        avg_price_for_period = middle_line.mean()
        # Если среднее значение 0, используем фиксированный минимальный порог
        slope_threshold = max(avg_price_for_period * 0.0001, 1e-6) 

        if slope > slope_threshold: # Если наклон положительный
            directions.append(1)
        elif slope < -slope_threshold: # Если наклон отрицательный
            directions.append(-1)
        else:
            directions.append(0)

    if all(d == 1 for d in directions):
        return '🟡🟡🟡' # Все вверх
    elif all(d == -1 for d in directions):
        return '🔴🔴🔴' # Все вниз
    else:
        return '⚪⚪⚪' # Смешанный или флэт

def get_candle_state_emoji(candles_df: pd.DataFrame) -> str:
    """
    Определяет состояние бара (Squat, Squeeze, Expansion).
    """
    if len(candles_df) < max(20, 10): # Для BB(20) и KC(20,10)
        return ''

    # Последняя свеча для анализа
    current_candle = candles_df.iloc[-1]
    prev_candle = candles_df.iloc[-2]

    # --- SQUAT (по Биллу Вильямсу) ---
    # Squat - это свеча, которая имеет очень узкое тело (close-open) 
    # и большой объем, а также находится на границе диапазона.
    # Более просто: большой объем при маленьком диапазоне close-open.
    # Требует расчета объема, который пока не добавлен в данные BingX.
    # Для текущих данных (без объема) - упрощенная логика: узкое тело.
    body_size = abs(current_candle['close'] - current_candle['open'])
    candle_range = current_candle['high'] - current_candle['low']
    
    # Если тело очень маленькое относительно диапазона свечи (например, < 10%)
    # Если тело очень маленькое относительно диапазона свечи (например, < 10%)
    # Для сквота (Squat) нужен объем и узкое тело.
    # Поскольку объем недоступен, временно используем упрощенную эвристику для Squat,
    # подразумевая, что это бар с маленьким телом относительно всего диапазона.
    if candle_range > 0 and body_size / candle_range < 0.15: # Узкое тело
        return '🔷' # Синий ромб (временная заглушка без анализа объема)

    # --- SQUEEZE / EXPANSION ---
    # Squeeze: Bollinger Bands сужаются и входят внутрь Keltner Channels.
    # Expansion: Bollinger Bands расширяются и выходят за Keltner Channels.
    bb = calculate_bollinger_bands(candles_df, period=20, num_std=2)
    kc = calculate_keltner_channels(candles_df, period_ema=20, period_atr=10, multiplier=2)

    if bb.empty or kc.empty or len(bb) < 2 or len(kc) < 2:
        return ''
    
    # Ширина BB и KC
    bb_width_curr = bb['upper'].iloc[-1] - bb['lower'].iloc[-1]
    kc_width_curr = kc['upper'].iloc[-1] - kc['lower'].iloc[-1]
    
    bb_width_prev = bb['upper'].iloc[-2] - bb['lower'].iloc[-2]
    kc_width_prev = kc['upper'].iloc[-2] - kc['lower'].iloc[-2]

    # Если BB уже, чем KC, и BB сужается
    is_squeeze = (bb_width_curr < kc_width_curr) and (bb_width_curr < bb_width_prev)
    # Если BB шире, чем KC, и BB расширяется
    is_expansion = (bb_width_curr > kc_width_curr) and (bb_width_curr > bb_width_prev)

    if is_squeeze:
        return '☀️' # Желтое солнце
    elif is_expansion:
        return '💥' # Взрыв

    return '' # По умолчанию пусто

# Паттерны Price Action
def detect_pin_bar(candles):
    if len(candles) < 2: return None
    c = candles[-1]
    rng = c['high'] - c['low']
    if rng == 0: return None
    body = abs(c['close'] - c['open'])
    upper_tail = c['high'] - max(c['open'], c['close'])
    lower_tail = min(c['open'], c['close']) - c['low']
    
    if lower_tail >= 0.55 * rng and body <= 0.35 * rng: return "Pin" # Бычий пин
    if upper_tail >= 0.55 * rng and body <= 0.35 * rng: return "Pin" # Медвежий пин
    return None

def detect_inside_bar(candles):
    if len(candles) < 2: return None
    mother = candles[-2]
    inside = candles[-1]
    if inside['high'] <= mother['high'] and inside['low'] >= mother['low']: return "Ins"
    return None

def detect_fakey(candles):
    if len(candles) < 3: return None
    mother = candles[-3]
    inside = candles[-2]
    signal = candles[-1]
    
    is_inside = (inside['high'] <= mother['high']) and (inside['low'] >= mother['low'])
    if not is_inside: return None
        
    if signal['low'] < inside['low'] and signal['close'] > inside['high']: return "Fak" # Бычий фейки
    if signal['high'] > inside['high'] and signal['close'] < inside['low']: return "Fak" # Медвежий фейки
    return None

def detect_ppr(candles):
    # Паттерн Price Action Reversal. Требует 3 бара.
    if len(candles) < 3: return None
    c2 = candles[-3] # 2 бара назад
    c1 = candles[-2] # 1 бар назад
    c0 = candles[-1] # Текущий бар
    
    # Бычий PPR: c1['high'] > c2['high'] и c0['close'] < c1['low']
    if c1['high'] > c2['high'] and c0['close'] < c1['low']: return "PPR"
    # Медвежий PPR: c1['low'] < c2['low'] и c0['close'] > c1['high']
    if c1['low'] < c2['low'] and c0['close'] > c1['high']: return "PPR"
    return None

def detect_ud_bar(candles):
    # Up-thrust (UD-бар) - обычно в комбинации с другими паттернами
    if len(candles) < 2: return None
    prev = candles[-2]
    curr = candles[-1]
    
    # Бычий UD (поглощение): текущая бычья свеча поглощает предыдущую медвежью
    if prev['close'] < prev['open'] and curr['close'] > curr['open'] and curr['close'] > prev['open'] and curr['open'] < prev['close']:
        return "UD" # Предположим, это бар поглощения, который пользователь назвал UD
    # Медвежий UD (поглощение): текущая медвежья свеча поглощает предыдущую бычью
    if prev['close'] > prev['open'] and curr['close'] < curr['open'] and curr['close'] < prev['open'] and curr['open'] > prev['close']:
        return "UD" # Предположим, это бар поглощения, который пользователь назвал UD
    return None

def detect_impossible_pattern(candles: list, atr_period=14, lookback=20):
    # Паттерн "Невозможный бар" - большой диапазон, маленький объем, закрытие близко к одному из экстремумов
    if len(candles) < max(atr_period + 1, lookback): return None
    curr = candles[-1]
    rng = curr['high'] - curr['low']
    if rng == 0: return None
        
    atr = calculate_atr(candles, period=atr_period)
    upper_tail = curr['high'] - max(curr['open'], curr['close'])
    lower_tail = min(curr['open'], curr['close']) - curr['low']
    
    # Смотрим на экстремумы за lookback баров (исключая текущий)
    recent_highs = [c['high'] for c in candles[-lookback-1:-1]]
    recent_lows = [c['low'] for c in candles[-lookback-1:-1]]
    
    # Бычий "Невозможный бар" (разворот вниз)
    if curr['high'] > max(recent_highs) and (upper_tail >= 0.7 * rng) and ((curr['close'] - curr['low']) <= 0.1 * rng) and (rng >= 2.0 * atr):
        return "Imp"
    # Медвежий "Невозможный бар" (разворот вверх)
    if curr['low'] < min(recent_lows) and (lower_tail >= 0.7 * rng) and ((curr['high'] - curr['close']) <= 0.1 * rng) and (rng >= 2.0 * atr):
        return "Imp"
    return None

def detect_combo_pin_engulfing(candles: list):
    # Комбинация пин-бара и поглощения
    if len(candles) < 3: return None
    prev = candles[-2]
    curr = candles[-1]
    prev_rng = prev['high'] - prev['low']
    if prev_rng == 0: return None
        
    prev_body = abs(prev['close'] - prev['open'])
    prev_lower_tail = min(prev['open'], prev['close']) - prev['low']
    prev_upper_tail = prev['high'] - max(prev['open'], prev['close'])
    
    is_prev_bull_pin = (prev_lower_tail >= 0.55 * prev_rng) and (prev_body <= 0.35 * prev_rng)
    is_prev_bear_pin = (prev_upper_tail >= 0.55 * prev_rng) and (prev_body <= 0.35 * prev_rng)
    
    # Если предыдущий бар был бычьим пин-баром, и текущий бар закрывается выше его High
    if is_prev_bull_pin and curr['close'] > prev['high']:
        return "Cmb"
    # Если предыдущий бар был медвежьим пин-баром, и текущий бар закрывается ниже его Low
    if is_prev_bear_pin and curr['close'] < prev['low']:
        return "Cmb"
    return None

def validate_pin_m15_structure(m15_candles: list):
    m15_list = normalize_candles(m15_candles)
    if not m15_list or len(m15_list) < 4: return True
    lows = [c['low'] for c in m15_list]
    min_idx = lows.index(min(lows))
    return min_idx <= 2 and m15_list[-1]['close'] > m15_list[min_idx]['low']

def analyze_patterns(candles: list, m15_candles: list = None) -> dict:
    """
    Универсальная функция анализа паттернов и состояния свечи.
    Возвращает словарь с паттерном, направлением BB и эмодзи состояния.
    """
    candle_list = normalize_candles(candles)
    if not candle_list or len(candle_list) < 3:
        return {"pattern": "-", "direction_bb": "⚪⚪⚪", "state_emoji": ""}
    
    df = pd.DataFrame(candle_list)

    # Детектируем паттерны
    detected_patterns = []

    cmb = detect_combo_pin_engulfing(candle_list)
    if cmb: detected_patterns.append(cmb)
        
    imp = detect_impossible_pattern(candle_list)
    if imp: detected_patterns.append(imp)
        
    fak = detect_fakey(candle_list)
    if fak: detected_patterns.append(fak)
        
    ppr = detect_ppr(candle_list)
    if ppr: detected_patterns.append(ppr)
        
    ud = detect_ud_bar(candle_list)
    if ud: detected_patterns.append(ud) # Временно, пока UD не станет полноценным поглощением

    pin = detect_pin_bar(candle_list)
    if pin: 
        if m15_candles and not validate_pin_m15_structure(m15_candles):
            pass # Не добавляем пин, если структура на М15 не подтверждена
        else:
            detected_patterns.append(pin)
            
    ins = detect_inside_bar(candle_list)
    if ins: detected_patterns.append(ins)
        
    pattern_str = "/".join(sorted(list(set(detected_patterns)))) if detected_patterns else "-"

    # Детектируем направление BB и состояние свечи
    direction_bb_emoji = get_bb_direction_emoji(df)
    state_emoji = get_candle_state_emoji(df)

    return {
        "pattern": pattern_str,
        "direction_bb": direction_bb_emoji,
        "state_emoji": state_emoji
    }

import logging
from datetime import datetime
from core.bingx.candles import fetch_bingx_candles
from core.patterns import analyze_patterns
from core.formatter import format_report, clean_symbol, MSK_TZ

logger = logging.getLogger(__name__)

# Список монет для сканирования
SYMBOLS = [
    "BTC-USDT", "ETH-USDT", "SOL-USDT", "LTC-USDT", 
    "ADA-USDT", "DOT-USDT", "ATOM-USDT", "XRP-USDT", 
    "DOGE-USDT", "KAS-USDT", "XAU-USDT", "XAG-USDT"
]

async def scan_timeframe_detailed(tf: str) -> list:
    """
    Детальное сканирование одного таймфрейма с логированием.
    Возвращает список сигналов.
    """
    signals = []
    now_msk = datetime.now(MSK_TZ)
    
    logger.info(f"🔍 Начало сканирования TF={tf} для {len(SYMBOLS)} монет...")
    
    for sym_full in SYMBOLS:
        try:
            # Запрашиваем 600 свечей для точного расчета BB(480)
            klines = await fetch_bingx_candles(sym_full, tf=tf, limit=600)
            
            if klines is None or klines.empty:
                logger.warning(f"⚠️ {sym_full} ({tf}): Нет данных (пустой ответ).")
                continue
                
            if len(klines) < 50: # Минимум для надежного анализа
                logger.warning(f"⚠️ {sym_full} ({tf}): Мало данных ({len(klines)}). Нужно >= 50.")
                continue

            # Преобразуем в список словарей для analyze_patterns
            candles_list = klines.to_dict('records')
            
            # Вызываем анализ
            pat_data = analyze_patterns(candles_list)
            
            # Логгируем результат анализа последней свечи
            last_close = float(candles_list[-1]['close'])
            pattern_found = pat_data.get("pattern") if pat_data else None
            
            if pattern_found and pattern_found != "-":
                logger.info(f"✅ {sym_full} ({tf}): Паттерн [{pattern_found}] на цене {last_close}")
                
                signals.append({
                    "symbol": clean_symbol(sym_full),
                    "tf": tf,
                    "pattern": pattern_found,
                    "direction_bb": pat_data.get("direction_bb", '⚪⚪⚪'),
                    "state_emoji": pat_data.get("state_emoji', ''),
                    "bb_breakthrough": pat_data.get("bb_breakthrough', ''),
                    "is_auto": False,
                    "timestamp": int(candles_list[-1].get('time', 0))
                })
            else:
                # Раскомментируйте следующую строку для ПОЛНОГО лога всех проверок (будет много мусора)
                # logger.debug(f"❌ {sym_full} ({tf}): Паттернов нет. Close={last_close}")
                pass
                
        except Exception as e:
            logger.error(f"❌ Ошибка сканирования {sym_full} {tf}: {e}", exc_info=True)
    
    logger.info(f"🏁 Сканирование {tf} завершено. Найдено сигналов: {len(signals)}")
    return signals

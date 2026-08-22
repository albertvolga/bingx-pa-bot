import logging
import pandas as pd
from core.bingx.candles import fetch_bingx_candles
from core.patterns import analyze_patterns

logging.basicConfig(level=logging.DEBUG)

SYMBOLS = ["BTC-USDT", "ETH-USDT", "SOL-USDT"]
TFS = ["1h", "4h", "1d"]

for tf in TFS:
    print(f"\n================ TIMEFRAME: {tf} ================")
    for sym in SYMBOLS:
        klines = fetch_bingx_candles(sym, tf=tf, limit=50)
        if klines is None or klines.empty:
            print(f"[{sym}] Ошибка получения свечей")
            continue
            
        candles_list = klines.to_dict('records')
        print(f"\n--- {sym} ({tf}) ---")
        print(f"Всего свечей: {len(candles_list)}")
        print(f"Последняя свеча: {candles_list[-1]}")
        
        try:
            res = analyze_patterns(candles_list)
            print(f"Результат analyze_patterns: {res}")
        except Exception as e:
            print(f"Исключение при анализе {sym}: {e}")
            import traceback
            traceback.print_exc()

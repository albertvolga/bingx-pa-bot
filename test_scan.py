import asyncio
from config import SYMBOL_MAP, TIMEFRAMES
from core.bingx.candles import fetch_bingx_candles
from core.patterns import analyze_patterns

def test():
    print("=== ТЕСТ СКАНИРОВАНИЯ ===")
    for symbol in list(SYMBOL_MAP.keys())[:2]:  # Проверим первые 2 актива
        for tf in TIMEFRAMES:
            print(f"\nЗапрос: {symbol} | TF: {tf}")
            df = fetch_bingx_candles(symbol, tf, limit=5)
            
            if df.empty:
                print("❌ Ошибка: DataFrame пустой!")
                continue
                
            print(f"Загружено свечей: {len(df)}")
            print("Последние 2 свечи:")
            print(df[['datetime_msk', 'open', 'high', 'low', 'close', 'volume']].tail(2))
            
            patterns = analyze_patterns(df, is_historical=False)
            print(f"Результат анализа: {patterns}")

if __name__ == "__main__":
    test()

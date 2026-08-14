from core.bingx.candles import fetch_bingx_candles
from core.patterns import analyze_patterns

df = fetch_bingx_candles("BTC-USDT", "1h", limit=30)
print(f"Загружено свечей: {len(df)}")

# Проверим последние 5 свечей по очереди
for i in range(2, 7):
    sub_df = df.iloc[:-i] if i > 1 else df
    last_candle = sub_df.iloc[-2]
    patterns = analyze_patterns(sub_df, is_historical=False)
    time_str = last_candle['datetime_msk'].strftime('%d.%m %H:%M')
    print(f"Свеча {time_str} (Close: {last_candle['close']}) -> Паттерны: {patterns}")

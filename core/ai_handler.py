import asyncio
from datetime import datetime, timezone, timedelta
from core.nlp_parser import parse_user_intent
from core.database import add_alert, get_all_alerts, delete_alert
from core.fetcher import fetch_klines

MSK_TZ = timezone(timedelta(hours=3))

def clean_symbol(symbol: str) -> str:
    if not symbol:
        return "BTC"
    symbol = symbol.upper().replace("-USDT", "").replace("USDT", "")
    return symbol

def format_alerts_table(chat_id: int):
    alerts = get_all_alerts(chat_id=chat_id)
    if not alerts:
        return "🔔 <b>У вас нет активных алертов.</b>", None

    lines = []
    lines.append("<pre>")
    lines.append("№ | AKT   | УРОВЕНЬ   | ОПИСАНИЕ")
    lines.append("----------------------------------")

    buttons = []
    row_buttons = []

    for idx, alt in enumerate(alerts, 1):
        alert_id = alt.get("id")
        symbol = alt.get("symbol", "BTC")
        target_price = alt.get("target_price", 0.0)
        note = alt.get("note", "Алерт")

        price_str = f"{target_price:.4f}" if target_price < 1 else f"{target_price:.1f}" if target_price > 1000 else f"{target_price:.2f}"
        lines.append(f"{idx:<2}| {symbol:<5} | {price_str:<9} | {note}")

        row_buttons.append({"text": f"❌ #{idx}", "callback_data": f"del_alert_{alert_id}"})
        if len(row_buttons) == 3:
            buttons.append(row_buttons)
            row_buttons = []

    if row_buttons:
        buttons.append(row_buttons)

    lines.append("</pre>")
    text = "🔔 <b>АКТИВНЫЕ ЦЕНОВЫЕ АЛЕРТЫ:</b>\n" + "\n".join(lines)
    return text, buttons

async def process_ai_message(user_text: str, chat_id: int) -> dict:
    data = parse_user_intent(user_text)

    if "error" in data:
        return {"content": f"⚠️ Не удалось распознать запрос: {data['error']}"}

    req_type = data.get("type", "chat")

    if req_type == "chat":
        reply = data.get("reply", "Понял вас, но затрудняюсь ответить.")
        return {"content": reply}

    if req_type == "alert":
        symbol_short = clean_symbol(data.get("symbol"))
        symbol_full = f"{symbol_short}-USDT"
        timeframe = data.get("timeframe") or "1h"
        level_type = data.get("level_type", "exact")

        created_alerts = []

        if level_type in ["prev_candle_high_low", "prev_candle_high", "prev_candle_low", "prev_candle_close", "prev_candle_open", "pou", "prev_d1_high", "prev_d1_low"]:
            df = await fetch_klines(symbol_full, timeframe, limit=5)
            if df is not None and len(df) >= 2:
                prev_candle = df.iloc[-2]
                c_high = float(prev_candle['high'])
                c_low = float(prev_candle['low'])
                c_close = float(prev_candle['close'])
                c_open = float(prev_candle['open'])
                c_time = prev_candle.name.strftime('%d.%m %H:%M') if hasattr(prev_candle.name, 'strftime') else ""

                if level_type == "prev_candle_high_low":
                    # Создаем два алерта (High и Low)
                    aid_h = add_alert(chat_id=chat_id, symbol=symbol_short, target_price=c_high, note=f"High {timeframe.upper()} {c_time}")
                    aid_l = add_alert(chat_id=chat_id, symbol=symbol_short, target_price=c_low, note=f"Low {timeframe.upper()} {c_time}")
                    created_alerts.append((c_high, f"High {timeframe.upper()} {c_time}", aid_h))
                    created_alerts.append((c_low, f"Low {timeframe.upper()} {c_time}", aid_l))
                elif level_type in ["prev_candle_low", "prev_d1_low"]:
                    aid = add_alert(chat_id=chat_id, symbol=symbol_short, target_price=c_low, note=f"Low {timeframe.upper()} {c_time}")
                    created_alerts.append((c_low, f"Low {timeframe.upper()} {c_time}", aid))
                elif level_type in ["prev_candle_high", "prev_d1_high"]:
                    aid = add_alert(chat_id=chat_id, symbol=symbol_short, target_price=c_high, note=f"High {timeframe.upper()} {c_time}")
                    created_alerts.append((c_high, f"High {timeframe.upper()} {c_time}", aid))
                elif level_type in ["prev_candle_close", "pou"]:
                    aid = add_alert(chat_id=chat_id, symbol=symbol_short, target_price=c_close, note=f"POU {timeframe.upper()} {c_time}")
                    created_alerts.append((c_close, f"POU {timeframe.upper()} {c_time}", aid))
                elif level_type == "prev_candle_open":
                    aid = add_alert(chat_id=chat_id, symbol=symbol_short, target_price=c_open, note=f"Open {timeframe.upper()} {c_time}")
                    created_alerts.append((c_open, f"Open {timeframe.upper()} {c_time}", aid))
            else:
                return {"content": f"❌ Не удалось получить данные по свечам для {symbol_short} ({timeframe})."}
        else:
            # Ручной ввод точной цены
            target_price = data.get("target_price")
            if target_price:
                aid = add_alert(chat_id=chat_id, symbol=symbol_short, target_price=target_price, note="Точный уровень")
                created_alerts.append((target_price, "Точный уровень", aid))

        if not created_alerts:
            return {"content": "❌ Не удалось определить цену для алерта. Укажите конкретный уровень."}

        cards = []
        buttons = []
        for price, desc, aid in created_alerts:
            price_str = f"{price:.4f}" if price < 1 else f"{price:.1f}" if price > 1000 else f"{price:.2f}"
            cards.append(f"📌 <b>{symbol_short}</b> ({timeframe.upper()}) -> <b>{price_str}</b> [{desc}]")
            buttons.append({"text": f"❌ Удалить {price_str}", "callback_data": f"del_alert_{aid}"})

        res_text = "✅ <b>УСПЕШНО УСТАНОВЛЕНО АЛЕРТОВ: " + str(len(created_alerts)) + "</b>\n\n" + "\n".join(cards) + "\n\n<i>Посмотреть все: /alerts</i>"
        markup = [buttons] if buttons else None
        return {"content": res_text, "markup": markup}

    return {"content": "Запрос обработан."}

async def timer_checker_loop(bot):
    """Фоновая проверка срабатывания алертов каждые 10 секунд"""
    while True:
        try:
            await asyncio.sleep(10)
            
            # Получаем абсолютно все алерты из базы (chat_id=None берет все записи)
            alerts = get_all_alerts(chat_id=None)
            if not alerts:
                continue

            # Группируем алерты по активам, чтобы лишний раз не делать 100 запросов к BingX
            symbols_to_check = set(alt.get("symbol") for alt in alerts if alt.get("symbol"))

            for sym in symbols_to_check:
                symbol_full = f"{sym}-USDT"
                df = await fetch_klines(symbol_full, "1m", limit=2)
                if df is None or len(df) == 0:
                    continue

                # Текущая цена с последней 1м свечи
                current_price = float(df.iloc[-1]['close'])

                # Проверяем все алерты по этому симболу
                sym_alerts = [a for a in alerts if a.get("symbol") == sym]
                for alt in sym_alerts:
                    target_price = float(alt.get("target_price", 0))
                    chat_id = alt.get("chat_id")
                    alert_id = alt.get("id")
                    note = alt.get("note", "Уровень")

                    # Если цена подошла очень близко (погрешность 0.05%) или пересекла
                    diff_pct = abs(current_price - target_price) / target_price * 100
                    if diff_pct <= 0.08 or (current_price >= target_price and alt.get("last_price", current_price) < target_price):
                        price_str = f"{target_price:.4f}" if target_price < 1 else f"{target_price:.1f}" if target_price > 1000 else f"{target_price:.2f}"
                        curr_str = f"{current_price:.4f}" if current_price < 1 else f"{current_price:.1f}" if current_price > 1000 else f"{current_price:.2f}"
                        
                        msg = (
                            f"🚨 <b>СРАБОТАЛ АЛЕРТ!</b> 🚨\n\n"
                            f"🎯 <b>Актив:</b> {sym}\n"
                            f"📍 <b>Целевой уровень:</b> {price_str} ({note})\n"
                            f"📊 <b>Текущая цена:</b> {curr_str}\n"
                        )
                        try:
                            await bot.send_message(chat_id=chat_id, text=msg, parse_mode="HTML")
                            delete_alert(alert_id=alert_id, chat_id=chat_id)
                        except Exception as send_err:
                            print(f"⚠️ Ошибка отправки алерта: {send_err}")

        except Exception as e:
            print(f"⚠️ Ошибка в timer_checker_loop: {e}")
            await asyncio.sleep(10)

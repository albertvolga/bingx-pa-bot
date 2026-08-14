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
        target_price = data.get("target_price")

        level_desc = "Ценовой уровень"
        
        if level_type in ["prev_candle_high", "prev_candle_low", "prev_candle_close", "prev_candle_open", "pou", "prev_d1_high", "prev_d1_low"]:
            df = await fetch_klines(symbol_full, timeframe, limit=5)
            if df is not None and len(df) >= 2:
                prev_candle = df.iloc[-2]
                c_high = float(prev_candle['high'])
                c_low = float(prev_candle['low'])
                c_close = float(prev_candle['close'])
                c_open = float(prev_candle['open'])
                c_time = prev_candle.name.strftime('%d.%m %H:%M') if hasattr(prev_candle.name, 'strftime') else ""

                if level_type in ["prev_candle_low", "prev_d1_low"]:
                    target_price = c_low
                    level_desc = f"Low {timeframe.upper()} {c_time}"
                elif level_type in ["prev_candle_high", "prev_d1_high"]:
                    target_price = c_high
                    level_desc = f"High {timeframe.upper()} {c_time}"
                elif level_type in ["prev_candle_close", "pou"]:
                    target_price = c_close
                    level_desc = f"POU {timeframe.upper()} {c_time}"
                elif level_type == "prev_candle_open":
                    target_price = c_open
                    level_desc = f"Open {timeframe.upper()} {c_time}"
            else:
                return {"content": f"❌ Не удалось получить данные по свечам для {symbol_short} ({timeframe})."}

        if not target_price:
            return {"content": "❌ Не удалось определить цену для алерта. Укажите конкретный уровень."}

        alert_id = add_alert(
            chat_id=chat_id,
            symbol=symbol_short,
            target_price=target_price,
            is_multi=data.get("is_multi", False),
            note=level_desc
        )

        price_str = f"{target_price:.4f}" if target_price < 1 else f"{target_price:.1f}" if target_price > 1000 else f"{target_price:.2f}"

        single_card = (
            f"✅ <b>АЛЕРТ УСПЕШНО УСТАНОВЛЕН!</b>\n\n"
            f"<pre>"
            f"📌 Актив:     {symbol_short}\n"
            f"⏱ ТФ:        {timeframe.upper()}\n"
            f"🎯 Уровень:   {price_str}\n"
            f"📝 Описание:  {level_desc}\n"
            f"</pre>\n"
            f"<i>Посмотреть все алерты: /alerts</i>"
        )

        markup = [[{"text": "❌ Удалить этот алерт", "callback_data": f"del_alert_{alert_id}"}]]
        return {"content": single_card, "markup": markup}

    return {"content": "Запрос обработан."}

async def timer_checker_loop(bot):
    """Фоновая проверка срабатывания алертов"""
    while True:
        try:
            await asyncio.sleep(10)
        except Exception as e:
            await asyncio.sleep(10)

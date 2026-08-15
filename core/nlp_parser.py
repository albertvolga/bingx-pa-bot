import re

def parse_user_intent(text: str) -> dict:
    if not text:
        return {"type": "chat", "reply": "Пустое сообщение."}

    text_clean = text.strip()
    
    # 1. Поиск точной цены (число с точкой или запятой, либо целое число)
    # Ищет конструкции вида: "0.1249", "0,1249", "1980", "1985.5"
    price_match = re.search(r'\b(\d+[\.,]\d+|\d+)\b', text_clean)
    
    target_price = None
    if price_match:
        try:
            target_price = float(price_match.group(1).replace(',', '.'))
        except ValueError:
            target_price = None

    # 2. Проверка на короткий формат: "Монета Цена" (например: "Каспа 0.1249", "Доги 0.34", "ETH 2000")
    # Если в тексте есть число, а длина сообщения меньше 30 символов — считаем это прямым приказом на алерт
    if target_price is not None and len(text_clean) < 35:
        return {
            "type": "alert",
            "level_type": "exact",
            "target_price": target_price
        }

    # 3. Полный формат со словами-триггерами ("поставь", "уведомление", "алерт", "напомни")
    t_lower = text_clean.lower()
    alert_keywords = ["алерт", "альерт", "уведомление", "поставь", "напомни", "сигнал", "уровень", "оповещение"]
    
    if any(kw in t_lower for kw in alert_keywords):
        if target_price is not None and not any(k in t_lower for k in ["хай", "лоу", "бар", "свеч"]):
            return {
                "type": "alert",
                "level_type": "exact",
                "target_price": target_price
            }
        return {
            "type": "alert",
            "level_type": "calculated"
        }

    return {"type": "chat", "reply": "Принято."}

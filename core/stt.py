import whisper
import os
import re

model = whisper.load_model("base")

# Полный контекстный промпт для Whisper под все активы со скриншота
TRADING_PROMPT = (
    "Поставь алерт, альерт, уведомление, оповещение, сигнал, напомни. "
    "Активы и монеты: "
    "золото, голд, XAU, PAXG, "
    "серебро, сильвер, XAG, "
    "каспа, касспа, KAS, "
    "доги, доге, DOGE, "
    "атом, космос, ATOM, "
    "дот, полкадот, DOT, "
    "ада, кардано, ADA, "
    "лайткоин, лайт, LTC, "
    "солана, сол, SOL, "
    "эфир, эфириум, ETH, "
    "биткоин, биток, BTC, "
    "монеро, монейро, XMR, "
    "рипл, риппл, XRP, "
    "газ, природный газ, натуральный газ, NG, "
    "нефть, брент, oil, brent. "
    "Уровни: хай, лоу, high, low, вчерашний дневной бар, закрытие, уровень, цена."
)

def normalize_recognized_text(text: str) -> str:
    if not text:
        return ""
    
    # 1. Уведомления и команды
    text = re.sub(r'\b(альерт|олерт|алерт|видомлении|в\s*уведомлении)\b', 'уведомление', text, flags=re.IGNORECASE)
    
    # 2. Драгметаллы и товары
    text = re.sub(r'\b(золото|золота|голд|xau)\b', 'PAXG', text, flags=re.IGNORECASE)
    text = re.sub(r'\b(серебро|серебра|сильвер|xag)\b', 'SILVER', text, flags=re.IGNORECASE)
    text = re.sub(r'\b(газ|природный\s*газ|натуральный\s*газ|газа)\b', 'NATURALGAS', text, flags=re.IGNORECASE)
    text = re.sub(r'\b(нефть|нефти|брент|brent)\b', 'OILBRENT', text, flags=re.IGNORECASE)

    # 3. Криптовалюты
    text = re.sub(r'\b(касспа|каспа|каспу|касспу)\b', 'KAS', text, flags=re.IGNORECASE)
    text = re.sub(r'\b(атом|космос|атома)\b', 'ATOM', text, flags=re.IGNORECASE)
    text = re.sub(r'\b(монеро|монейро)\b', 'XMR', text, flags=re.IGNORECASE)
    text = re.sub(r'\b(доги|доге|догикоин)\b', 'DOGE', text, flags=re.IGNORECASE)
    text = re.sub(r'\b(ада|кардано|аду)\b', 'ADA', text, flags=re.IGNORECASE)
    text = re.sub(r'\b(лайткоин|лайткойн|лайт|лайта)\b', 'LTC', text, flags=re.IGNORECASE)
    text = re.sub(r'\b(салану|салана|салане|солану|солана|сол)\b', 'SOL', text, flags=re.IGNORECASE)
    text = re.sub(r'\b(полка\s*dot|полкадот|полка|дот)\b', 'DOT', text, flags=re.IGNORECASE)
    text = re.sub(r'\b(эфир|эфириум|кефир|эфира)\b', 'ETH', text, flags=re.IGNORECASE)
    text = re.sub(r'\b(биткоин|биткойн|биток|битка|биткоина)\b', 'BTC', text, flags=re.IGNORECASE)
    text = re.sub(r'\b(рипл|риппл|рипла)\b', 'XRP', text, flags=re.IGNORECASE)
    
    # 4. Трейдинг-термины и исправление опечаток
    text = re.sub(r'\b(демной|демного|дневного)\b', 'дневной', text, flags=re.IGNORECASE)
    text = re.sub(r'\b(хай\s*ило|хай\s*и\s*ло|хай\s*лоу)\b', 'хай и лоу', text, flags=re.IGNORECASE)
    
    return text

async def transcribe_voice(file_bytes: bytes) -> str:
    temp_path = "temp_voice.ogg"
    with open(temp_path, "wb") as f:
        f.write(file_bytes)
    
    try:
        result = model.transcribe(
            temp_path, 
            language="ru",
            initial_prompt=TRADING_PROMPT,
            temperature=0.0
        )
        raw_text = result.get("text", "").strip()
        text = normalize_recognized_text(raw_text)
    except Exception as e:
        text = ""
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
            
    return text

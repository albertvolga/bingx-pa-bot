import whisper
import os

model = whisper.load_model("tiny")

async def transcribe_voice(file_bytes: bytes) -> str:
    temp_path = "temp_voice.ogg"
    with open(temp_path, "wb") as f:
        f.write(file_bytes)
    
    try:
        result = model.transcribe(temp_path, language="ru")
        text = result.get("text", "").strip()
    except Exception as e:
        text = ""
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
            
    return text

import json
import asyncio
from core.nlp_parser import parse_user_intent

TEST_PHRASES = [
    "поставь алерты на солана по бар 1ч",
    "поставь алерты на солана по бар 1ч закрытый в 10 утра",
    "поставь алерт максимум и минимум на солана по бару 1ч закрытый в 10 утра",
    "поставь мультиалерт на солана по бару 1ч",
    "поставь многоразовый алерт на BTC 65000"
]

def run_tests():
    print("==================================================")
    print("🚀 ЗАПУСК ТЕСТИРОВАНИЯ NLP-ПАРСЕРА")
    print("==================================================\n")

    for i, phrase in enumerate(TEST_PHRASES, 1):
        print(f"[{i}/{len(TEST_PHRASES)}] Фраза: \"{phrase}\"")
        
        try:
            # Вызываем парсер
            result = parse_user_intent(phrase)
            
            # Если функция parse_user_intent асинхронная, расскоментируйте строчку ниже, а верхнюю закомментируйте:
            # result = asyncio.run(parse_user_intent(phrase))
            
            formatted_json = json.dumps(result, ensure_ascii=False, indent=2)
            print("Результат от ИИ:")
            print(formatted_json)
            
            is_multi = result.get("is_multi")
            level_type = result.get("level_type")
            
            print("🔍 Проверка флагов:")
            print(f"   • Многоразовый (is_multi): {is_multi}")
            print(f"   • Тип уровня (level_type): {level_type}")
            
        except Exception as e:
            print(f"❌ Ошибка при обработке фразы: {e}")
            
        print("-" * 50 + "\n")

if __name__ == "__main__":
    run_tests()

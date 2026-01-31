import aiohttp
import asyncio
import json
import os
import logging

# Налаштування
NEWSKY_API_KEY = os.getenv("NEWSKY_API_KEY")
BASE_URL = "https://newsky.app/api/airline-api"
HEADERS = {"Authorization": f"Bearer {NEWSKY_API_KEY}"}

async def recursive_search(data, path=""):
    """Рекурсивно шукає ключі, пов'язані з посадкою"""
    found = []
    
    if isinstance(data, dict):
        for k, v in data.items():
            new_path = f"{path}.{k}" if path else k
            
            # Ключові слова для пошуку
            keywords = ["rate", "touchdown", "landing", "fpm", "vs", "speed"]
            if any(word in k.lower() for word in keywords):
                # Якщо це число або рядок - зберігаємо
                if isinstance(v, (int, float, str)):
                    found.append(f"🔍 ЗНАЙДЕНО: {new_path} = {v}")
            
            # Йдемо глибше
            found.extend(await recursive_search(v, new_path))
            
    elif isinstance(data, list):
        for i, item in enumerate(data):
            found.extend(await recursive_search(item, f"{path}[{i}]"))
            
    return found

async def main():
    print("🕵️ ПОЧИНАЮ ГЛИБОКЕ СКАНУВАННЯ...")
    
    async with aiohttp.ClientSession() as session:
        # 1. Беремо останній завершений рейс
        async with session.post(f"{BASE_URL}/flights/recent", headers=HEADERS, json={"count": 1}) as r:
            if r.status != 200:
                print(f"❌ Помилка доступу до історії: {r.status}")
                return
            
            data = await r.json()
            if not data.get("results"):
                print("⚠️ Немає завершених польотів для аналізу.")
                return
                
            fid = data["results"][0]["_id"]
            print(f"✅ Аналізую рейс ID: {fid}")
            
            # 2. Качаємо повне досьє
            async with session.get(f"{BASE_URL}/flight/{fid}", headers=HEADERS) as r2:
                full_data = await r2.json()
                
                # 3. Шукаємо FPM
                print("\n--- РЕЗУЛЬТАТИ ПОШУКУ FPM ---")
                results = await recursive_search(full_data)
                
                if results:
                    for res in results:
                        print(res)
                else:
                    print("❌ Нічого схожого на FPM не знайдено.")
                    # Якщо нічого не знайшли, виведемо структуру result
                    print("\n--- STRUCUTRE OF RESULT ---")
                    print(json.dumps(full_data.get("flight", {}).get("result", {}), indent=2))

if __name__ == "__main__":
    asyncio.run(main())
    

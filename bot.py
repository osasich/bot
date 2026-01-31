import discord
import aiohttp
import asyncio
import json
import os
import logging

# Змінні
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
NEWSKY_API_KEY = os.getenv("NEWSKY_API_KEY")

# Налаштування
BASE_URL = "https://newsky.app/api/airline-api"
HEADERS = {"Authorization": f"Bearer {NEWSKY_API_KEY}"}

logging.basicConfig(level=logging.INFO)
client = discord.Client(intents=discord.Intents.default())

@client.event
async def on_ready():
    print(f"🕵️ ШПИГУН ОНЛАЙН: {client.user}")
    print("⏳ Чекаю 5 секунд перед запитом...")
    await asyncio.sleep(5)
    
    async with aiohttp.ClientSession() as session:
        print("\n" + "="*40)
        print("📡 ЗАПИТ 1: /flights/ongoing (Список активних)")
        print("="*40)
        
        async with session.get(f"{BASE_URL}/flights/ongoing", headers=HEADERS) as r:
            if r.status == 200:
                data = await r.json()
                # Друкуємо повну структуру JSON
                print(json.dumps(data, indent=2, ensure_ascii=False))
                
                # Якщо є хоч один політ, беремо його ID і копаємо глибше
                if data.get("results") and len(data["results"]) > 0:
                    first_flight = data["results"][0]
                    # Пробуємо знайти ID (він може бути _id або id)
                    fid = first_flight.get("_id") or first_flight.get("id")
                    
                    if fid:
                        print("\n" + "="*40)
                        print(f"🔬 ЗАПИТ 2: /flight/{fid} (Деталі польоту)")
                        print("="*40)
                        async with session.get(f"{BASE_URL}/flight/{fid}", headers=HEADERS) as r2:
                            det = await r2.json()
                            print(json.dumps(det, indent=2, ensure_ascii=False))
                    else:
                        print("❌ Не знайдено ID польоту в списку ongoing")
                else:
                    print("⚠️ Список ongoing порожній (API каже, що ніхто не летить)")
            else:
                print(f"❌ Помилка запиту ongoing: {r.status}")
                print(await r.text())

    print("\n🏁 Діагностику завершено.")
    await client.close()

client.run(DISCORD_TOKEN)

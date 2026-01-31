import discord
import aiohttp
import asyncio
import json
import os
import logging

# Налаштування
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
NEWSKY_API_KEY = os.getenv("NEWSKY_API_KEY")
BASE_URL = "https://newsky.app/api/airline-api"
HEADERS = {"Authorization": f"Bearer {NEWSKY_API_KEY}"}

logging.basicConfig(level=logging.INFO)
client = discord.Client(intents=discord.Intents.default())

@client.event
async def on_ready():
    print(f"🕵️ ШПИГУН АРХІВУ ОНЛАЙН: {client.user}")
    print("⏳ Підключаюся до бази даних завершених польотів...")
    
    async with aiohttp.ClientSession() as session:
        # 1. Беремо список останніх завершених (RECENT)
        print("\n" + "="*40)
        print("📡 ЗАПИТ: /flights/recent (Архів)")
        print("="*40)
        
        # Newsky вимагає POST запит для історії
        async with session.post(f"{BASE_URL}/flights/recent", headers=HEADERS, json={"count": 1}) as r:
            if r.status == 200:
                data = await r.json()
                
                if data.get("results") and len(data["results"]) > 0:
                    last_flight = data["results"][0]
                    fid = last_flight.get("_id") or last_flight.get("id")
                    
                    print(f"✅ Знайдено останній політ ID: {fid}")
                    print("⬇️ Завантажую повний фінансовий звіт...")
                    
                    # 2. Беремо повні деталі цього польоту
                    async with session.get(f"{BASE_URL}/flight/{fid}", headers=HEADERS) as r2:
                        full_details = await r2.json()
                        print("\n📜 JSON ВІДПОВІДЬ (Скопіюй це розробнику):")
                        print(json.dumps(full_details, indent=2, ensure_ascii=False))
                else:
                    print("⚠️ Історія польотів порожня.")
            else:
                print(f"❌ Помилка доступу до історії: {r.status}")
                print(await r.text())

    print("\n🏁 Готово. Бот вимикається.")
    await client.close()

client.run(DISCORD_TOKEN)

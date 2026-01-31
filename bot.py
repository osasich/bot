import discord
import aiohttp
import asyncio
import json
import os
import logging
from pathlib import Path

# ---------- НАЛАШТУВАННЯ ----------
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
NEWSKY_API_KEY = os.getenv("NEWSKY_API_KEY")
BASE_URL = "https://newsky.app/api/airline-api"
HEADERS = {"Authorization": f"Bearer {NEWSKY_API_KEY}"}

logging.basicConfig(level=logging.INFO)
client = discord.Client(intents=discord.Intents.default())

async def fetch_api(session, path):
    try:
        async with session.get(f"{BASE_URL}{path}", headers=HEADERS) as r:
            if r.status == 200: return await r.json()
    except Exception as e:
        print(f"❌ API Error: {e}")
    return None

@client.event
async def on_ready():
    print(f"🕵️ FPM SPY OONLINE: {client.user}")
    print("⏳ Чекаю на посадку...")
    
    # Змінна щоб не спамити логами
    landed_flag = False

    async with aiohttp.ClientSession() as session:
        while True:
            try:
                # 1. Шукаємо активний політ
                ongoing = await fetch_api(session, "/flights/ongoing")
                
                if ongoing and "results" in ongoing and len(ongoing["results"]) > 0:
                    raw_f = ongoing["results"][0]
                    fid = raw_f.get("_id") or raw_f.get("id")
                    
                    # Качаємо деталі
                    det = await fetch_api(session, f"/flight/{fid}")
                    if det and "flight" in det:
                        f = det["flight"]
                        cs = f.get("flightNumber") or "N/A"
                        
                        # Перевіряємо статус
                        is_landed = f.get("arrTimeAct") is not None
                        
                        # Якщо тільки що сів (або ми вперше побачили посадку)
                        if is_landed and not landed_flag:
                            print("\n" + "="*50)
                            print(f"🛬 DETECTED LANDING: {cs}")
                            print("="*50)
                            
                            # --- ЕТАП 1: МИТТЄВИЙ ЗАПИТ ---
                            print("⏱️ T+0 sec (Миттєво):")
                            speed_data = f.get("lastState", {}).get("speed", {})
                            print(f"   📉 lastState.speed: {json.dumps(speed_data, indent=2)}")
                            print(f"   📄 Raw FPM field: {speed_data.get('touchDownRate')}")
                            print(f"   ↕️ Vertical Speed (vs): {speed_data.get('vs')}")
                            
                            # --- ЕТАП 2: ЧЕРЕЗ 5 СЕКУНД ---
                            print("\n⏳ Чекаю 5 секунд, щоб сервер оновив дані...")
                            await asyncio.sleep(5)
                            
                            det_5s = await fetch_api(session, f"/flight/{fid}")
                            f_5s = det_5s["flight"]
                            speed_5s = f_5s.get("lastState", {}).get("speed", {})
                            
                            print("⏱️ T+5 sec:")
                            print(f"   📉 lastState.speed: {json.dumps(speed_5s, indent=2)}")
                            print(f"   📄 Raw FPM field: {speed_5s.get('touchDownRate')}")
                            
                            # --- ЕТАП 3: ЧЕРЕЗ 10 СЕКУНД ---
                            print("\n⏳ Чекаю ще 5 секунд...")
                            await asyncio.sleep(5)
                            
                            det_10s = await fetch_api(session, f"/flight/{fid}")
                            f_10s = det_10s["flight"]
                            speed_10s = f_10s.get("lastState", {}).get("speed", {})
                            
                            print("⏱️ T+10 sec:")
                            print(f"   📉 lastState.speed: {json.dumps(speed_10s, indent=2)}")
                            print(f"   📄 Raw FPM field: {speed_10s.get('touchDownRate')}")
                            
                            landed_flag = True # Більше не реагуємо на цей рейс
                            print("\n✅ Діагностику завершено. Скинь ці логи!")

                        elif not is_landed:
                            # Просто показуємо що бот живий і бачить політ
                            alt = f.get("lastState", {}).get("location", {}).get("alt", 0)
                            print(f"✈️ У польоті: {cs} | Alt: {alt} ft | Чекаю на посадку...", end="\r")
                            landed_flag = False # Скидаємо прапор якщо новий рейс

            except Exception as e:
                print(f"Error: {e}")
            
            await asyncio.sleep(2)

client.run(DISCORD_TOKEN)

import discord
import aiohttp
import asyncio
import json
import os
import logging
from pathlib import Path

# ---------- НАЛАШТУВАННЯ ----------
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID")) if os.getenv("CHANNEL_ID") else 0
NEWSKY_API_KEY = os.getenv("NEWSKY_API_KEY")

STATE_FILE = Path("sent.json")
CHECK_INTERVAL = 20 # Перевіряємо частіше
BASE_URL = "https://newsky.app/api/airline-api"
HEADERS = {"Authorization": f"Bearer {NEWSKY_API_KEY}"}

logging.basicConfig(level=logging.INFO)
intents = discord.Intents.default()
client = discord.Client(intents=intents)

def load_state():
    if not STATE_FILE.exists(): return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except: return {}

def save_state(state):
    try:
        if len(state) > 100: state = dict(list(state.items())[-50:])
        STATE_FILE.write_text(json.dumps(state), encoding="utf-8")
    except: pass

def get_flag(icao):
    if not icao or icao == "????": return "🏳️"
    m = {"UK": "ua", "EP": "pl", "ED": "de", "LF": "fr", "EG": "gb", "EH": "nl", "LI": "it", "LE": "es", "LO": "at", "KJ": "us", "UU": "ru", "UR": "ru"}
    return f":flag_{m.get(str(icao)[:2], 'white')}:"

def get_timing(delay):
    if delay is None: return "⏱️ Невідомо"
    try:
        d = float(delay)
        if d > 5: return f"🔴 Затримка (+{int(d)} хв)"
        if d < -5: return f"🟡 Раніше на {-int(d)} хв"
        return "🟢 Вчасно"
    except: return "⏱️ Невідомо"

async def fetch_api(session, path, method="GET", body=None):
    url = f"{BASE_URL}{path}"
    try:
        async with session.request(method, url, headers=HEADERS, json=body, timeout=10) as r:
            if r.status == 200: return await r.json()
            print(f"⚠️ API API Newsky повернув помилку: {r.status}")
            return None
    except Exception as e:
        print(f"⚠️ Помилка з'єднання: {e}")
        return None

@client.event
async def on_ready():
    print(f"✅ Бот онлайн: {client.user}")
    client.loop.create_task(main_loop())

async def main_loop():
    await client.wait_until_ready()
    channel = client.get_channel(CHANNEL_ID)
    if not channel:
        try: channel = await client.fetch_channel(CHANNEL_ID)
        except: print(f"❌ КРИТИЧНО: Не можу знайти канал {CHANNEL_ID}"); return

    state = load_state()
    print("🚀 Цикл запущено. Чекаю даних від Newsky...")

    async with aiohttp.ClientSession() as session:
        while True:
            try:
                # 1. ПЕРЕВІРКА ONGOING
                ongoing = await fetch_api(session, "/flights/ongoing")
                if ongoing is not None:
                    flights = ongoing.get("results", [])
                    print(f"📡 API Ongoing: знайдено {len(flights)} польотів.")
                    
                    for f in flights:
                        fid = str(f.get("_id") or f.get("id"))
                        cs = f.get("callsign", "N/A")
                        
                        # ДЕБАГ ІНФО
                        print(f"   ✈️ Рейс {cs} (ID: {fid}) | Takeoff: {bool(f.get('takeoffTimeAct'))} | Landed: {bool(f.get('arrTimeAct'))}")

                        state.setdefault(fid, {})
                        
                        # ЗБІР ДАНИХ
                        dep = f.get("departure", {}).get("icao") or "????"
                        arr = f.get("arrival", {}).get("icao") or "????"
                        ac = f.get("aircraft", {}).get("airframe", {}).get("ident") or "A/C"
                        delay = f.get("delay")

                        # ЛОГІКА ВЗЛІТ
                        if f.get("takeoffTimeAct") and not state[fid].get("takeoff"):
                            print(f"      🔔 Відправляю TAKEOFF для {cs}")
                            det = await fetch_api(session, f"/flight/{fid}")
                            pilot = det["flight"].get("pilot", {}).get("fullname", "Pilot") if det else "Pilot"
                            pax = f.get("pax", 0)
                            cargo = f.get("cargo", 0)
                            
                            msg = (f"🛫 **{cs} departed**\n{get_flag(dep)}{dep} ➡️ {get_flag(arr)}{arr}\n"
                                   f"✈️ {ac}\n🕒 {get_timing(delay)}\n👨‍✈️ {pilot}\n📦 {pax} Pax / {cargo} kg Cargo")
                            await channel.send(msg)
                            state[fid]["takeoff"] = True

                        # ЛОГІКА ПОСАДКА
                        if f.get("arrTimeAct") and not state[fid].get("landing"):
                            print(f"      🔔 Відправляю LANDING для {cs}")
                            det = await fetch_api(session, f"/flight/{fid}")
                            pilot = det["flight"].get("pilot", {}).get("fullname", "Pilot") if det else "Pilot"
                            fpm = det["flight"].get("lastState", {}).get("speed", {}).get("touchDownRate", "N/A") if det else "N/A"
                            pax = f.get("pax", 0)
                            cargo = f.get("cargo", 0)

                            msg = (f"🛬 **{cs} arrived**\n{get_flag(dep)}{dep} ➡️ {get_flag(arr)}{arr}\n"
                                   f"✈️ {ac}\n🕒 {get_timing(delay)}\n📉 {fpm} FPM\n👨‍✈️ {pilot}\n📦 {pax} Pax / {cargo} kg Cargo")
                            await channel.send(msg)
                            state[fid]["landing"] = True

                # 2. ПЕРЕВІРКА RECENT (Завершені)
                recent = await fetch_api(session, "/flights/recent", method="POST", body={"count": 5})
                if recent is not None:
                    r_flights = recent.get("results", [])
                    # print(f"📡 API Recent: перевірка {len(r_flights)} останніх записів.") # Розкоментуй якщо треба
                    
                    for f in r_flights:
                        fid = str(f.get("_id") or f.get("id"))
                        # Якщо вже відправили або рейс не закритий - пропускаємо
                        if state.get(fid, {}).get("completed") or not f.get("close"):
                            continue
                        
                        print(f"   😎 Знайдено завершений рейс {f.get('callsign')} - готую звіт.")
                        
                        det = await fetch_api(session, f"/flight/{fid}")
                        if not det or "flight" not in det: continue
                        
                        fl = det["flight"]
                        cs = fl.get("callsign", "N/A")
                        
                        # ФІЛЬТР ПУСТИХ
                        if cs == "N/A": 
                            print("      ⚠️ Пропущено (немає позивного)")
                            continue

                        # ДАНІ
                        dep = fl.get("departure", {}).get("icao") or "????"
                        arr = fl.get("arrival", {}).get("icao") or "????"
                        ac = fl.get("aircraft", {}).get("airframe", {}).get("ident") or "A/C"
                        pilot = fl.get("pilot", {}).get("fullname") or "Pilot"
                        
                        raw_net = fl.get("network")
                        if isinstance(raw_net, dict): net = str(raw_net.get("name") or "OFFLINE").upper()
                        else: net = str(raw_net or "OFFLINE").upper()
                        
                        msg = (f"😎 **{cs} completed**\n{get_flag(dep)}{dep} ➡️ {get_flag(arr)}{arr}\n"
                               f"✈️ {ac}\n👨‍✈️ {pilot}\n🌐 {net}\n"
                               f"📦 {fl.get('pax', 0)} Pax / {fl.get('cargo', 0)} kg Cargo\n"
                               f"📏 {fl.get('distance', 0)} nm / ⏱️ {fl.get('flightTime', 0)} min\n"
                               f"💰 {fl.get('finances', {}).get('totalIncome', 0)}$\n"
                               f"⭐ {fl.get('rating', '0.00')}")
                        
                        await channel.send(msg)
                        state.setdefault(fid, {})["completed"] = True
                        print(f"      ✅ Звіт відправлено!")

                save_state(state)
            except Exception as e:
                print(f"❌ ПОМИЛКА: {e}")
            
            await asyncio.sleep(CHECK_INTERVAL)

client.run(DISCORD_TOKEN)

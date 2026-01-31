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
CHECK_INTERVAL = 20
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
            return None
    except Exception as e:
        print(f"⚠️ API Error: {e}")
        return None

@client.event
async def on_ready():
    print(f"✅ Бот онлайн: {client.user}")
    client.loop.create_task(main_loop())

async def main_loop():
    await client.wait_until_ready()
    channel = client.get_channel(CHANNEL_ID) or await client.fetch_channel(CHANNEL_ID)
    state = load_state()
    print("🚀 Flight Dispatcher: СТАРТ")

    async with aiohttp.ClientSession() as session:
        while True:
            try:
                # === 1. АКТИВНІ РЕЙСИ ===
                ongoing_list = await fetch_api(session, "/flights/ongoing")
                
                if ongoing_list and "results" in ongoing_list:
                    for raw_f in ongoing_list["results"]:
                        fid = str(raw_f.get("_id") or raw_f.get("id"))
                        if not fid or fid == "None": continue

                        # Качаємо деталі
                        det = await fetch_api(session, f"/flight/{fid}")
                        if not det or "flight" not in det: continue
                        f = det["flight"]

                        # Витягуємо дані (оновлено під JSON)
                        cs = f.get("flightNumber") or f.get("callsign") or "N/A"
                        if cs == "N/A": continue

                        state.setdefault(fid, {})

                        # Аеропорти (keys: dep, arr)
                        dep = f.get("dep", {}).get("icao") or "????"
                        arr = f.get("arr", {}).get("icao") or "????"
                        ac = f.get("aircraft", {}).get("airframe", {}).get("name") or "Aircraft"
                        pilot = f.get("pilot", {}).get("fullname", "Pilot")
                        
                        # Payload (активний рейс)
                        pax = f.get("payload", {}).get("pax", 0)
                        cargo = f.get("payload", {}).get("cargo", 0)
                        delay = f.get("delay")

                        # --- ВЗЛІТ ---
                        if f.get("takeoffTimeAct") and not state[fid].get("takeoff"):
                            msg = (f"🛫 **{cs} departed**\n"
                                   f"{get_flag(dep)}{dep} ➡️ {get_flag(arr)}{arr}\n"
                                   f"✈️ {ac}\n"
                                   f"🕒 {get_timing(delay)}\n"
                                   f"👨‍✈️ {pilot}\n"
                                   f"📦 {pax} Pax / {cargo} kg Cargo")
                            await channel.send(msg)
                            state[fid]["takeoff"] = True
                            print(f"✅ Взліт: {cs}")

                        # --- ПОСАДКА ---
                        if f.get("arrTimeAct") and not state[fid].get("landing"):
                            # Вертикальна швидкість при посадці
                            fpm = f.get("lastState", {}).get("speed", {}).get("touchDownRate", "N/A")
                            
                            msg = (f"🛬 **{cs} arrived**\n"
                                   f"{get_flag(dep)}{dep} ➡️ {get_flag(arr)}{arr}\n"
                                   f"✈️ {ac}\n"
                                   f"🕒 {get_timing(delay)}\n"
                                   f"📉 {fpm} FPM\n"
                                   f"👨‍✈️ {pilot}\n"
                                   f"📦 {pax} Pax / {cargo} kg Cargo")
                            await channel.send(msg)
                            state[fid]["landing"] = True
                            print(f"✅ Посадка: {cs}")
                        
                        await asyncio.sleep(1)

                # === 2. ЗАВЕРШЕНІ (ЗВІТ) ===
                recent = await fetch_api(session, "/flights/recent", method="POST", body={"count": 5})
                if recent and "results" in recent:
                    for raw_f in recent["results"]:
                        fid = str(raw_f.get("_id") or raw_f.get("id"))
                        if fid in state and state[fid].get("completed"): continue
                        
                        # Перевіряємо чи рейс закритий (closed date exists)
                        if not raw_f.get("close"): continue

                        det = await fetch_api(session, f"/flight/{fid}")
                        if not det or "flight" not in det: continue
                        f = det["flight"]
                        
                        cs = f.get("flightNumber") or f.get("callsign") or "N/A"
                        if cs == "N/A": continue

                        # Дані для звіту
                        dep = f.get("dep", {}).get("icao") or "????"
                        arr = f.get("arr", {}).get("icao") or "????"
                        ac = f.get("aircraft", {}).get("airframe", {}).get("name") or "Aircraft"
                        pilot = f.get("pilot", {}).get("fullname", "Pilot")
                        
                        # Мережа
                        net_obj = f.get("network")
                        net_name = "OFFLINE"
                        if isinstance(net_obj, dict):
                            net_name = (net_obj.get("name") or "OFFLINE").upper()

                        # Статистика з result.totals (це те, що ми знайшли в логах!)
                        totals = f.get("result", {}).get("totals", {})
                        
                        # Фінанси
                        income = totals.get("revenue", 0) 
                        
                        # Payload / Stats
                        final_pax = totals.get("payload", {}).get("pax", 0)
                        final_cargo = totals.get("payload", {}).get("cargo", 0)
                        distance = totals.get("distance", 0)
                        flight_time = totals.get("time", 0)
                        rating = f.get("rating", 0.0)

                        msg = (f"😎 **{cs} completed**\n"
                               f"{get_flag(dep)}{dep} ➡️ {get_flag(arr)}{arr}\n"
                               f"✈️ {ac}\n"
                               f"👨‍✈️ {pilot}\n"
                               f"🌐 {net_name}\n"
                               f"📦 {final_pax} Pax / {final_cargo} kg Cargo\n"
                               f"📏 {distance} nm / ⏱️ {flight_time} min\n"
                               f"💰 {income} $\n"
                               f"⭐ {rating}")
                        
                        await channel.send(msg)
                        state.setdefault(fid, {})["completed"] = True
                        print(f"✅ Звіт: {cs}")

                save_state(state)
            except Exception as e:
                print(f"❌ Error loop: {e}")
            
            await asyncio.sleep(CHECK_INTERVAL)

client.run(DISCORD_TOKEN)

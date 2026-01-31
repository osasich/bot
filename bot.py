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
        print(f"⚠️ Помилка API: {e}")
        return None

@client.event
async def on_ready():
    print(f"✅ Бот онлайн: {client.user}")
    client.loop.create_task(main_loop())

async def main_loop():
    await client.wait_until_ready()
    channel = client.get_channel(CHANNEL_ID) or await client.fetch_channel(CHANNEL_ID)
    state = load_state()
    print("🚀 Flight Dispatcher запущено.")

    async with aiohttp.ClientSession() as session:
        while True:
            try:
                # 1. АКТИВНІ ПОЛЬОТИ
                ongoing_list = await fetch_api(session, "/flights/ongoing")
                
                if ongoing_list and "results" in ongoing_list:
                    for raw_f in ongoing_list["results"]:
                        # Беремо ID
                        fid = str(raw_f.get("_id") or raw_f.get("id"))
                        if not fid or fid == "None": continue

                        # Одразу качаємо деталі, бо в списку немає статусу takeoff
                        det = await fetch_api(session, f"/flight/{fid}")
                        if not det or "flight" not in det: continue

                        f = det["flight"]
                        
                        # --- ВИПРАВЛЕННЯ: ШУКАЄМО flightNumber, ЯКЩО НЕМАЄ callsign ---
                        cs = f.get("callsign") or f.get("flightNumber") or "N/A"
                        if cs == "N/A": continue # Все ще фільтруємо зовсім пусті, але 574N тепер пройде
                        # -------------------------------------------------------------

                        state.setdefault(fid, {})

                        # Дані
                        dep = f.get("departure", {}).get("icao") or f.get("dep", {}).get("icao") or "????"
                        arr = f.get("arrival", {}).get("icao") or f.get("arr", {}).get("icao") or "????"
                        ac = f.get("aircraft", {}).get("airframe", {}).get("ident") or "A/C"
                        delay = f.get("delay")

                        # ВЗЛІТ (Перевіряємо takeoffTimeAct)
                        if f.get("takeoffTimeAct") and not state[fid].get("takeoff"):
                            print(f"🛫 Взліт підтверджено: {cs}")
                            pilot = f.get("pilot", {}).get("fullname", "Pilot")
                            pax = f.get("pax", 0)
                            cargo = f.get("cargo", 0)
                            
                            msg = (f"🛫 **{cs} departed**\n{get_flag(dep)}{dep} ➡️ {get_flag(arr)}{arr}\n"
                                   f"✈️ {ac}\n🕒 {get_timing(delay)}\n👨‍✈️ {pilot}\n📦 {pax} Pax / {cargo} kg Cargo")
                            await channel.send(msg)
                            state[fid]["takeoff"] = True

                        # ПОСАДКА (Перевіряємо arrTimeAct)
                        if f.get("arrTimeAct") and not state[fid].get("landing"):
                            print(f"🛬 Посадку підтверджено: {cs}")
                            pilot = f.get("pilot", {}).get("fullname", "Pilot")
                            fpm = f.get("lastState", {}).get("speed", {}).get("touchDownRate", "N/A")
                            pax = f.get("pax", 0)
                            cargo = f.get("cargo", 0)

                            msg = (f"🛬 **{cs} arrived**\n{get_flag(dep)}{dep} ➡️ {get_flag(arr)}{arr}\n"
                                   f"✈️ {ac}\n🕒 {get_timing(delay)}\n📉 {fpm} FPM\n👨‍✈️ {pilot}\n📦 {pax} Pax / {cargo} kg Cargo")
                            await channel.send(msg)
                            state[fid]["landing"] = True
                        
                        await asyncio.sleep(1) # Невелика пауза між запитами

                # 2. ЗАВЕРШЕНІ (Тут теж додаю фікс на flightNumber)
                recent = await fetch_api(session, "/flights/recent", method="POST", body={"count": 5})
                if recent and "results" in recent:
                    for raw_f in recent["results"]:
                        fid = str(raw_f.get("_id") or raw_f.get("id"))
                        if fid in state and state[fid].get("completed"): continue
                        if not raw_f.get("close"): continue

                        det = await fetch_api(session, f"/flight/{fid}")
                        if not det or "flight" not in det: continue
                        fl = det["flight"]
                        
                        # --- ТУТ ТЕЖ ВИПРАВЛЕННЯ ---
                        cs = fl.get("callsign") or fl.get("flightNumber") or "N/A"
                        if cs == "N/A": continue
                        # ---------------------------

                        dep = fl.get("departure", {}).get("icao") or fl.get("dep", {}).get("icao") or "????"
                        arr = fl.get("arrival", {}).get("icao") or fl.get("arr", {}).get("icao") or "????"
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

                save_state(state)
            except Exception as e:
                print(f"❌ Error: {e}")
            
            await asyncio.sleep(CHECK_INTERVAL)

client.run(DISCORD_TOKEN)

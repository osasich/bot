import discord
import aiohttp
import asyncio
import json
import os
import logging
from pathlib import Path

# ---------- НАЛАШТУВАННЯ (Змінні Railway) ----------
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
# Перетворюємо ID каналу в int, якщо змінна є
CHANNEL_ID = int(os.getenv("CHANNEL_ID")) if os.getenv("CHANNEL_ID") else 0
NEWSKY_API_KEY = os.getenv("NEWSKY_API_KEY")

STATE_FILE = Path("sent.json")
CHECK_INTERVAL = 30 
BASE_URL = "https://newsky.app/api/airline-api"
HEADERS = {"Authorization": f"Bearer {NEWSKY_API_KEY}"}

logging.basicConfig(level=logging.INFO)
intents = discord.Intents.default()
client = discord.Client(intents=intents)

# ---------- ДОПОМІЖНІ ФУНКЦІЇ ----------
def load_state():
    if not STATE_FILE.exists(): return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except: return {}

def save_state(state):
    if len(state) > 100: state = dict(list(state.items())[-50:])
    STATE_FILE.write_text(json.dumps(state), encoding="utf-8")

def get_flag(icao):
    if not icao: return "🏳️"
    icao = str(icao) # Захист від помилок
    m = {"UK": "ua", "EP": "pl", "ED": "de", "LF": "fr", "EG": "gb", "EH": "nl", "LI": "it", "LE": "es", "LO": "at", "KJ": "us", "UU": "ru", "UR": "ru"}
    return f":flag_{m.get(icao[:2], 'white')}:"

def get_timing(delay):
    if delay is None: return "⏱️ Невідомо"
    try:
        d = float(delay)
        if d > 5: return f"🔴 Затримка (+{int(d)} хв)"
        if d < -5: return f"🟡 Раніше на {-int(d)} хв"
        return "🟢 Вчасно"
    except:
        return "⏱️ Невідомо"

# ---------- API КЛІЄНТ ----------
async def fetch_api(session, path, method="GET", body=None):
    url = f"{BASE_URL}{path}"
    async with session.request(method, url, headers=HEADERS, json=body) as r:
        return await r.json() if r.status == 200 else None

# ---------- ГОЛОВНИЙ ПРОЦЕС ----------
@client.event
async def on_ready():
    logging.info(f"Бот запущений як {client.user}")
    client.loop.create_task(main_loop())

async def main_loop():
    await client.wait_until_ready()
    channel = client.get_channel(CHANNEL_ID)
    
    if not channel:
        try:
            channel = await client.fetch_channel(CHANNEL_ID)
        except Exception as e:
            logging.error(f"Не можу знайти канал {CHANNEL_ID}: {e}")
            return

    state = load_state()

    async with aiohttp.ClientSession() as session:
        while True:
            try:
                # === 1. ONGOING (ВЗЛІТ / ПОСАДКА) ===
                ongoing = await fetch_api(session, "/flights/ongoing")
                if ongoing and "results" in ongoing:
                    for f in ongoing["results"]:
                        # БЕЗПЕЧНЕ ОТРИМАННЯ ID
                        fid = str(f.get("_id") or f.get("id"))
                        if not fid or fid == "None": continue
                        
                        state.setdefault(fid, {})
                        
                        # Безпечний збір даних
                        cs = f.get("callsign") or "N/A"
                        dep = f.get("departure", {}).get("icao") or "????"
                        arr = f.get("arrival", {}).get("icao") or "????"
                        ac = f.get("aircraft", {}).get("airframe", {}).get("ident") or "A/C"
                        delay = f.get("delay")
                        
                        # -- ВЗЛІТ (DEPARTED) --
                        if f.get("takeoffTimeAct") and not state[fid].get("takeoff"):
                            det = await fetch_api(session, f"/flight/{fid}")
                            pilot = "Pilot"
                            pax = f.get("pax", 0)
                            cargo = f.get("cargo", 0)
                            
                            if det and "flight" in det:
                                pilot = det["flight"].get("pilot", {}).get("fullname") or "Pilot"

                            msg = (
                                f"🛫 **{cs} departed**\n"
                                f"{get_flag(dep)}{dep} ➡️ {get_flag(arr)}{arr}\n"
                                f"✈️ {ac}\n"
                                f"🕒 {get_timing(delay)}\n"
                                f"👨‍✈️ {pilot}\n"
                                f"📦 {pax} Pax / {cargo} kg Cargo"
                            )
                            await channel.send(msg)
                            state[fid]["takeoff"] = True

                        # -- ПОСАДКА (ARRIVED) --
                        if f.get("arrTimeAct") and not state[fid].get("landing"):
                            det = await fetch_api(session, f"/flight/{fid}")
                            pilot = "Pilot"
                            fpm = "N/A"
                            pax = f.get("pax", 0)
                            cargo = f.get("cargo", 0)

                            if det and "flight" in det:
                                pilot = det["flight"].get("pilot", {}).get("fullname") or "Pilot"
                                fpm = det["flight"].get("lastState", {}).get("speed", {}).get("touchDownRate", "N/A")

                            msg = (
                                f"🛬 **{cs} arrived**\n"
                                f"{get_flag(dep)}{dep} ➡️ {get_flag(arr)}{arr}\n"
                                f"✈️ {ac}\n"
                                f"🕒 {get_timing(delay)}\n"
                                f"📉 {fpm} FPM\n"
                                f"👨‍✈️ {pilot}\n"
                                f"📦 {pax} Pax / {cargo} kg Cargo"
                            )
                            await channel.send(msg)
                            state[fid]["landing"] = True

                # === 2. COMPLETED (CLOSED) ===
                recent = await fetch_api(session, "/flights/recent", method="POST", body={"count": 5})
                if recent and "results" in recent:
                    for f in recent["results"]:
                        fid = str(f.get("_id") or f.get("id"))
                        if not fid or fid == "None": continue
                        
                        if f.get("close") and not state.get(fid, {}).get("completed"):
                            state.setdefault(fid, {})
                            det = await fetch_api(session, f"/flight/{fid}")
                            
                            if det and "flight" in det:
                                fl = det["flight"]
                                
                                # --- ВИПРАВЛЕННЯ ДЛЯ МЕРЕЖІ (ТУТ БУЛА ПОМИЛКА) ---
                                raw_net = fl.get("network")
                                if isinstance(raw_net, dict):
                                    # Якщо це словник, беремо 'name', якщо null -> 'OFFLINE'
                                    net_val = raw_net.get("name") or raw_net.get("code") or "OFFLINE"
                                    net = str(net_val).upper()
                                elif raw_net:
                                    net = str(raw_net).upper()
                                else:
                                    net = "OFFLINE"
                                # --------------------------------------------------

                                cs = fl.get("callsign") or "N/A"
                                dep = fl.get("departure", {}).get("icao") or "????"
                                arr = fl.get("arrival", {}).get("icao") or "????"
                                ac = fl.get("aircraft", {}).get("airframe", {}).get("ident") or "A/C"
                                pilot = fl.get("pilot", {}).get("fullname") or "Pilot"
                                pax = fl.get("pax", 0)
                                cargo = fl.get("cargo", 0)
                                dist = fl.get("distance", 0)
                                flight_time = fl.get("flightTime", 0)
                                income = fl.get("finances", {}).get("totalIncome", 0)
                                score = fl.get("rating", "0.00")

                                msg = (
                                    f"😎 **{cs} completed**\n"
                                    f"{get_flag(dep)}{dep} ➡️ {get_flag(arr)}{arr}\n"
                                    f"✈️ {ac}\n"
                                    f"👨‍✈️ {pilot}\n"
                                    f"🌐 {net}\n"
                                    f"📦 {pax} Pax / {cargo} kg Cargo\n"
                                    f"📏 {dist} nm / ⏱️ {flight_time} min\n"
                                    f"💰 {income}$\n"
                                    f"⭐ {score}"
                                )
                                await channel.send(msg)
                                state[fid]["completed"] = True

                save_state(state)

            except Exception as e:
                logging.error(f"Критична помилка: {e}")
            
            await asyncio.sleep(CHECK_INTERVAL)

client.run(DISCORD_TOKEN)

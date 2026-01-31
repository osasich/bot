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
CHECK_INTERVAL = 30 
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
    if len(state) > 100: state = dict(list(state.items())[-50:])
    STATE_FILE.write_text(json.dumps(state), encoding="utf-8")

def get_flag(icao):
    if not icao or icao == "????": return "🏳️"
    icao = str(icao)
    m = {"UK": "ua", "EP": "pl", "ED": "de", "LF": "fr", "EG": "gb", "EH": "nl", "LI": "it", "LE": "es", "LO": "at", "KJ": "us", "UU": "ru", "UR": "ru"}
    return f":flag_{m.get(icao[:2], 'white')}:"

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
        async with session.request(method, url, headers=HEADERS, json=body) as r:
            return await r.json() if r.status == 200 else None
    except: return None

@client.event
async def on_ready():
    logging.info(f"Бот запущений як {client.user}")
    client.loop.create_task(main_loop())

async def main_loop():
    await client.wait_until_ready()
    channel = client.get_channel(CHANNEL_ID)
    if not channel: return

    state = load_state()
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                # 1. АКТИВНІ ПОЛЬОТИ
                ongoing = await fetch_api(session, "/flights/ongoing")
                if ongoing and "results" in ongoing:
                    for f in ongoing["results"]:
                        fid = str(f.get("_id") or f.get("id"))
                        if not fid or fid == "None": continue
                        
                        state.setdefault(fid, {})
                        cs = f.get("callsign")
                        if not cs: continue # Пропускаємо, якщо немає позивного

                        dep = f.get("departure", {}).get("icao") or "????"
                        arr = f.get("arrival", {}).get("icao") or "????"
                        ac = f.get("aircraft", {}).get("airframe", {}).get("ident") or "A/C"
                        
                        # ВЗЛІТ
                        if f.get("takeoffTimeAct") and not state[fid].get("takeoff"):
                            det = await fetch_api(session, f"/flight/{fid}")
                            pilot = det["flight"].get("pilot", {}).get("fullname", "Pilot") if det else "Pilot"
                            await channel.send(f"🛫 **{cs} departed**\n{get_flag(dep)}{dep} ➡️ {get_flag(arr)}{arr}\n✈️ {ac}\n👨‍✈️ {pilot}")
                            state[fid]["takeoff"] = True

                        # ПОСАДКА
                        if f.get("arrTimeAct") and not state[fid].get("landing"):
                            det = await fetch_api(session, f"/flight/{fid}")
                            fpm = det["flight"].get("lastState", {}).get("speed", {}).get("touchDownRate", "N/A") if det else "N/A"
                            await channel.send(f"🛬 **{cs} arrived**\n{get_flag(dep)}{dep} ➡️ {get_flag(arr)}{arr}\n📉 {fpm} FPM")
                            state[fid]["landing"] = True

                # 2. ЗАВЕРШЕНІ ПОЛЬОТИ
                recent = await fetch_api(session, "/flights/recent", method="POST", body={"count": 5})
                if recent and "results" in recent:
                    for f in recent["results"]:
                        fid = str(f.get("_id") or f.get("id"))
                        if not fid or fid == "None" or fid in state and state[fid].get("completed"):
                            continue
                        
                        det = await fetch_api(session, f"/flight/{fid}")
                        if not det or "flight" not in det: continue
                        
                        fl = det["flight"]
                        cs = fl.get("callsign")
                        # ГОЛОВНИЙ ФІЛЬТР: якщо позивного немає або це пустий запис - ігноруємо
                        if not cs or cs == "N/A": continue

                        dep = fl.get("departure", {}).get("icao") or "????"
                        arr = fl.get("arrival", {}).get("icao") or "????"
                        
                        # Додаткова перевірка: якщо обидва аеропорти невідомі - це пустий лог
                        if dep == "????" and arr == "????": continue

                        ac = fl.get("aircraft", {}).get("airframe", {}).get("ident") or "A/C"
                        pilot = fl.get("pilot", {}).get("fullname") or "Pilot"
                        
                        # Мережа
                        raw_net = fl.get("network")
                        if isinstance(raw_net, dict): net = str(raw_net.get("name") or "OFFLINE").upper()
                        else: net = str(raw_net or "OFFLINE").upper()

                        msg = (
                            f"😎 **{cs} completed**\n"
                            f"{get_flag(dep)}{dep} ➡️ {get_flag(arr)}{arr}\n"
                            f"✈️ {ac} | 👨‍✈️ {pilot} | 🌐 {net}\n"
                            f"⭐ {fl.get('rating', '0.00')} | 💰 {fl.get('finances', {}).get('totalIncome', 0)}$"
                        )
                        await channel.send(msg)
                        state.setdefault(fid, {})["completed"] = True

                save_state(state)
            except Exception as e:
                logging.error(f"Цикл: {e}")
            await asyncio.sleep(CHECK_INTERVAL)

client.run(DISCORD_TOKEN)

import discord
import aiohttp
import asyncio
import json
import os
import logging
from pathlib import Path

# ---------- НАЛАШТУВАННЯ (Береться з Railway Variables) ----------
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
    m = {"UK": "ua", "EP": "pl", "ED": "de", "LF": "fr", "EG": "gb", "EH": "nl", "LI": "it", "LE": "es", "LO": "at", "KJ": "us", "UU": "ru", "UR": "ru"}
    return f":flag_{m.get(icao[:2], 'white')}:"

def get_timing(delay):
    if delay is None: return "⏱️ Unknown"
    if delay > 5: return f"🔴 Delayed (+{delay} min)"
    if delay < -5: return f"🟡 Earlier ({-delay} min)"
    return "🟢 On time"

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
    state = load_state()

    async with aiohttp.ClientSession() as session:
        while True:
            try:
                # 1. Перевірка активних рейсів (Takeoff / Landing)
                ongoing = await fetch_api(session, "/flights/ongoing")
                if ongoing and "results" in ongoing:
                    for f in ongoing["results"]:
                        fid = str(f["id"])
                        state.setdefault(fid, {})
                        
                        # Дані для повідомлення
                        cs = f["callsign"]
                        dep, arr = f["departure"]["icao"], f["arrival"]["icao"]
                        ac = f.get("aircraft", {}).get("airframe", {}).get("ident", "A/C")
                        pax = f.get("pax", 0)
                        cargo = f.get("cargo", 0)

                        # ТАКЕOFF
                        if f.get("takeoffTimeAct") and not state[fid].get("takeoff"):
                            det = await fetch_api(session, f"/flight/{fid}")
                            pilot = det["flight"]["pilot"]["fullname"] if det else "Pilot"
                            msg = (
                                f"🛫 **{cs} departed**\n"
                                f"{get_flag(dep)}{dep} ➡️ {get_flag(arr)}{arr}\n"
                                f"✈️ {ac}\n"
                                f"🕒 {get_timing(f.get('delay'))}\n"
                                f"👨‍✈️ {pilot}\n"
                                f"📦 {pax} pax / {cargo} kg cargo"
                            )
                            await channel.send(msg)
                            state[fid]["takeoff"] = True

                        # LANDING
                        if f.get("arrTimeAct") and not state[fid].get("landing"):
                            det = await fetch_api(session, f"/flight/{fid}")
                            pilot = det["flight"]["pilot"]["fullname"] if det else "Pilot"
                            fpm = det["flight"].get("lastState", {}).get("speed", {}).get("touchDownRate", 0) if det else "N/A"
                            msg = (
                                f"🛬 **{cs} arrived**\n"
                                f"{get_flag(dep)}{dep} ➡️ {get_flag(arr)}{arr}\n"
                                f"✈️ {ac}\n"
                                f"🕒 {get_timing(f.get('delay'))}\n"
                                f"📉 {fpm} FPM\n"
                                f"👨‍✈️ {pilot}\n"
                                f"📦 {pax} pax / {cargo} kg cargo"
                            )
                            await channel.send(msg)
                            state[fid]["landing"] = True

                # 2. Перевірка закритих рейсів (Completed)
                recent = await fetch_api(session, "/flights/recent", method="POST", body={"count": 5})
                if recent and "results" in recent:
                    for f in recent["results"]:
                        fid = str(f["id"])
                        if f.get("close") and not state.get(fid, {}).get("completed"):
                            state.setdefault(fid, {})
                            det = await fetch_api(session, f"/flight/{fid}")
                            if det:
                                fl = det["flight"]
                                msg = (
                                    f"😎 **{fl['callsign']} completed**\n"
                                    f"{get_flag(fl['departure']['icao'])}{fl['departure']['icao']} ➡️ {get_flag(fl['arrival']['icao'])}{fl['arrival']['icao']}\n"
                                    f"✈️ {fl['aircraft']['airframe']['ident']}\n"
                                    f"👨‍✈️ {fl['pilot']['fullname']}\n"
                                    f"🌐 {fl.get('network', 'OFFLINE').upper()}\n"
                                    f"📦 {fl.get('pax', 0)} pax / {fl.get('cargo', 0)} kg cargo\n"
                                    f"📏 {fl.get('distance', 0)} nm / ⏱️ {fl.get('flightTime', 0)} min\n"
                                    f"💰 {fl.get('finances', {}).get('totalIncome', 0)}$\n"
                                    f"⭐ {fl.get('rating', '0.00')}"
                                )
                                await channel.send(msg)
                                state[fid]["completed"] = True

                save_state(state)
            except Exception as e:
                logging.error(f"Помилка циклу: {e}")
            
            await asyncio.sleep(CHECK_INTERVAL)

client.run(DISCORD_TOKEN)
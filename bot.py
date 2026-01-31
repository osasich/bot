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
intents.message_content = True # Потрібно для читання команд
client = discord.Client(intents=intents)

# ---------- ДОПОМІЖНІ ФУНКЦІЇ ----------
def load_state():
    if not STATE_FILE.exists(): return {}
    try: return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except: return {}

def save_state(state):
    try:
        if len(state) > 100: state = dict(list(state.items())[-50:])
        STATE_FILE.write_text(json.dumps(state), encoding="utf-8")
    except: pass

def get_flag(icao):
    if not icao or len(icao) < 2: return "🏳️"
    icao = icao.upper()
    prefixes = {
        'UK': 'UA', 'KJ': 'US', 'K': 'US', 'C': 'CA', 'Y': 'AU', 'Z': 'CN',
        'EG': 'GB', 'LF': 'FR', 'ED': 'DE', 'ET': 'DE', 'LI': 'IT', 'LE': 'ES',
        'EP': 'PL', 'LK': 'CZ', 'LH': 'HU', 'LO': 'AT', 'LS': 'CH', 'EB': 'BE',
        'EH': 'NL', 'EK': 'DK', 'EN': 'NO', 'ES': 'SE', 'EF': 'FI', 'LT': 'TR',
        'LG': 'GR', 'U': 'RU', 'UM': 'BY', 'UB': 'AZ', 'UG': 'GE', 'UD': 'AM',
        'UA': 'KZ', 'O': 'SA', 'V': 'IN', 'W': 'ID', 'F': 'ZA', 'S': 'BR'
    }
    iso = prefixes.get(icao[:2]) or prefixes.get(icao[:1])
    if not iso: return "🏳️"
    return "".join([chr(ord(c) + 127397) for c in iso])

def get_timing(delay):
    try:
        d = float(delay)
        if d > 5: return f"🔴 Затримка {int(d)} хв"
        if d < -5: return f"🟡 Раніше на {abs(int(d))} хв"
        return "🟢 Вчасно"
    except: return "⏱️ Невідомо"

def format_time(minutes):
    if not minutes: return "00:00"
    return f"{int(minutes // 60):02d}:{int(minutes % 60):02d}"

async def fetch_api(session, path, method="GET", body=None):
    try:
        async with session.request(method, f"{BASE_URL}{path}", headers=HEADERS, json=body, timeout=10) as r:
            return await r.json() if r.status == 200 else None
    except: return None

# ---------- ГЕНЕРАТОР ПОВІДОМЛЕННЯ ----------
async def send_flight_message(channel, status, f, details_type="ongoing"):
    """
    status: 'Departed', 'Arrived', 'Completed'
    """
    # 1. Дані
    cs = f.get("flightNumber") or f.get("callsign") or "N/A"
    airline = f.get("airline", {}).get("icao", "")
    full_cs = f"{airline} {cs}" if airline else cs
    
    dep = f.get("dep", {}).get("icao", "????")
    arr = f.get("arr", {}).get("icao", "????")
    ac = f.get("aircraft", {}).get("airframe", {}).get("name", "A/C")
    pilot = f.get("pilot", {}).get("fullname", "Pilot")
    
    # Payload
    if details_type == "result":
        pax = f.get("result", {}).get("totals", {}).get("payload", {}).get("pax", 0)
        cargo = f.get("result", {}).get("totals", {}).get("payload", {}).get("cargo", 0)
    else:
        pax = f.get("payload", {}).get("pax", 0)
        cargo = f.get("payload", {}).get("cargo", 0)

    # 2. Формування тексту
    if status == "Departed":
        delay = f.get("delay", 0)
        msg = (f"🛫 **{full_cs} departed**\n"
               f"{get_flag(dep)}{dep} ➡️ {get_flag(arr)}{arr}\n"
               f"✈️ {ac}\n"
               f"{get_timing(delay)}\n"
               f"👨‍✈️ {pilot}\n"
               f"👫 {pax} / 📦 {cargo} kg")

    elif status == "Arrived":
        # FPM логіка
        fpm = f.get("lastState", {}).get("speed", {}).get("touchDownRate", 0)
        # Якщо нуль, пробуємо VS або ставимо N/A (для тесту підставимо число якщо 0)
        if fpm == 0 and details_type == "test": fpm = -152 
        
        delay = f.get("delay", 0)
        
        msg = (f"🛬 **{full_cs} arrived**\n"
               f"{get_flag(dep)}{dep} ➡️ {get_flag(arr)}{arr}\n"
               f"✈️ {ac}\n"
               f"{get_timing(delay)}\n"
               f"📉 {int(fpm)} FPM\n"
               f"👨‍✈️ {pilot}\n"
               f"👫 {pax} / 📦 {cargo} kg")

    elif status == "Completed":
        net_data = f.get("network")
        net = (net_data.get("name") if isinstance(net_data, dict) else str(net_data)) or "OFFLINE"
        
        t = f.get("result", {}).get("totals", {})
        dist = t.get("distance", 0)
        ftime = t.get("time", 0)
        income = t.get("revenue", 0)
        rating = f.get("rating", 0)

        msg = (f"😎 **{full_cs} completed**\n"
               f"{get_flag(dep)}{dep} ➡️ {get_flag(arr)}{arr}\n"
               f"✈️ {ac}\n"
               f"👨‍✈️ {pilot}\n"
               f"🌐 {net.upper()}\n"
               f"👫 {pax} / 📦 {cargo} kg\n"
               f"📏 {dist} nm / ⏱️ {format_time(ftime)}\n"
               f"💰 {income} $\n"
               f"⭐ {rating}")

    await channel.send(msg)

# ---------- КОМАНДА ДЛЯ ТЕСТУВАННЯ ----------
@client.event
async def on_message(message):
    if message.author == client.user: return

    if message.content == "!test":
        await message.channel.send("🛠️ **Запуск симуляції польоту...**")
        
        # Фейкові дані
        mock_flight = {
            "flightNumber": "TEST777",
            "airline": {"icao": "OSA"},
            "dep": {"icao": "UKKK"},
            "arr": {"icao": "UKBB"},
            "aircraft": {"airframe": {"name": "Boeing 737-800"}},
            "pilot": {"fullname": "Test Pilot"},
            "payload": {"pax": 150, "cargo": 2500},
            "delay": -2,
            "network": {"name": "VATSIM"},
            "lastState": {"speed": {"touchDownRate": -145}},
            "result": {
                "totals": {
                    "distance": 350,
                    "time": 55,
                    "revenue": 4500,
                    "payload": {"pax": 150, "cargo": 2500}
                }
            },
            "rating": 9.8
        }

        await asyncio.sleep(1)
        await send_flight_message(message.channel, "Departed", mock_flight, "test")
        
        await asyncio.sleep(2)
        await send_flight_message(message.channel, "Arrived", mock_flight, "test")
        
        await asyncio.sleep(2)
        await send_flight_message(message.channel, "Completed", mock_flight, "test")
        
        await message.channel.send("✅ **Тест завершено!**")

# ---------- ГОЛОВНИЙ ЦИКЛ ----------
async def main_loop():
    await client.wait_until_ready()
    channel = client.get_channel(CHANNEL_ID)
    state = load_state()

    async with aiohttp.ClientSession() as session:
        while True:
            try:
                # 1. АКТИВНІ
                ongoing = await fetch_api(session, "/flights/ongoing")
                if ongoing and "results" in ongoing:
                    for raw_f in ongoing["results"]:
                        fid = str(raw_f.get("_id") or raw_f.get("id"))
                        # Для активних треба деталі
                        det = await fetch_api(session, f"/flight/{fid}")
                        if not det or "flight" not in det: continue
                        f = det["flight"]

                        state.setdefault(fid, {})
                        
                        # ВЗЛІТ
                        if f.get("takeoffTimeAct") and not state[fid].get("takeoff"):
                            await send_flight_message(channel, "Departed", f, "ongoing")
                            state[fid]["takeoff"] = True

                        # ПОСАДКА
                        if f.get("arrTimeAct") and not state[fid].get("landing"):
                            await send_flight_message(channel, "Arrived", f, "ongoing")
                            state[fid]["landing"] = True

                # 2. ЗАКРИТІ
                recent = await fetch_api(session, "/flights/recent", method="POST", body={"count": 5})
                if recent and "results" in recent:
                    for raw_f in recent["results"]:
                        fid = str(raw_f.get("_id") or raw_f.get("id"))
                        if fid in state and state[fid].get("completed"): continue
                        if not raw_f.get("close"): continue

                        det = await fetch_api(session, f"/flight/{fid}")
                        if not det or "flight" not in det: continue
                        f = det["flight"]

                        await send_flight_message(channel, "Completed", f, "result")
                        state.setdefault(fid, {})["completed"] = True

                save_state(state)
            except Exception as e: print(f"Error: {e}")
            await asyncio.sleep(CHECK_INTERVAL)

@client.event
async def on_ready():
    print(f"✅ Бот {client.user} запущений")
    client.loop.create_task(main_loop())

client.run(DISCORD_TOKEN)

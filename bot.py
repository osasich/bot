import discord
import aiohttp
import asyncio
import json
import os
import logging
import re
import random
from pathlib import Path

# ---------- SETTINGS ----------
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID")) if os.getenv("CHANNEL_ID") else 0
NEWSKY_API_KEY = os.getenv("NEWSKY_API_KEY")

STATE_FILE = Path("sent.json")
CHECK_INTERVAL = 30
BASE_URL = "https://newsky.app/api/airline-api"
HEADERS = {"Authorization": f"Bearer {NEWSKY_API_KEY}"}

logging.basicConfig(level=logging.INFO)
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# ---------- HELPERS ----------
def load_state():
    if not STATE_FILE.exists(): return {}
    try: return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except: return {}

def save_state(state):
    try:
        if len(state) > 100: state = dict(list(state.items())[-50:])
        STATE_FILE.write_text(json.dumps(state), encoding="utf-8")
    except: pass

def clean_airport_name(name):
    if not name: return ""
    name = re.sub(r"\(.*?\)", "", name)
    removals = ["International", "Regional", "Airport", "Aerodrome", "Air Base", "Intl", "  "]
    for word in removals:
        name = name.replace(word, "")
    return name.strip()

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
        if d > 5: return f"🔴 **Delay** (+{int(d)} min)"
        if d < -5: return f"🟡 **Early** ({int(d)} min)"
        return "🟢 **On time**"
    except: return "⏱️ **N/A**"

def format_time(minutes):
    if not minutes: return "00:00"
    return f"{int(minutes // 60):02d}:{int(minutes % 60):02d}"

def get_rating_square(rating):
    try:
        r = float(rating)
        if r >= 9.5: return "🟩"
        if r >= 8.0: return "🟨"
        if r >= 5.0: return "🟧"
        return "🟥"
    except: return "⬜"

# --- 🔥 ОТРИМАННЯ FPM ТА G-FORCE 🔥 ---
def get_landing_data(f, details_type):
    """Повертає рядок формату: 📉 -123 fpm, 1.3 G"""
    
    # Фейк для тесту
    if details_type == "test":
        fpm = -random.randint(50, 400)
        g = round(random.uniform(0.9, 1.8), 2)
        return f"📉 **{fpm} fpm**, **{g} G**"

    fpm = 0
    g_force = 0.0
    found = False

    # 1. Пошук у violations/events (Найточніше, бо Newsky сюди записує посадку як подію)
    if "result" in f and "violations" in f["result"]:
        for v in f["result"]["violations"]:
            # Шукаємо об'єкт touchDown всередині payload
            payload = v.get("entry", {}).get("payload", {})
            td = payload.get("touchDown", {})
            
            if td:
                if "rate" in td: 
                    fpm = int(td["rate"])
                    found = True
                if "gForce" in td: 
                    g_force = float(td["gForce"])
                    found = True
                
                # Якщо знайшли хоч щось - виходимо
                if found: break

    # 2. Якщо не знайшли в violations, шукаємо в landing object (для ідеальних посадок)
    if not found and "landing" in f and f["landing"]:
        td = f["landing"]
        if "rate" in td: fpm = int(td["rate"])
        if "touchDownRate" in td: fpm = int(td["touchDownRate"])
        if "gForce" in td: g_force = float(td["gForce"])
        if fpm != 0 or g_force != 0: found = True

    # 3. Fallback (Last State - тут зазвичай немає G, але є FPM)
    if not found:
        val = f.get("lastState", {}).get("speed", {}).get("touchDownRate")
        if val: 
            fpm = int(val)
            found = True

    # Формуємо рядок результату
    if found and fpm != 0:
        # Робимо FPM завжди з мінусом, якщо це зниження
        fpm_val = -abs(fpm)
        # Якщо G = 0, не показуємо його, або показуємо як N/A
        g_str = f", **{g_force} G**" if g_force > 0 else ""
        return f"📉 **{fpm_val} fpm**{g_str}"
    
    return "📉 **N/A**"

async def fetch_api(session, path, method="GET", body=None):
    try:
        async with session.request(method, f"{BASE_URL}{path}", headers=HEADERS, json=body, timeout=10) as r:
            return await r.json() if r.status == 200 else None
    except: return None

# ---------- MESSAGE GENERATOR ----------
async def send_flight_message(channel, status, f, details_type="ongoing"):
    cs = f.get("flightNumber") or f.get("callsign") or "N/A"
    airline = f.get("airline", {}).get("icao", "")
    full_cs = f"{airline} {cs}" if airline else cs
    
    dep_icao = f.get("dep", {}).get("icao", "????")
    dep_name = clean_airport_name(f.get("dep", {}).get("name"))
    arr_icao = f.get("arr", {}).get("icao", "????")
    arr_name = clean_airport_name(f.get("arr", {}).get("name"))
    
    ac = f.get("aircraft", {}).get("airframe", {}).get("name", "A/C")
    pilot = f.get("pilot", {}).get("fullname", "Pilot")
    
    if details_type == "result":
        pax = f.get("result", {}).get("totals", {}).get("payload", {}).get("pax", 0)
        cargo = f.get("result", {}).get("totals", {}).get("payload", {}).get("cargo", 0)
    else:
        pax = f.get("payload", {}).get("pax", 0)
        cargo = f.get("payload", {}).get("cargo", 0)

    embed = None

    # === 1. DEPARTED ===
    if status == "Departed":
        delay = f.get("delay", 0)
        desc = (
            f"{get_flag(dep_icao)} **{dep_icao}** ({dep_name}) ➡️ {get_flag(arr_icao)} **{arr_icao}** ({arr_name})\n\n"
            f"✈️ **{ac}**\n\n"
            f"{get_timing(delay)}\n\n"
            f"👨‍✈️ **{pilot}**\n\n"
            f"👫 **{pax}** Pax  |  📦 **{cargo}** kg"
        )
        embed = discord.Embed(title=f"🛫 {full_cs} departed", description=desc, color=0x3498db)

    # === 2. ARRIVED ===
    elif status == "Arrived":
        delay = f.get("delay", 0)
        desc = (
            f"{get_flag(dep_icao)} **{dep_icao}** ({dep_name}) ➡️ {get_flag(arr_icao)} **{arr_icao}** ({arr_name})\n\n"
            f"✈️ **{ac}**\n\n"
            f"{get_timing(delay)}\n\n"
            f"👨‍✈️ **{pilot}**\n\n"
            f"👫 **{pax}** Pax  |  📦 **{cargo}** kg"
        )
        embed = discord.Embed(title=f"🛬 {full_cs} arrived", description=desc, color=0x3498db)

    # === 3. COMPLETED ===
    elif status == "Completed":
        net_data = f.get("network")
        net = (net_data.get("name") if isinstance(net_data, dict) else str(net_data)) or "OFFLINE"
        
        t = f.get("result", {}).get("totals", {})
        dist = t.get("distance", 0)
        ftime = t.get("time", 0)
        income = t.get("revenue", 0)
        rating = f.get("rating", 0.0)
        
        # ОТРИМУЄМО РЯДОК FPM + G
        landing_info = get_landing_data(f, details_type)

        desc = (
            f"{get_flag(dep_icao)} **{dep_icao}** ({dep_name}) ➡️ {get_flag(arr_icao)} **{arr_icao}** ({arr_name})\n\n"
            f"✈️ **{ac}**\n\n"
            f"👨‍✈️ **{pilot}**\n\n"
            f"🌐 **{net.upper()}**\n\n"
            f"{landing_info}\n\n" 
            f"👫 **{pax}** Pax  |  📦 **{cargo}** kg\n\n"
            f"📏 **{dist}** nm  |  ⏱️ **{format_time(ftime)}**\n\n"
            f"💰 **{income} $**\n\n"
            f"{get_rating_square(rating)} **{rating}**"
        )
        embed = discord.Embed(title=f"😎 {full_cs} completed", description=desc, color=0x2ecc71)

    if embed:
        await channel.send(embed=embed)

# ---------- TEST COMMAND ----------
@client.event
async def on_message(message):
    if message.author == client.user: return
    if message.content == "!test":
        await message.channel.send("🛠️ **Test with G-Force...**")
        mock = {
            "flightNumber": "TEST1", "airline": {"icao": "OSA"},
            "dep": {"icao": "UKKK", "name": "Kyiv Zhuliany"}, "arr": {"icao": "UKBB", "name": "Boryspil"},
            "aircraft": {"airframe": {"name": "Boeing 737-800"}},
            "pilot": {"fullname": "Test Pilot"},
            "payload": {"pax": 100, "cargo": 1500},
            "delay": -12, "network": {"name": "VATSIM"},
            # Імітація Landing Data
            "result": {
                "violations": [
                    { "entry": { "payload": { "touchDown": {"rate": 185, "gForce": 1.34} } } }
                ],
                "totals": {"distance": 350, "time": 55, "revenue": 2500, "payload": {"pax": 100, "cargo": 1500}}
            },
            "rating": 9.9
        }
        await send_flight_message(message.channel, "Departed", mock, "test")
        await asyncio.sleep(1)
        await send_flight_message(message.channel, "Arrived", mock, "test")
        await asyncio.sleep(1)
        await send_flight_message(message.channel, "Completed", mock, "test")

# ---------- MAIN LOOP ----------
async def main_loop():
    await client.wait_until_ready()
    channel = client.get_channel(CHANNEL_ID)
    state = load_state()

    async with aiohttp.ClientSession() as session:
        while True:
            try:
                # 1. Active Flights
                ongoing = await fetch_api(session, "/flights/ongoing")
                if ongoing and "results" in ongoing:
                    print(f"📡 Tracking {len(ongoing['results'])} flights...", end='\r')
                    for raw_f in ongoing["results"]:
                        fid = str(raw_f.get("_id") or raw_f.get("id"))
                        det = await fetch_api(session, f"/flight/{fid}")
                        if not det or "flight" not in det: continue
                        f = det["flight"]
                        
                        cs = f.get("flightNumber") or f.get("callsign") or "N/A"
                        if cs == "N/A": continue
                        
                        state.setdefault(fid, {})

                        if f.get("takeoffTimeAct") and not state[fid].get("takeoff"):
                            await send_flight_message(channel, "Departed", f, "ongoing")
                            state[fid]["takeoff"] = True

                        if f.get("arrTimeAct") and not state[fid].get("landing"):
                            await send_flight_message(channel, "Arrived", f, "ongoing")
                            state[fid]["landing"] = True

                # 2. Completed Flights
                recent = await fetch_api(session, "/flights/recent", method="POST", body={"count": 5})
                if recent and "results" in recent:
                    for raw_f in recent["results"]:
                        fid = str(raw_f.get("_id") or raw_f.get("id"))
                        if fid in state and state[fid].get("completed"): continue
                        if not raw_f.get("close"): continue

                        det = await fetch_api(session, f"/flight/{fid}")
                        if not det or "flight" not in det: continue
                        f = det["flight"]
                        
                        cs = f.get("flightNumber") or f.get("callsign") or "N/A"
                        if cs == "N/A": continue

                        await send_flight_message(channel, "Completed", f, "result")
                        state.setdefault(fid, {})["completed"] = True
                        print(f"✅ Report Sent: {cs}")

                save_state(state)
            except Exception as e: print(f"Loop Error: {e}")
            await asyncio.sleep(CHECK_INTERVAL)

@client.event
async def on_ready():
    print(f"✅ Bot online: {client.user}")
    print("🚀 MONITORING STARTED")
    client.loop.create_task(main_loop())

client.run(DISCORD_TOKEN)

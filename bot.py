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
# Використовуємо надійну базу JSON
AIRPORTS_DB_URL = "https://raw.githubusercontent.com/mwgg/Airports/master/airports.json"
HEADERS = {"Authorization": f"Bearer {NEWSKY_API_KEY}"}

logging.basicConfig(level=logging.INFO)
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# Глобальна змінна для бази аеропортів
AIRPORTS_DB = {}

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

def clean_text(text):
    """Чистить назву від зайвих слів (Case Insensitive)"""
    if not text: return ""
    # Видаляємо дужки
    text = re.sub(r"\(.*?\)", "", text)
    
    # Список слів для видалення
    removals = ["International", "Regional", "Airport", "Aerodrome", "Air Base", "Intl"]
    
    # Видаляємо слова, ігноруючи регістр
    for word in removals:
        pattern = re.compile(re.escape(word), re.IGNORECASE)
        text = pattern.sub("", text)
        
    # Прибираємо зайві пробіли та коми
    return text.strip().strip(",").strip()

# --- 🌍 ЗАВАНТАЖЕННЯ БАЗИ ---
async def update_airports_db():
    global AIRPORTS_DB
    print("🌍 Downloading airports database...")
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(AIRPORTS_DB_URL) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    AIRPORTS_DB = {}
                    # Перезберігаємо з ключами у Upper Case для надійності
                    for k, v in data.items():
                        AIRPORTS_DB[k.upper()] = {
                            "country": v.get("country", "XX"),
                            "city": v.get("city", ""),
                            "name": v.get("name", "")
                        }
                    print(f"✅ Airports DB loaded! ({len(AIRPORTS_DB)} airports)")
                else:
                    print("⚠️ Failed to load airports DB")
        except Exception as e:
            print(f"⚠️ Error loading DB: {e}")

def get_flag(country_code):
    if not country_code or country_code == "XX": return "🏳️"
    try:
        return "".join([chr(ord(c) + 127397) for c in country_code.upper()])
    except:
        return "🏳️"

# --- 🧠 РОЗУМНЕ ФОРМУВАННЯ НАЗВИ (SMART CITY LOGIC) ---
def format_airport_string(icao, api_name):
    """
    Формує: 🇺🇦 UKBB (Kyiv Boryspil) або 🇵🇹 LPMA (Funchal Madeira)
    """
    icao = icao.upper()
    flag = "🏳️"
    display_text = clean_text(api_name) # Дефолтне значення
    
    # Спробуємо знайти в базі
    db_data = AIRPORTS_DB.get(icao)
    
    if db_data:
        city = db_data.get("city", "") or ""
        name = db_data.get("name", "") or ""
        country = db_data.get("country", "XX")
        flag = get_flag(country)
        
        # --- FIX: KIEV -> KYIV ---
        if city.lower() == "kiev": city = "Kyiv"
        name = name.replace("Kiev", "Kyiv") # Заміна в назві аеропорту теж
        
        # Чистимо назву аеропорту від "Airport" тощо
        clean_name = clean_text(name)
        
        # --- ГОЛОВНА ЛОГІКА ---
        if city and clean_name:
            # Перевірка: чи є назва міста всередині назви аеропорту?
            # Наприклад: City="London", Name="London Heathrow" -> True
            if city.lower() in clean_name.lower():
                display_text = clean_name
            else:
                # Наприклад: City="Funchal", Name="Madeira" -> False -> "Funchal Madeira"
                display_text = f"{city} {clean_name}"
        elif clean_name:
            display_text = clean_name
        elif city:
            display_text = city

    else:
        # Якщо в базі немає, пробуємо вгадати прапор по префіксу
        if len(icao) >= 2:
            prefix = icao[:2]
            manual_map = {
                'UK': 'UA', 'KJ': 'US', 'K': 'US', 'EG': 'GB', 'LF': 'FR', 'ED': 'DE', 
                'LP': 'PT', 'LE': 'ES', 'LI': 'IT', 'U': 'RU' # Додав LP для Португалії про всяк випадок
            }
            code = manual_map.get(prefix, "XX")
            if code != "XX":
                flag = get_flag(code)

    return f"{flag} **{icao}** ({display_text})"

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

# --- FPM + G-Force Search ---
def get_landing_data(f, details_type):
    if details_type == "test":
        fpm = -random.randint(50, 400)
        g = round(random.uniform(0.9, 1.8), 2)
        return f"📉 **{fpm} fpm**, **{g} G**"

    fpm = 0
    g_force = 0.0
    found = False

    # 1. Violations/Events
    if "result" in f and "violations" in f["result"]:
        for v in f["result"]["violations"]:
            payload = v.get("entry", {}).get("payload", {})
            td = payload.get("touchDown", {})
            if td:
                if "rate" in td: 
                    fpm = int(td["rate"])
                    found = True
                if "gForce" in td: 
                    g_force = float(td["gForce"])
                    found = True
                if found: break

    # 2. Landing Object
    if not found and "landing" in f and f["landing"]:
        td = f["landing"]
        if "rate" in td: fpm = int(td["rate"])
        if "touchDownRate" in td: fpm = int(td["touchDownRate"])
        if "gForce" in td: g_force = float(td["gForce"])
        if fpm != 0 or g_force != 0: found = True

    # 3. Fallback
    if not found:
        val = f.get("lastState", {}).get("speed", {}).get("touchDownRate")
        if val: 
            fpm = int(val)
            found = True

    if found and fpm != 0:
        fpm_val = -abs(fpm)
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
    # Links
    fid = f.get("_id") or f.get("id") or "test_id"
    if status == "Completed":
        flight_url = f"https://newsky.app/flight/{fid}"
    else:
        flight_url = f"https://newsky.app/map/{fid}"

    cs = f.get("flightNumber") or f.get("callsign") or "N/A"
    airline = f.get("airline", {}).get("icao", "")
    full_cs = f"{airline} {cs}" if airline else cs
    
    # --- AIRPORT FORMATTING ---
    dep_icao = f.get("dep", {}).get("icao", "????")
    dep_api_name = f.get("dep", {}).get("name", "")
    dep_str = format_airport_string(dep_icao, dep_api_name)
    
    arr_icao = f.get("arr", {}).get("icao", "????")
    arr_api_name = f.get("arr", {}).get("name", "")
    arr_str = format_airport_string(arr_icao, arr_api_name)
    
    ac = f.get("aircraft", {}).get("airframe", {}).get("name", "A/C")
    pilot = f.get("pilot", {}).get("fullname", "Pilot")
    
    # Cargo Calc
    raw_pax = 0
    raw_cargo_units = 0

    if details_type == "result":
        raw_pax = f.get("result", {}).get("totals", {}).get("payload", {}).get("pax", 0)
        raw_cargo_units = f.get("result", {}).get("totals", {}).get("payload", {}).get("cargo", 0)
    else:
        raw_pax = f.get("payload", {}).get("pax", 0)
        raw_cargo_units = f.get("payload", {}).get("cargo", 0)
    
    cargo_kg = int(raw_cargo_units * 108)

    embed = None

    # === 1. DEPARTED ===
    if status == "Departed":
        delay = f.get("delay", 0)
        desc = (
            f"{dep_str} ➡️ {arr_str}\n\n"
            f"✈️ **{ac}**\n\n"
            f"{get_timing(delay)}\n\n"
            f"👨‍✈️ **{pilot}**\n\n"
            f"👫 **{raw_pax}** Pax  |  📦 **{cargo_kg}** kg"
        )
        embed = discord.Embed(title=f"🛫 {full_cs} departed", url=flight_url, description=desc, color=0x3498db)

    # === 2. ARRIVED ===
    elif status == "Arrived":
        delay = f.get("delay", 0)
        desc = (
            f"{dep_str} ➡️ {arr_str}\n\n"
            f"✈️ **{ac}**\n\n"
            f"{get_timing(delay)}\n\n"
            f"👨‍✈️ **{pilot}**\n\n"
            f"👫 **{raw_pax}** Pax  |  📦 **{cargo_kg}** kg"
        )
        embed = discord.Embed(title=f"🛬 {full_cs} arrived", url=flight_url, description=desc, color=0x3498db)

    # === 3. COMPLETED ===
    elif status == "Completed":
        net_data = f.get("network")
        net = (net_data.get("name") if isinstance(net_data, dict) else str(net_data)) or "OFFLINE"
        
        t = f.get("result", {}).get("totals", {})
        dist = t.get("distance", 0)
        ftime = t.get("time", 0)
        
        raw_balance = int(t.get("balance", 0))
        formatted_balance = f"{raw_balance:,}".replace(",", ".")
        
        rating = f.get("rating", 0.0)
        landing_info = get_landing_data(f, details_type)

        desc = (
            f"{dep_str} ➡️ {arr_str}\n\n"
            f"✈️ **{ac}**\n\n"
            f"👨‍✈️ **{pilot}**\n\n"
            f"🌐 **{net.upper()}**\n\n"
            f"{landing_info}\n\n" 
            f"👫 **{raw_pax}** Pax  |  📦 **{cargo_kg}** kg\n\n"
            f"📏 **{dist}** nm  |  ⏱️ **{format_time(ftime)}**\n\n"
            f"💰 **{formatted_balance} $**\n\n"
            f"{get_rating_square(rating)} **{rating}**"
        )
        embed = discord.Embed(title=f"😎 {full_cs} completed", url=flight_url, description=desc, color=0x2ecc71)

    if embed:
        await channel.send(embed=embed)

# ---------- TEST COMMAND ----------
@client.event
async def on_message(message):
    if message.author == client.user: return
    if message.content == "!test":
        await message.channel.send("🛠️ **Test (Kyiv+Boryspil / Funchal+Madeira)...**")
        mock = {
            "_id": "697f11b19da57b990acafff9",
            "flightNumber": "TEST1", "airline": {"icao": "OSA"},
            "dep": {"icao": "UKBB", "name": "Boryspil International Airport"}, # Має бути Kyiv Boryspil
            "arr": {"icao": "LPMA", "name": "Madeira Airport"}, # Має бути Funchal Madeira (PT flag)
            "aircraft": {"airframe": {"name": "Boeing 737-800"}},
            "pilot": {"fullname": "Test Pilot"},
            "payload": {"pax": 100, "cargo": 40}, 
            "delay": -12, "network": {"name": "VATSIM"},
            "landing": {"rate": -185, "gForce": 1.34},
            "result": {
                "totals": {
                    "distance": 350, "time": 55, 
                    "balance": 12500,
                    "payload": {"pax": 100, "cargo": 40}
                }
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
    await update_airports_db()
    
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

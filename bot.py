import discord
import aiohttp
import asyncio
import json
import os
import logging
import re
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

# ---------- ДОПОМІЖНІ ФУНКЦІЇ ----------
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

def clean_airport_name(name):
    """
    Скорочує назву аеропорту.
    UKKK (Ihor Sikorsky Kyiv International Airport) -> Kyiv
    """
    if not name: return ""
    
    # 1. Якщо є дужки (наприклад "Kyiv (Zhuliany)"), беремо те, що в дужках, або видаляємо їх
    # Тут ми просто видаляємо зайві слова
    name = name.replace("International Airport", "")
    name = name.replace("Regional Airport", "")
    name = name.replace("Airport", "")
    name = name.replace("Aerodrome", "")
    name = name.replace("Air Base", "")
    
    # Видаляємо вміст у дужках (часто там сміття або код)
    name = re.sub(r"\(.*?\)", "", name)
    
    # Прибираємо зайві пробіли
    return name.strip()

def get_flag(icao):
    """
    Повертає прапор країни на основі ICAO коду аеропорту.
    Працює для всього світу.
    """
    if not icao or len(icao) < 2: return "🏳️"
    icao = icao.upper()
    
    # Мапа префіксів ICAO -> ISO код країни
    # Це покриває 99% країн світу
    prefixes = {
        'UK': 'UA', # Ukraine
        'K': 'US',  # USA (4-letter start with K)
        'C': 'CA',  # Canada
        'Y': 'AU',  # Australia
        'Z': 'CN',  # China (mostly)
        'RJ': 'JP', 'RO': 'JP', # Japan
        'EG': 'GB', # UK
        'LF': 'FR', # France
        'ED': 'DE', 'ET': 'DE', # Germany
        'LI': 'IT', # Italy
        'LE': 'ES', # Spain
        'LP': 'PT', # Portugal
        'EP': 'PL', # Poland
        'LK': 'CZ', # Czechia
        'LH': 'HU', # Hungary
        'LZ': 'SK', # Slovakia
        'LO': 'AT', # Austria
        'LS': 'CH', # Switzerland
        'EB': 'BE', # Belgium
        'EH': 'NL', # Netherlands
        'EK': 'DK', # Denmark
        'EN': 'NO', # Norway
        'ES': 'SE', # Sweden
        'EF': 'FI', # Finland
        'LG': 'GR', # Greece
        'LT': 'TR', # Turkey
        'UU': 'RU', 'UE': 'RU', 'UH': 'RU', 'UI': 'RU', 'UL': 'RU', 'UN': 'RU', 'UO': 'RU', 'UR': 'RU', 'US': 'RU', 'UW': 'RU', # Russia
        'UM': 'BY', # Belarus
        'UB': 'AZ', # Azerbaijan
        'UG': 'GE', # Georgia
        'UD': 'AM', # Armenia
        'UA': 'KZ', # Kazakhstan
        'UT': 'UZ', 'UC': 'KG', 'UA': 'KZ', # Central Asia
        'O': 'SA',  # Middle East (Generic match, works for OM, OE, etc usually)
        'V': 'IN',  # India/SE Asia (Generic)
        'W': 'ID',  # Indonesia/SE Asia
        'F': 'ZA',  # Africa (Generic)
        'H': 'EG',  # North East Africa
        'S': 'BR',  # South America
        'M': 'MX',  # Central America
    }

    # Логіка пошуку: спочатку шукаємо точний збіг 2 букв, потім 1 букви
    iso = prefixes.get(icao[:2])
    if not iso:
        iso = prefixes.get(icao[:1])
    
    if not iso: return "🏳️"

    # Конвертуємо ISO код (наприклад 'UA') в Emoji прапор
    return "".join([chr(ord(c) + 127397) for c in iso])

def format_time(minutes):
    """00:00 формат"""
    if not minutes: return "00:00"
    h = int(minutes // 60)
    m = int(minutes % 60)
    return f"{h:02d}:{m:02d}"

def get_rating_square(rating):
    try:
        r = float(rating)
        if r >= 9.5: return "🟩"
        if r >= 8.0: return "🟨"
        if r >= 5.0: return "🟧"
        return "🟥"
    except: return "⬜"

async def fetch_api(session, path, method="GET", body=None):
    url = f"{BASE_URL}{path}"
    try:
        async with session.request(method, url, headers=HEADERS, json=body, timeout=10) as r:
            if r.status == 200: return await r.json()
            return None
    except Exception as e:
        print(f"⚠️ API Error: {e}")
        return None

# ---------- БОТ ----------
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
                # === 1. АКТИВНІ (ВЗЛІТ / ПОСАДКА) ===
                ongoing_list = await fetch_api(session, "/flights/ongoing")
                if ongoing_list and "results" in ongoing_list:
                    for raw_f in ongoing_list["results"]:
                        fid = str(raw_f.get("_id") or raw_f.get("id"))
                        if not fid or fid == "None": continue

                        det = await fetch_api(session, f"/flight/{fid}")
                        if not det or "flight" not in det: continue
                        f = det["flight"]

                        cs = f.get("flightNumber") or f.get("callsign") or "N/A"
                        if cs == "N/A": continue

                        state.setdefault(fid, {})
                        
                        # Дані
                        dep_icao = f.get("dep", {}).get("icao") or "????"
                        arr_icao = f.get("arr", {}).get("icao") or "????"
                        ac_name = f.get("aircraft", {}).get("airframe", {}).get("name") or "Aircraft"
                        pilot = f.get("pilot", {}).get("fullname", "Pilot")
                        
                        # --- ВЗЛІТ ---
                        if f.get("takeoffTimeAct") and not state[fid].get("takeoff"):
                            embed = discord.Embed(title=f"🛫 {cs} Departed", color=0x3498db)
                            embed.description = (
                                f"{get_flag(dep_icao)} **{dep_icao}** ➡️ {get_flag(arr_icao)} **{arr_icao}**\n\n"
                                f"✈️ {ac_name}\n"
                                f"👨‍✈️ {pilot}"
                            )
                            await channel.send(embed=embed)
                            state[fid]["takeoff"] = True

                        # --- ПОСАДКА ---
                        if f.get("arrTimeAct") and not state[fid].get("landing"):
                            fpm = f.get("lastState", {}).get("speed", {}).get("touchDownRate", 0)
                            embed = discord.Embed(title=f"🛬 {cs} Arrived", color=0x3498db)
                            embed.description = (
                                f"{get_flag(dep_icao)} **{dep_icao}** ➡️ {get_flag(arr_icao)} **{arr_icao}**\n\n"
                                f"📉 **{fpm} fpm**"
                            )
                            await channel.send(embed=embed)
                            state[fid]["landing"] = True
                        
                        await asyncio.sleep(1.5)

                # === 2. ЗАВЕРШЕНІ (ПОВНИЙ ЗВІТ) ===
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

                        # --- ЗБІР ДАНИХ ---
                        airline_icao = f.get("airline", {}).get("icao") or "AIR"
                        
                        # Аеропорти (чистимо назви)
                        dep_icao = f.get("dep", {}).get("icao") or "????"
                        dep_name = clean_airport_name(f.get("dep", {}).get("name"))
                        
                        arr_icao = f.get("arr", {}).get("icao") or "????"
                        arr_name = clean_airport_name(f.get("arr", {}).get("name"))
                        
                        # Літак
                        ac_ident = f.get("aircraft", {}).get("airframe", {}).get("ident") or ""
                        ac_reg = f.get("aircraft", {}).get("registry") or "REG" # Іноді немає реєстрації в JSON
                        # Якщо немає registry, спробуємо скласти (Newsky іноді не віддає reg)
                        if ac_reg == "REG": ac_reg = ac_ident

                        pilot = f.get("pilot", {}).get("fullname", "Pilot")
                        
                        net_data = f.get("network")
                        network = "OFFLINE"
                        if isinstance(net_data, dict):
                            network = (net_data.get("name") or "OFFLINE").upper()
                        
                        # Stats
                        totals = f.get("result", {}).get("totals", {})
                        pax = totals.get("payload", {}).get("pax", 0)
                        cargo = totals.get("payload", {}).get("cargo", 0)
                        dist = int(totals.get("distance", 0))
                        time_min = totals.get("time", 0)
                        income = int(totals.get("revenue", 0))
                        rating = f.get("rating", 0.0)
                        
                        # --- ДИЗАЙН ПОВІДОМЛЕННЯ (ВІДСТУПИ + ПРАПОРИ) ---
                        embed = discord.Embed(
                            title=f"😎 {airline_icao} {cs} completed",
                            color=0x2f3136
                        )
                        
                        desc = (
                            f"{get_flag(dep_icao)} **{dep_icao} ({dep_name})** ➡️ {get_flag(arr_icao)} **{arr_icao} ({arr_name})**\n\n"
                            f"✈️ **{ac_reg} ({ac_ident})**\n\n"
                            f"👨‍✈️ **{pilot}**\n\n"
                            f"🌐 **{network}**\n\n"
                            f"👫 **{pax}** / 📦 **{cargo} kg**\n\n"
                            f"📏 **{dist}nm** / ⏱️ **{format_time(time_min)}**\n\n"
                            f"💰 **{income}$**\n\n"
                            f"{get_rating_square(rating)} **{rating}**"
                        )
                        
                        embed.description = desc
                        embed.color = 0x3498db # Синя смужка

                        await channel.send(embed=embed)
                        state.setdefault(fid, {})["completed"] = True
                        print(f"✅ Звіт відправлено: {cs}")

                save_state(state)
            except Exception as e:
                print(f"❌ Error loop: {e}")
            
            await asyncio.sleep(CHECK_INTERVAL)

client.run(DISCORD_TOKEN)

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
CHECK_INTERVAL = 20
BASE_URL = "https://newsky.app/api/airline-api"
HEADERS = {"Authorization": f"Bearer {NEWSKY_API_KEY}"}

logging.basicConfig(level=logging.INFO)
intents = discord.Intents.default()
client = discord.Client(intents=intents)

# ---------- ФУНКЦІЇ ----------

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
    """Робить назву короткою: Ihor Sikorsky Kyiv -> Kyiv"""
    if not name: return ""
    # Видаляємо дужки і все що в них
    name = re.sub(r"\(.*?\)", "", name)
    # Видаляємо сміттєві слова
    removals = ["International", "Regional", "Airport", "Aerodrome", "Air Base", "Intl"]
    for word in removals:
        name = name.replace(word, "")
    return name.strip()

def get_flag(icao):
    """Повертає прапор за кодом ICAO"""
    if not icao or len(icao) < 2: return "🏳️"
    icao = icao.upper()
    
    # Словник префіксів
    prefixes = {
        'UK': 'UA', 'KJ': 'US', 'K': 'US', 'C': 'CA', 'Y': 'AU', 'Z': 'CN',
        'EG': 'GB', 'LF': 'FR', 'ED': 'DE', 'ET': 'DE', 'LI': 'IT', 'LE': 'ES',
        'EP': 'PL', 'LK': 'CZ', 'LH': 'HU', 'LO': 'AT', 'LS': 'CH', 'EB': 'BE',
        'EH': 'NL', 'EK': 'DK', 'EN': 'NO', 'ES': 'SE', 'EF': 'FI', 'LT': 'TR',
        'LG': 'GR', 'U': 'RU', 'UM': 'BY', 'UB': 'AZ', 'UG': 'GE', 'UD': 'AM',
        'UA': 'KZ', 'O': 'SA', 'V': 'IN', 'W': 'ID', 'F': 'ZA', 'S': 'BR'
    }
    
    # Шукаємо по 2 буквах, потім по 1
    iso = prefixes.get(icao[:2]) or prefixes.get(icao[:1])
    if not iso: return "🏳️"
    
    return "".join([chr(ord(c) + 127397) for c in iso])

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

async def fetch_api(session, path, method="GET", body=None):
    try:
        async with session.request(method, f"{BASE_URL}{path}", headers=HEADERS, json=body, timeout=10) as r:
            return await r.json() if r.status == 200 else None
    except Exception as e:
        print(f"API Error: {e}")
        return None

# ---------- ГЕНЕРАТОР ПОВІДОМЛЕННЯ (EMBED) ----------
def create_embed(status, f, details_type="ongoing"):
    """
    status: 'Departed', 'Arrived', 'Completed'
    f: об'єкт польоту (flight details)
    """
    # 1. Основні дані
    cs = f.get("flightNumber") or f.get("callsign") or "N/A"
    airline_icao = f.get("airline", {}).get("icao") or "AIR"
    
    # 2. Аеропорти (Clean names)
    dep_icao = f.get("dep", {}).get("icao") or "????"
    dep_name = clean_airport_name(f.get("dep", {}).get("name"))
    arr_icao = f.get("arr", {}).get("icao") or "????"
    arr_name = clean_airport_name(f.get("arr", {}).get("name"))
    
    # 3. Літак і Пілот
    ac_name = f.get("aircraft", {}).get("airframe", {}).get("name") or "Aircraft"
    ac_ident = f.get("aircraft", {}).get("airframe", {}).get("ident") or ""
    pilot = f.get("pilot", {}).get("fullname", "Pilot")
    
    # 4. Payload (Пасажири/Вантаж)
    # Newsky зберігає payload по-різному для active і finished
    if details_type == "result":
        # Для завершеного беремо з totals
        payload = f.get("result", {}).get("totals", {}).get("payload", {})
    else:
        # Для активного беремо напряму
        payload = f.get("payload", {})
        
    pax = payload.get("pax", 0)
    cargo = payload.get("cargo", 0)

    # 5. Мережа
    net_data = f.get("network")
    network = (net_data.get("name") if isinstance(net_data, dict) else "OFFLINE") or "OFFLINE"
    
    # --- ЗБИРАЄМО ОПИС ---
    # Рядок 1: Аеропорти
    desc = f"{get_flag(dep_icao)} **{dep_icao} ({dep_name})** ➡️ {get_flag(arr_icao)} **{arr_icao} ({arr_name})**\n\n"
    
    # Рядок 2: Літак
    desc += f"✈️ **{ac_name} ({ac_ident})**\n"
    
    # Рядок 3: Пілот
    desc += f"👨‍✈️ **{pilot}**\n"
    
    # Рядок 4: Мережа
    desc += f"🌐 **{network.upper()}**\n\n"
    
    # Рядок 5: Завантаження
    desc += f"👫 **{pax}** / 📦 **{cargo} kg**\n"

    # --- СПЕЦИФІКА ДЛЯ КОЖНОГО СТАТУСУ ---
    
    embed_color = 0x3498db # Default Blue
    
    if status == "Departed":
        embed_color = 0x3498db # Blue
        # Можна додати час вильоту або ETE, якщо є
        
    elif status == "Arrived":
        embed_color = 0x3498db # Blue
        # Пробуємо дістати FPM
        fpm = f.get("lastState", {}).get("speed", {}).get("touchDownRate", 0)
        
        # FIX: Якщо FPM 0 (API глюк), пробуємо взяти VS
        if fpm == 0:
            vs = f.get("lastState", {}).get("speed", {}).get("vs", 0)
            # Якщо VS дуже малий, пишемо N/A, інакше показуємо VS як орієнтир
            fpm_str = f"{int(vs)}" if abs(vs) > 10 else "Calculating..."
        else:
            fpm_str = f"{int(fpm)}"
            
        desc += f"\n📉 **{fpm_str} fpm**"

    elif status == "Completed":
        embed_color = 0x2ecc71 # Green-ish (або темний як ти хотів)
        
        totals = f.get("result", {}).get("totals", {})
        dist = int(totals.get("distance", 0))
        time_min = totals.get("time", 0)
        income = int(totals.get("revenue", 0))
        rating = f.get("rating", 0.0)
        
        desc += f"📏 **{dist}nm** / ⏱️ **{format_time(time_min)}**\n"
        desc += f"💰 **{income}$**\n"
        desc += f"{get_rating_square(rating)} **{rating}**"

    # Створюємо об'єкт Embed
    # Заголовок: 😎 OSA 901N completed / 🛫 OSA 901N Departed
    title_emoji = "🛫" if status == "Departed" else "🛬" if status == "Arrived" else "😎"
    embed = discord.Embed(
        title=f"{title_emoji} {airline_icao} {cs} {status.lower()}",
        description=desc,
        color=0x2f3136 # Темний фон (бічна смужка буде залежати від налаштувань, тут ми ставимо колір)
    )
    embed.color = embed_color # Перезаписуємо колір смужки

    return embed

# ---------- ГОЛОВНИЙ ЦИКЛ ----------
@client.event
async def on_ready():
    print(f"✅ Бот онлайн: {client.user}")
    client.loop.create_task(main_loop())

async def main_loop():
    await client.wait_until_ready()
    channel = client.get_channel(CHANNEL_ID) or await client.fetch_channel(CHANNEL_ID)
    state = load_state()
    print("🚀 СТАРТ МОНІТОРИНГУ")

    async with aiohttp.ClientSession() as session:
        while True:
            try:
                # 1. АКТИВНІ (Departed / Arrived)
                ongoing = await fetch_api(session, "/flights/ongoing")
                if ongoing and "results" in ongoing:
                    for raw_f in ongoing["results"]:
                        fid = str(raw_f.get("_id") or raw_f.get("id"))
                        if not fid or fid == "None": continue

                        # Качаємо деталі
                        det = await fetch_api(session, f"/flight/{fid}")
                        if not det or "flight" not in det: continue
                        f = det["flight"]
                        
                        cs = f.get("flightNumber") or f.get("callsign") or "N/A"
                        if cs == "N/A": continue

                        state.setdefault(fid, {})

                        # ВЗЛІТ
                        if f.get("takeoffTimeAct") and not state[fid].get("takeoff"):
                            embed = create_embed("Departed", f, details_type="ongoing")
                            await channel.send(embed=embed)
                            state[fid]["takeoff"] = True
                            print(f"🛫 Departed: {cs}")

                        # ПОСАДКА
                        if f.get("arrTimeAct") and not state[fid].get("landing"):
                            embed = create_embed("Arrived", f, details_type="ongoing")
                            await channel.send(embed=embed)
                            state[fid]["landing"] = True
                            print(f"🛬 Arrived: {cs}")
                        
                        await asyncio.sleep(1.5)

                # 2. ЗАВЕРШЕНІ (Completed)
                recent = await fetch_api(session, "/flights/recent", method="POST", body={"count": 5})
                if recent and "results" in recent:
                    for raw_f in recent["results"]:
                        fid = str(raw_f.get("_id") or raw_f.get("id"))
                        if fid in state and state[fid].get("completed"): continue
                        if not raw_f.get("close"): continue # Тільки якщо рейс закрито

                        det = await fetch_api(session, f"/flight/{fid}")
                        if not det or "flight" not in det: continue
                        f = det["flight"]
                        
                        cs = f.get("flightNumber") or f.get("callsign") or "N/A"
                        if cs == "N/A": continue

                        embed = create_embed("Completed", f, details_type="result")
                        await channel.send(embed=embed)
                        
                        state.setdefault(fid, {})["completed"] = True
                        print(f"😎 Completed: {cs}")

                save_state(state)
            except Exception as e:
                print(f"Loop Error: {e}")
            
            await asyncio.sleep(CHECK_INTERVAL)

client.run(DISCORD_TOKEN)

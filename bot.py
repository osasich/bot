import discord
import aiohttp
import asyncio
import json
import os
import logging
import math
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

def get_flag(icao):
    if not icao or icao == "????": return "🏳️"
    # Спрощена мапа прапорів, можна розширювати
    m = {"UK": "ua", "EP": "pl", "ED": "de", "LF": "fr", "EG": "gb", "EH": "nl", 
         "LI": "it", "LE": "es", "LO": "at", "KJ": "us", "UU": "ru", "UR": "ru"}
    return f":flag_{m.get(str(icao)[:2], 'white')}:"

def format_time(minutes):
    """Перетворює хвилини у формат 00:00"""
    if not minutes: return "00:00"
    h = int(minutes // 60)
    m = int(minutes % 60)
    return f"{h:02d}:{m:02d}"

def get_rating_square(rating):
    """Повертає кольоровий квадрат залежно від рейтингу"""
    try:
        r = float(rating)
        if r >= 9.5: return "🟩"
        if r >= 8.0: return "🟨"
        if r >= 6.0: return "🟧"
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
                # Для активних повідомлення простіші (текстові або прості ембеди)
                ongoing_list = await fetch_api(session, "/flights/ongoing")
                if ongoing_list and "results" in ongoing_list:
                    for raw_f in ongoing_list["results"]:
                        fid = str(raw_f.get("_id") or raw_f.get("id"))
                        if not fid or fid == "None": continue

                        # Щоб не спамити запитами, перевіряємо чи ми вже писали про цей етап
                        # Але треба деталі, щоб дізнатися статус
                        det = await fetch_api(session, f"/flight/{fid}")
                        if not det or "flight" not in det: continue
                        f = det["flight"]

                        cs = f.get("flightNumber") or f.get("callsign") or "N/A"
                        if cs == "N/A": continue

                        state.setdefault(fid, {})
                        
                        # Дані
                        dep = f.get("dep", {}).get("icao") or "????"
                        arr = f.get("arr", {}).get("icao") or "????"
                        ac_name = f.get("aircraft", {}).get("airframe", {}).get("name") or "Aircraft"
                        pilot = f.get("pilot", {}).get("fullname", "Pilot")
                        
                        # --- ВЗЛІТ ---
                        if f.get("takeoffTimeAct") and not state[fid].get("takeoff"):
                            embed = discord.Embed(title=f"🛫 {cs} Departed", color=0x3498db)
                            embed.description = (f"{get_flag(dep)} **{dep}** ➡️ {get_flag(arr)} **{arr}**\n"
                                                 f"✈️ {ac_name}\n👨‍✈️ {pilot}")
                            await channel.send(embed=embed)
                            state[fid]["takeoff"] = True

                        # --- ПОСАДКА ---
                        if f.get("arrTimeAct") and not state[fid].get("landing"):
                            fpm = f.get("lastState", {}).get("speed", {}).get("touchDownRate", 0)
                            embed = discord.Embed(title=f"🛬 {cs} Arrived", color=0x3498db)
                            embed.description = (f"{get_flag(dep)} **{dep}** ➡️ {get_flag(arr)} **{arr}**\n"
                                                 f"📉 {fpm} fpm")
                            await channel.send(embed=embed)
                            state[fid]["landing"] = True
                        
                        await asyncio.sleep(1)

                # === 2. ЗАВЕРШЕНІ (КРАСИВИЙ ЗВІТ) ===
                recent = await fetch_api(session, "/flights/recent", method="POST", body={"count": 5})
                if recent and "results" in recent:
                    for raw_f in recent["results"]:
                        fid = str(raw_f.get("_id") or raw_f.get("id"))
                        # Перевірка: чи писали, чи закрито
                        if fid in state and state[fid].get("completed"): continue
                        if not raw_f.get("close"): continue

                        # Тягнемо повні дані
                        det = await fetch_api(session, f"/flight/{fid}")
                        if not det or "flight" not in det: continue
                        f = det["flight"]
                        
                        cs = f.get("flightNumber") or f.get("callsign") or "N/A"
                        if cs == "N/A": continue

                        # --- ЗБІР ДАНИХ ДЛЯ EMBED ---
                        
                        # Авіакомпанія (ICAO)
                        airline_icao = f.get("airline", {}).get("icao") or "AIR"
                        
                        # Аеропорти
                        dep_icao = f.get("dep", {}).get("icao") or "????"
                        dep_name = f.get("dep", {}).get("name") or ""
                        arr_icao = f.get("arr", {}).get("icao") or "????"
                        arr_name = f.get("arr", {}).get("name") or ""
                        
                        # Літак
                        ac_name = f.get("aircraft", {}).get("airframe", {}).get("name") or "Aircraft"
                        ac_ident = f.get("aircraft", {}).get("airframe", {}).get("ident") or "" # B738
                        
                        # Пілот і Мережа
                        pilot = f.get("pilot", {}).get("fullname", "Pilot")
                        net_data = f.get("network")
                        network = "OFFLINE"
                        if isinstance(net_data, dict):
                            network = (net_data.get("name") or "OFFLINE").upper()
                        
                        # Статистика (Totals)
                        totals = f.get("result", {}).get("totals", {})
                        
                        pax = totals.get("payload", {}).get("pax", 0)
                        cargo = totals.get("payload", {}).get("cargo", 0)
                        
                        dist = int(totals.get("distance", 0))
                        time_min = totals.get("time", 0)
                        income = int(totals.get("revenue", 0))
                        
                        rating = f.get("rating", 0.0)
                        
                        # --- СТВОРЕННЯ EMBED (Як на скріні) ---
                        
                        # Заголовок: 😎 OSA 17K completed
                        embed = discord.Embed(
                            title=f"😎 {airline_icao} {cs} completed",
                            color=0x2f3136 # Темний фон, Discord сам додасть синю смужку зліва
                        )
                        
                        # Тіло повідомлення
                        desc = (
                            f"{get_flag(dep_icao)} **{dep_icao} ({dep_name})** ➡️ {get_flag(arr_icao)} **{arr_icao} ({arr_name})**\n"
                            f"✈️ **{ac_name} ({ac_ident})**\n"
                            f"👨‍✈️ **{pilot}**\n"
                            f"🌐 **{network}**\n"
                            f"👫 **{pax}** / 📦 **{cargo} kg**\n"
                            f"📏 **{dist}nm** / ⏱️ **{format_time(time_min)}**\n"
                            f"💰 **{income}$**\n"
                            f"{get_rating_square(rating)} **{rating}**"
                        )
                        
                        embed.description = desc
                        # Щоб смужка зліва була синьою
                        embed.color = 0x3498db 

                        await channel.send(embed=embed)
                        
                        state.setdefault(fid, {})["completed"] = True
                        print(f"✅ Відправлено звіт: {cs}")

                save_state(state)
            except Exception as e:
                print(f"❌ Помилка циклу: {e}")
            
            await asyncio.sleep(CHECK_INTERVAL)

client.run(DISCORD_TOKEN)

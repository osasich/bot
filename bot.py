import discord
import aiohttp
import asyncio
import json
import os
import logging
import re
import random
import io
from pathlib import Path
from itertools import cycle

# ---------- НАЛАШТУВАННЯ ----------
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID")) if os.getenv("CHANNEL_ID") else 0
NEWSKY_API_KEY = os.getenv("NEWSKY_API_KEY")

STATE_FILE = Path("sent.json")
STATUS_FILE = Path("statuses.json")
CHECK_INTERVAL = 30
BASE_URL = "https://newsky.app/api/airline-api"
AIRPORTS_DB_URL = "https://raw.githubusercontent.com/mwgg/Airports/master/airports.json"
HEADERS = {"Authorization": f"Bearer {NEWSKY_API_KEY}"}

logging.basicConfig(level=logging.INFO)
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# Глобальна змінна для бази
AIRPORTS_DB = {}

# --- 🎭 СТАНДАРТНІ СТАТУСИ ---
DEFAULT_STATUSES = [
    {"type": "watch", "name": "🔴 YouTube KAZUAR AVIA"},
    {"type": "play",  "name": "🕹️ Tracking with Newsky.app"}
]

# --- 📚 БАЗА ЖАРТІВ (НОВІ ПРОМІЖКИ) ---
FPM_DB = {
    "butter": [ # 0 - 60 fpm
        "Ти привид? Сенсори кажуть 0 G.",
        "Чисте масло. Пасажири думають, що ми ще летимо.",
        "Така посадка вартує мільйон баксів.",
        "Kiss landing. Літак закохався в смугу.",
        "10/10. Навіть кава у пілотів не розлилась.",
        "Ти змастив асфальт салом? Зізнавайся.",
        "Це левітація. Гоґвортс висилає листа.",
        "Ти продав душу за таку посадку?",
        "Навіть муха на смузі не прокинулась.",
        "Ідеально. Занадто ідеально. Ти чітер?",
        "Капітан плаче від щастя.",
        "Сіммер, прокинься, це сон. Так не буває.",
        "Тобі треба працювати хірургом.",
        "Магія поза Хогвартсом заборонена.",
        "Боїнг в шоці, що він так вміє."
    ],
    "good": [ # 61 - 180 fpm
        "Професійно. Як по книжці.",
        "Солідно. Другий пілот зацінив.",
        "Хороша робота, кеп. Можна йти пити пиво.",
        "М'яко, ніжно, стабільно. Лайк.",
        "Пасажири аплодують (хоча вони боти).",
        "Красиво пішов, красиво сів.",
        "Це була посадка здорової людини.",
        "Ти точно не робот? Дуже рівно.",
        "Смуга каже тобі 'дякую'.",
        "Не масло, але дуже близько.",
        "Майстер-клас для новачків.",
        "Стабільно. Без понтів, просто якісно.",
        "За таку посадку дають премію.",
        "Комфорт-клас. Ніхто не жаліється.",
        "Все ціле, всі довольні."
    ],
    "firm": [ # 181 - 350 fpm (Ryanair zone)
        "Ryanair style! Твердо і чітко.",
        "Це називається 'Positive Landing'.",
        "Не масло, але й не щебінь. Піде.",
        "Відчув смугу п'ятою точкою. Норм.",
        "Сів і сів, чого бубніти. Безпечно ж.",
        "Головне, що амортизатори працюють.",
        "Трохи гупнув, але спишемо на боковий вітер.",
        "По-чоловічому. Без зайвих ніжностей.",
        "Пасажири прокинулись — значить точно сіли.",
        "Диспетчер поставив галочку 'Прибув'.",
        "Типовий рейс економ-класу.",
        "Боїнг любить, коли його так садять.",
        "Ну, колеса розкрутив миттєво.",
        "Не соромно, але й хвалити нема за що.",
        "Літак цілий, совість чиста."
    ],
    "hard": [ # 351 - 600 fpm
        "Ай! Мій хребет вийшов з чату.",
        "Стоматологи дякують за нових клієнтів.",
        "Жорстко. Як життя в Україні.",
        "Ти хотів пробити смугу наскрізь?",
        "Підвіска сказала 'кря', але вижила.",
        "Кава на штанях у другого пілота. Ти винен.",
        "Пасажири трохи напружились.",
        "Це була посадка чи падіння з контролем?",
        "Диспетчер питає, чи потрібна тобі швидка.",
        "Ну... зате ми на землі.",
        "Наступного разу спробуй вирівнювати.",
        "Ще трохи і стійки пішли б у салон.",
        "Остеохондроз гарантовано всім на борту.",
        "Звук був неприємний.",
        "Ти переплутав літак з цеглою?"
    ],
    "damage": [ # 601 - 900 fpm
        "Техніки плачуть біля ангару.",
        "Шасі написали заяву на звільнення.",
        "Ти зробив з Боїнга лоурайдер.",
        "Вітаю, ти погнув стійки.",
        "Це не посадка, це напад на аеропорт.",
        "Страхова компанія вже виїхала за тобою.",
        "Звук удару чули в сусідньому місті.",
        "Літак потребує капітального ремонту.",
        "Пасажири вимагають повернення коштів.",
        "Ти впевнений, що у тебе є ліцензія?",
        "Це було схоже на падіння шафи.",
        "Мінус спина, мінус літак, мінус премія.",
        "Амортизатори вийшли через крило.",
        "Це фіаско, братан.",
        "Це вже рівень Spirit Airlines."
    ],
    "crash": [ # 901+ fpm
        "Землетрус 9 балів. Епіцентр — ти.",
        "💀 WASTED. Ти в пеклі.",
        "Літака більше немає. Є тільки кратер.",
        "Це був метеорит? Ні, це ти сів.",
        "Привіт шахтарям. Ти пробив кору.",
        "Апокаліпсис сьогодні. Автор — ти.",
        "Ти знищив аеропорт. Game Over.",
        "Навіть чорна скринька не вижила.",
        "Геологи зафіксували новий каньйон.",
        "Це не політ, це буріння свердловини.",
        "F. Press F to pay respects.",
        "Ти вбив всіх. Молодець.",
        "Служба розслідувань (NTSB) вже виїхала.",
        "Тут нема слів. Тільки дим і уламки.",
        "АЛЛО, ШВИДКУ! ТУТ БІДА!"
    ]
}

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

def load_statuses():
    if not STATUS_FILE.exists(): return list(DEFAULT_STATUSES)
    try:
        data = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
        if not data: return list(DEFAULT_STATUSES)
        return data
    except: return list(DEFAULT_STATUSES)

def save_statuses():
    try: STATUS_FILE.write_text(json.dumps(status_list, indent=4), encoding="utf-8")
    except Exception as e: print(f"⚠️ Failed to save statuses: {e}")

status_list = load_statuses()
status_cycle = cycle(status_list)

def clean_text(text):
    if not text: return ""
    text = re.sub(r"\(.*?\)", "", text)
    removals = ["International", "Regional", "Airport", "Aerodrome", "Air Base", "Intl"]
    for word in removals:
        pattern = re.compile(re.escape(word), re.IGNORECASE)
        text = pattern.sub("", text)
    return text.strip().strip(",").strip()

# --- 🎲 FPM LOGIC WITH NEW RANGES ---
def get_fpm_joke(fpm):
    fpm = abs(int(fpm))
    joke_list = []
    category_icon = ""
    
    if fpm <= 60:
        joke_list = FPM_DB["butter"]
        category_icon = "🧈" # Butter
    elif fpm <= 180:
        joke_list = FPM_DB["good"]
        category_icon = "🟢" # Good
    elif fpm <= 350:
        joke_list = FPM_DB["firm"]
        category_icon = "🟡" # Firm
    elif fpm <= 600:
        joke_list = FPM_DB["hard"]
        category_icon = "😬" # Ouch
    elif fpm <= 900:
        joke_list = FPM_DB["damage"]
        category_icon = "🛠️" # Broken
    else:
        joke_list = FPM_DB["crash"]
        category_icon = "💀" # Dead
    
    selected_joke = random.choice(joke_list)
    return f"{category_icon} **{fpm} fpm** — {selected_joke}"

# --- 🌍 ЗАВАНТАЖЕННЯ БАЗИ ---
async def update_airports_db():
    global AIRPORTS_DB
    print("🌍 Downloading airports database...")
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(AIRPORTS_DB_URL) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    AIRPORTS_DB = {}
                    for k, v in data.items():
                        AIRPORTS_DB[k.upper()] = {
                            "country": v.get("country", "XX"),
                            "city": v.get("city", ""),
                            "name": v.get("name", "")
                        }
                    print(f"✅ Airports DB loaded! ({len(AIRPORTS_DB)} airports)")
                else:
                    print(f"⚠️ Failed to load airports DB: Status {resp.status}")
        except Exception as e:
            print(f"⚠️ Error loading DB: {e}")

def get_flag(country_code):
    if not country_code or country_code == "XX": return "🏳️"
    try: return "".join([chr(ord(c) + 127397) for c in country_code.upper()])
    except: return "🏳️"

def format_airport_string(icao, api_name):
    icao = icao.upper()
    db_data = AIRPORTS_DB.get(icao)
    if db_data:
        city = db_data.get("city", "") or ""
        name = db_data.get("name", "") or ""
        country = db_data.get("country", "XX")
        if city.lower() == "kiev": city = "Kyiv"
        name = name.replace("Kiev", "Kyiv")
        clean_name = clean_text(name)
        display_text = ""
        if city and clean_name:
            if city.lower() in clean_name.lower(): display_text = clean_name
            else: display_text = f"{city} {clean_name}"
        elif clean_name: display_text = clean_name
        elif city: display_text = city
        else: display_text = clean_text(api_name)
        return f"{get_flag(country)} **{icao}** ({display_text})"
    flag = "🏳️"
    if len(icao) >= 2:
        prefix = icao[:2]
        manual_map = {'UK': 'UA', 'KJ': 'US', 'K': 'US', 'EG': 'GB', 'LF': 'FR', 'ED': 'DE', 'LP': 'PT', 'LE': 'ES', 'LI': 'IT', 'U': 'RU'}
        code = manual_map.get(prefix, "XX")
        if code != "XX": flag = get_flag(code)
    return f"{flag} **{icao}** ({clean_text(api_name)})"

def get_timing(delay):
    try:
        d = float(delay)
        if d > 15: return f"🔴 **Delay** (+{int(d)} min)"
        if d < -15: return f"🟡 **Early** ({int(d)} min)"
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

def get_landing_data(f, details_type):
    if details_type == "test":
        fpm = -random.randint(50, 400)
        g = round(random.uniform(0.9, 1.8), 2)
        return f"📉 **{fpm} fpm**, **{g} G**"
    fpm, g_force, found = 0, 0.0, False
    if "result" in f and "violations" in f["result"]:
        for v in f["result"]["violations"]:
            td = v.get("entry", {}).get("payload", {}).get("touchDown", {})
            if td:
                fpm, g_force, found = int(td.get("rate", 0)), float(td.get("gForce", 0)), True
                if found: break
    if not found and "landing" in f and f["landing"]:
        td = f["landing"]
        fpm, g_force, found = int(td.get("rate", 0)), float(td.get("gForce", 0)), True
    if not found:
        val = f.get("lastState", {}).get("speed", {}).get("touchDownRate")
        if val: fpm = int(val); found = True
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

async def send_flight_message(channel, status, f, details_type="ongoing"):
    fid = f.get("_id") or f.get("id") or "test_id"
    if status == "Completed": flight_url = f"https://newsky.app/flight/{fid}"
    else: flight_url = f"https://newsky.app/map/{fid}"

    cs = f.get("flightNumber") or f.get("callsign") or "N/A"
    airline = f.get("airline", {}).get("icao", "")
    full_cs = f"{airline} {cs}" if airline else cs
    dep_str = format_airport_string(f.get("dep", {}).get("icao", ""), f.get("dep", {}).get("name", ""))
    arr_str = format_airport_string(f.get("arr", {}).get("icao", ""), f.get("arr", {}).get("name", ""))
    ac = f.get("aircraft", {}).get("airframe", {}).get("name", "A/C")
    pilot = f.get("pilot", {}).get("fullname", "Pilot")
    
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
    arrow = " \u2003➡️\u2003 "

    if status == "Departed":
        delay = f.get("delay", 0)
        desc = (f"{dep_str}{arrow}{arr_str}\n\n✈️ **{ac}**\n\n{get_timing(delay)}\n\n👨‍✈️ **{pilot}**\n\n👫 **{raw_pax}** Pax  |  📦 **{cargo_kg}** kg")
        embed = discord.Embed(title=f"🛫 {full_cs} departed", url=flight_url, description=desc, color=0x3498db)

    elif status == "Completed":
        net_data = f.get("network")
        net = (net_data.get("name") if isinstance(net_data, dict) else str(net_data)) or "OFFLINE"
        t = f.get("result", {}).get("totals", {})
        dist = t.get("distance", 0)
        ftime = t.get("time", 0)
        raw_balance = int(t.get("balance", 0))
        formatted_balance = f"{raw_balance:,}".replace(",", ".")
        rating = f.get("rating", 0.0)
        delay = f.get("delay", 0)
        
        title_text = f"😎 {full_cs} completed"
        color_code = 0x2ecc71
        rating_str = f"{get_rating_square(rating)} **{rating}**"

        if raw_balance <= -900000: 
            title_text = f"💥 {full_cs} CRASHED"; color_code = 0x992d22; rating_str = "💀 **CRASH**"
        elif f.get("emergency") is True or (raw_balance == 0 and dist > 1):
            title_text = f"⚠️ {full_cs} EMERGENCY"; color_code = 0xe67e22; rating_str = "🟥 **EMEG**"
            
        landing_info = get_landing_data(f, details_type)
        desc = (f"{dep_str}{arrow}{arr_str}\n\n✈️ **{ac}**\n\n{get_timing(delay)}\n\n👨‍✈️ **{pilot}**\n\n🌐 **{net.upper()}**\n\n{landing_info}\n\n👫 **{raw_pax}** Pax  |  📦 **{cargo_kg}** kg\n\n📏 **{dist}** nm  |  ⏱️ **{format_time(ftime)}**\n\n💰 **{formatted_balance} $**\n\n{rating_str}")
        embed = discord.Embed(title=title_text, url=flight_url, description=desc, color=color_code)

    if embed: await channel.send(embed=embed)

async def change_status():
    current_status = next(status_cycle)
    activity_type = discord.ActivityType.playing
    if current_status["type"] == "watch": activity_type = discord.ActivityType.watching
    elif current_status["type"] == "listen": activity_type = discord.ActivityType.listening
    await client.change_presence(activity=discord.Activity(type=activity_type, name=current_status["name"]))

async def status_loop():
    await client.wait_until_ready()
    while not client.is_closed():
        await change_status()
        await asyncio.sleep(3600)

@client.event
async def on_message(message):
    if message.author == client.user: return
    is_admin = message.author.guild_permissions.administrator if message.guild else False

    # 📚 HELP COMMAND
    if message.content == "!help":
        embed = discord.Embed(title="📚 Bot Commands", color=0x3498db)
        desc = "**🔹 User Commands:**\n"
        desc += "**`!live`** — Show active flights 🟢\n"
        desc += "**`!fpm <num>`** — Rate my landing 😂\n"
        desc += "**`!help`** — Show this list\n\n"
        
        desc += "**🔒 Admin / System (Restricted):**\n"
        desc += "**`!status`** — System status\n"
        desc += "**`!test [min]`** — Run test scenarios\n"
        desc += "**`!spy <ID>`** — Dump flight JSON\n\n"
        
        desc += "**🎭 Status Management (Admin):**\n"
        desc += "**`!next`** — Force next status\n"
        desc += "**`!addstatus <type> <text>`** — Save & Add status\n"
        desc += "**`!delstatus [num]`** — Delete status\n"
        embed.description = desc
        await message.channel.send(embed=embed)
        return

    # 🟢 LIVE COMMAND
    if message.content == "!live":
        async with aiohttp.ClientSession() as session:
            data = await fetch_api(session, "/flights/ongoing")
            if not data or "results" not in data or len(data["results"]) == 0:
                return await message.channel.send("🦗 **No pilots in the sky right now.** Quiet day!")
            
            embed = discord.Embed(title=f"📡 Live Radar ({len(data['results'])})", color=0x2ecc71)
            for raw_f in data["results"]:
                fid = str(raw_f.get("_id") or raw_f.get("id"))
                det = await fetch_api(session, f"/flight/{fid}")
                if not det or "flight" not in det: continue
                f = det["flight"]
                cs = f.get("flightNumber") or f.get("callsign") or "N/A"
                pilot = f.get("pilot", {}).get("fullname", "Unknown")
                ac = f.get("aircraft", {}).get("airframe", {}).get("name", "Plane")
                dep = f.get("dep", {}).get("icao", "???")
                arr = f.get("arr", {}).get("icao", "???")
                status_txt = "Flying ✈️"
                if not f.get("takeoffTimeAct"): status_txt = "Boarding 🚪"
                embed.add_field(name=f"✈️ {cs} ({pilot})", value=f"**{dep}** ➡️ **{arr}**\n{ac} | {status_txt}", inline=False)
            await message.channel.send(embed=embed)
        return

    # 😂 FPM COMMAND
    if message.content.startswith("!fpm"):
        parts = message.content.split()
        if len(parts) < 2: return await message.channel.send("⚠️ Usage: `!fpm <number>` (e.g. `!fpm -150`)")
        try:
            val = int(parts[1])
            joke = get_fpm_joke(val)
            await message.channel.send(joke)
        except ValueError:
            await message.channel.send("🔢 Please enter a valid number!")
        return

    # --- ADMIN COMMANDS ---
    if message.content == "!next":
        if not is_admin: return await message.channel.send("🚫 **Access Denied**")
        await change_status()
        await message.channel.send("✅ **Status switched!**")
        return

    if message.content.startswith("!addstatus"):
        if not is_admin: return await message.channel.send("🚫 **Access Denied**")
        parts = message.content.split(maxsplit=2)
        if len(parts) < 3: return await message.channel.send("⚠️ Usage: `!addstatus <watch/play> <text>`")
        sType = parts[1].lower()
        if sType not in ["watch", "play", "listen"]: return await message.channel.send("⚠️ Use: `watch`, `play`, `listen`")
        status_list.append({"type": sType, "name": parts[2]})
        save_statuses()
        global status_cycle; status_cycle = cycle(status_list)
        await message.channel.send(f"✅ Saved & Added: **{parts[2]}**")
        return

    if message.content.startswith("!delstatus"):
        if not is_admin: return await message.channel.send("🚫 **Access Denied**")
        parts = message.content.split()
        if len(parts) == 1:
            list_str = "\n".join([f"`{i+1}.` {s['type'].upper()}: {s['name']}" for i, s in enumerate(status_list)])
            embed = discord.Embed(title="🗑️ Delete Status", description=f"Type `!delstatus <number>` to delete.\n\n{list_str}", color=0xe74c3c)
            return await message.channel.send(embed=embed)
        try:
            idx = int(parts[1]) - 1
            if 0 <= idx < len(status_list):
                if len(status_list) <= 1: return await message.channel.send("⚠️ Cannot delete the last status!")
                removed = status_list.pop(idx)
                save_statuses()
                status_cycle = cycle(status_list) 
                await message.channel.send(f"🗑️ Deleted & Saved: **{removed['name']}**")
            else: await message.channel.send("⚠️ Invalid number.")
 

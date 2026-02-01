import discord
import asyncio
import os

# ---------- НАЛАШТУВАННЯ ----------
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# Тут ми зберігаємо стан діалогу для кожного юзера
sessions = {}

# Питання для кожного етапу
QUESTIONS = [
    "**Етап 1/15:** Оберіть тип повідомлення:\n`1` - 🛫 Виліт (Departed)\n`2` - 🛬 Приліт (Arrived)\n`3` - 😎 Звіт (Completed/Crash)", # 0
    "**Етап 2/15:** Введіть **ICAO вильоту** (напр. `UKBB`):", # 1
    "**Етап 3/15:** Введіть **Місто та Назву вильоту** (напр. `Kyiv Boryspil`):", # 2
    "**Етап 4/15:** Введіть **ICAO прильоту** (напр. `LPMA`):", # 3
    "**Етап 5/15:** Введіть **Місто та Назву прильоту** (напр. `Funchal Madeira`):", # 4
    "**Етап 6/15:** Введіть **Позивний рейсу** (напр. `OSA 101`):", # 5
    "**Етап 7/15:** Введіть **Літак** (напр. `Boeing 737-800`):", # 6
    "**Етап 8/15:** Введіть **Ім'я пілота** (напр. `Capt. Test`):", # 7
    "**Етап 9/15:** Кількість **Пасажирів** (число, напр. `140`):", # 8
    "**Етап 10/15:** Вантаж у **кг** (число, напр. `4500`):", # 9
    "**Етап 11/15:** (Тільки для Звіту) **Вертикальна FPM** (напр. `-150`):", # 10
    "**Етап 12/15:** (Тільки для Звіту) **G-Force** (напр. `1.2`):", # 11
    "**Етап 13/15:** (Тільки для Звіту) **Мережа** (напр. `VATSIM`):", # 12
    "**Етап 14/15:** (Тільки для Звіту) **Дистанція (nm)** та **Час (хв)** через пробіл (напр. `450 95`):", # 13
    "**Етап 15/15:** (Тільки для Звіту) **Баланс ($)** та **Рейтинг** через пробіл.\n💡 *Для КРАШУ введіть мінус (напр. `-1000000 0`).*\n💡 *Приклад норм рейсу: `12500 9.9`*:" # 14
]

def get_flag(icao_code):
    if not icao_code or len(icao_code) < 2: return "🏳️"
    prefix = icao_code[:2].upper()
    # Проста мапа для основних країн (можна розширити)
    manual_map = {
        'UK': 'UA', 'KJ': 'US', 'K': 'US', 'EG': 'GB', 'LF': 'FR', 'ED': 'DE', 
        'LP': 'PT', 'LE': 'ES', 'LI': 'IT', 'U': 'RU', 'EP': 'PL', 'LT': 'TR'
    }
    country = manual_map.get(prefix, "XX")
    if country == "XX": return "🏳️"
    return "".join([chr(ord(c) + 127397) for c in country])

async def generate_embed(data):
    # Визначаємо тип
    msg_type = data[0] # "1", "2" або "3"
    
    # Формування рядків
    dep_flag = get_flag(data[1])
    arr_flag = get_flag(data[3])
    
    dep_str = f"{dep_flag} **{data[1].upper()}** ({data[2]})"
    arr_str = f"{arr_flag} **{data[3].upper()}** ({data[4]})"
    
    # Стрілочка
    arrow = " \u2003➡️\u2003 "
    
    # Основні дані
    callsign = data[5]
    plane = data[6]
    pilot = data[7]
    pax = data[8]
    cargo = data[9]
    
    embed = discord.Embed()
    
    # --- ЛОГІКА ДЛЯ РІЗНИХ ТИПІВ ---
    
    # 🛫 DEPARTED
    if msg_type == "1":
        embed.title = f"🛫 {callsign} departed"
        embed.color = 0x3498db # Blue
        embed.description = (
            f"{dep_str}{arrow}{arr_str}\n\n"
            f"✈️ **{plane}**\n\n"
            f"🟢 **On time**\n\n"
            f"👨‍✈️ **{pilot}**\n\n"
            f"👫 **{pax}** Pax  |  📦 **{cargo}** kg"
        )

    # 🛬 ARRIVED
    elif msg_type == "2":
        embed.title = f"🛬 {callsign} arrived"
        embed.color = 0x3498db # Blue
        embed.description = (
            f"{dep_str}{arrow}{arr_str}\n\n"
            f"✈️ **{plane}**\n\n"
            f"🟢 **On time**\n\n"
            f"👨‍✈️ **{pilot}**\n\n"
            f"👫 **{pax}** Pax  |  📦 **{cargo}** kg"
        )

    # 😎 COMPLETED / CRASH
    elif msg_type == "3":
        fpm = data[10]
        g_force = data[11]
        network = data[12]
        
        # Розбиваємо "450 95" на dist і time
        try: dist, time_min = data[13].split()
        except: dist, time_min = "0", "0"
        
        # Форматуємо час
        try: 
            tm = int(time_min)
            time_str = f"{tm // 60:02d}:{tm % 60:02d}"
        except: time_str = "00:00"

        # Розбиваємо "12500 9.9" на balance і rating
        try: balance_str, rating_str = data[14].split()
        except: balance_str, rating_str = "0", "0.0"
        
        # Логіка кольорів
        try:
            balance = int(balance_str)
            if balance <= -900000:
                embed.title = f"💥 {callsign} CRASHED"
                embed.color = 0x992d22 # Red
            elif balance == 0:
                embed.title = f"⚠️ {callsign} EMERGENCY"
                embed.color = 0xe67e22 # Orange
            else:
                embed.title = f"😎 {callsign} completed"
                embed.color = 0x2ecc71 # Green
        except:
            embed.title = f"😎 {callsign} completed"
            embed.color = 0x2ecc71

        # Форматування грошей
        fmt_bal = f"{int(balance_str):,}".replace(",", ".")

        # Квадратик рейтингу
        try:
            rt = float(rating_str)
            sq = "🟩" if rt >= 9.5 else "🟨" if rt >= 8.0 else "🟧" if rt >= 5.0 else "🟥"
        except: sq, rt = "⬜", 0.0

        embed.description = (
            f"{dep_str}{arrow}{arr_str}\n\n"
            f"✈️ **{plane}**\n\n"
            f"👨‍✈️ **{pilot}**\n\n"
            f"🌐 **{network}**\n\n"
            f"📉 **{fpm} fpm**, **{g_force} G**\n\n" 
            f"👫 **{pax}** Pax  |  📦 **{cargo}** kg\n\n"
            f"📏 **{dist}** nm  |  ⏱️ **{time_str}**\n\n"
            f"💰 **{fmt_bal} $**\n\n"
            f"{sq} **{rating_str}**"
        )

    return embed

@client.event
async def on_message(message):
    if message.author == client.user: return

    uid = message.author.id

    # СТАРТ
    if message.content == "!test":
        sessions[uid] = {"step": 0, "answers": []}
        await message.channel.send("🛠️ **Режим ручного створення скріншоту**")
        await message.channel.send(QUESTIONS[0])
        return

    # ОБРОБКА ВІДПОВІДЕЙ
    if uid in sessions:
        step = sessions[uid]["step"]
        content = message.content.strip()
        
        # Зберігаємо відповідь
        sessions[uid]["answers"].append(content)
        
        # Перевірка: якщо вибрали тип 1 або 2 (не звіт), то пропускаємо питання 10-14
        if step == 0:
            if content not in ["1", "2", "3"]:
                await message.channel.send("❌ Введіть 1, 2 або 3")
                sessions[uid]["answers"].pop()
                return

        # Наступний крок
        next_step = step + 1
        sessions[uid]["step"] = next_step

        # Якщо тип "Виліт" або "Приліт", ми пропускаємо технічні деталі звіту
        msg_type = sessions[uid]["answers"][0]
        if msg_type in ["1", "2"] and next_step == 10:
             # Генеруємо одразу
             embed = await generate_embed(sessions[uid]["answers"])
             await message.channel.send(embed=embed)
             del sessions[uid]
             return

        # Якщо дійшли до кінця списку питань (для типу 3)
        if next_step >= len(QUESTIONS):
            embed = await generate_embed(sessions[uid]["answers"])
            await message.channel.send(embed=embed)
            del sessions[uid]
        else:
            # Задаємо наступне питання
            await message.channel.send(QUESTIONS[next_step])

@client.event
async def on_ready():
    print(f"✅ Screenshot Generator Online: {client.user}")

client.run(DISCORD_TOKEN)

from selenium import webdriver  # type: ignore
from selenium.webdriver.common.by import By  # type: ignore
from selenium.webdriver.common.keys import Keys  # type: ignore
from selenium.webdriver.chrome.service import Service  # type: ignore
from webdriver_manager.chrome import ChromeDriverManager  # type: ignore
from selenium.webdriver.support.ui import WebDriverWait  # type: ignore
from selenium.webdriver.support import expected_conditions as EC  # type: ignore
from datetime import datetime, timedelta
import requests  # type: ignore
import json
import os
import sys

MODE = "today"  # Default

if len(sys.argv) > 1:
    if sys.argv[1].lower() in ["today", "tomorrow"]:
        MODE = sys.argv[1].lower()

# Telegram config
TELEGRAM_TOKEN = "7792099885:AAG9qfwBTaTqnlQCtw03OBJ7fgPKSSNVkVE"
CHAT_ID = "409897409"

def send_telegram_message(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": message}
    try:
        requests.post(url, data=data)
    except Exception as e:
        print("Ошибка при отправке в Telegram:", e)

# Emoji mapping
emoji_map = {
    "SHE": "🕵️",
    "FRO": "⚱️",
    "BNK": "💰",
    "APO": "☣️"
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE_DIR, "last_state.json")

# Load name associations
ASSOCIATIONS_FILE = os.path.join(os.path.dirname(__file__), "associations.json")

if not os.path.exists(ASSOCIATIONS_FILE):
    with open(ASSOCIATIONS_FILE, "w") as f:
        json.dump({}, f, indent=2)

try:
    with open(ASSOCIATIONS_FILE, "r") as f:
        name_map = json.load(f)
except Exception as e:
    print(f"Error reading associations.json: {e}")
    name_map = {}

def load_last_state(today):
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
                if data.get("date") == today:
                    return data.get("games", [])
        except Exception:
            pass
    return []

def save_current_state(games, today):
    state_data = {
        "date": today,
        "games": games
    }
    with open(STATE_FILE, "w") as f:
        json.dump(state_data, f, indent=2)

def get_today_games(rows, today):
    games = []
    for row in rows:
        cells = row.find_elements(By.TAG_NAME, "td")
        if len(cells) < 9:
            continue
        date_text = cells[1].text.strip()
        if date_text[:10] == today:
            games.append({
                "game": cells[0].text.strip(),
                "time": cells[2].text.strip(),
                "responsible": cells[3].text.strip()
            })
    return games

# Chrome options
options = webdriver.ChromeOptions()
options.add_argument("--headless")  # ⬅ обязательно
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

try:
    driver.get("https://brain.quezzle.se/")

    wait = WebDriverWait(driver, 10)

    # Login
    login_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Logga in')]")))
    login_button.click()

    username_field = wait.until(EC.visibility_of_element_located((By.NAME, "email")))
    password_field = driver.find_element(By.NAME, "password")

    username_field.send_keys("vesselovskayan@gmail.com")
    password_field.send_keys("Onyx")
    password_field.send_keys(Keys.RETURN)

    wait.until(EC.visibility_of_element_located((By.CLASS_NAME, "avatar-img")))
    print("Авторизация прошла успешно!")

    # Table
    bookings_table = wait.until(EC.visibility_of_element_located((By.CLASS_NAME, "table-responsive")))
    rows = bookings_table.find_elements(By.TAG_NAME, "tr")

    date_offset = 0 if MODE == "today" else 1
    today = (datetime.now() + timedelta(days=date_offset)).strftime("%Y-%m-%d")

    today_games = get_today_games(rows, today)
    previous_games = load_last_state(today)

    if not previous_games:
        # Первый запуск или смена дня
        message_lines = []
        for g in today_games:
            abbr = g["game"][:3]
            emoji = emoji_map.get(abbr, "")
            name = g["responsible"]
            mention = "❓" if name.strip().startswith("Ingen") else name_map.get(name, name)
            message_lines.append(f"{emoji}{abbr} | {g['time']} | {mention}")
        if message_lines:
            full_message = f"🗓️ Today's games ({today}):\n\n" + "\n".join(message_lines)
        else:
            full_message = f"😱 No games planned ({today})"
        send_telegram_message(full_message)
        print(full_message)
        save_current_state(today_games, today)
    else:
        # Сравнение состояний
        changes_detected = False
        added, removed, changed = [], [], []

        previous_keys = {(g["game"], g["time"]): g for g in previous_games}
        current_keys = {(g["game"], g["time"]): g for g in today_games}

        for key in current_keys:
            if key not in previous_keys:
                added.append(current_keys[key])
                changes_detected = True
            elif current_keys[key]["responsible"] != previous_keys[key]["responsible"]:
                changed.append((previous_keys[key], current_keys[key]))
                changes_detected = True

        for key in previous_keys:
            if key not in current_keys:
                removed.append(previous_keys[key])
                changes_detected = True

        if changes_detected:
            messages = [f"📅 Сhanges in game bookings {today}:\n"]

            sections = []

            if added:
                lines = ["➕ New booking(s):"]
                for g in added:
                    abbr = g["game"][:3]
                    emoji = emoji_map.get(abbr, "")
                    name = g["responsible"]
                    mention = "❓" if name.strip().startswith("Ingen") else name_map.get(name, name)
                    lines.append(f"{emoji}{abbr} | {g['time']} | {mention}")
                sections.append("\n".join(lines))

            if changed:
                lines = ["🕴️ Game master assigned (changed):"]
                for old, new in changed:
                    abbr = new["game"][:3]
                    emoji = emoji_map.get(abbr, "")
                    old_name = old["responsible"]
                    new_name = new["responsible"]
                    old_mention = "❓" if old_name.strip().startswith("Ingen") else name_map.get(old_name, old_name)
                    new_mention = "❓" if new_name.strip().startswith("Ingen") else name_map.get(new_name, new_name)
                    lines.append(f"{emoji}{abbr} | {new['time']} | {old_mention} → {new_mention}")
                sections.append("\n".join(lines))

            if removed:
                lines = ["❌ Game booking cancelled:"]
                for g in removed:
                    abbr = g["game"][:3]
                    emoji = emoji_map.get(abbr, "")
                    name = g["responsible"]
                    mention = "❓" if name.strip().startswith("Ingen") else name_map.get(name, name)
                    lines.append(f"{emoji}{abbr} | {g['time']} | {mention}")
                sections.append("\n".join(lines))

            messages.append("\n\n".join(sections))  # Разделитель между секциями
            full_message = "\n".join(messages)

            send_telegram_message("\n".join(messages))
            print("\n".join(messages))
            save_current_state(today_games, today)
        else:
            print("Изменений не обнаружено.")

except Exception as e:
    error_message = f"❗️Script error: {str(e)}"
    print(error_message)
    send_telegram_message(error_message)

finally:
    driver.quit()
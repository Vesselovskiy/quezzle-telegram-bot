from selenium import webdriver  # type: ignore
from selenium.webdriver.common.by import By  # type: ignore
from selenium.webdriver.common.keys import Keys  # type: ignore
from selenium.webdriver.chrome.service import Service  # type: ignore
from selenium.webdriver.support.ui import WebDriverWait  # type: ignore
from selenium.webdriver.support import expected_conditions as EC  # type: ignore
from webdriver_manager.chrome import ChromeDriverManager  # type: ignore
from datetime import datetime, timedelta
from dotenv import load_dotenv
import requests  # type: ignore
import json
import os
import sys
import subprocess

load_dotenv()

# ─── Константы и конфигурация ───────────────────────────────────────────────────
BRAIN_QUEZZLE_USERNAME=os.getenv("BRAIN_QUEZZLE_USERNAME")
BRAIN_QUEZZLE_PASSWORD=os.getenv("BRAIN_QUEZZLE_PASSWORD")

GIT_USERNAME = os.getenv("GIT_USERNAME")
GIT_TOKEN = os.getenv("GIT_TOKEN")
GIT_REPO = os.getenv("GIT_REPO")


MODE = sys.argv[1].lower() if len(sys.argv) > 1 and sys.argv[1].lower() in ["today", "tomorrow"] else "today"
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE_DIR, "last_state.json")
ASSOCIATIONS_FILE = os.path.join(BASE_DIR, "associations.json")

EMOJI_MAP = {
    "SHE": "🕵️",
    "FRO": "⚱️",
    "BNK": "💰",
    "APO": "☣️"
}

# ─── Telegram ────────────────────────────────────────────────────────────────────
def send_telegram_message(message: str):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": message})
    except Exception as e:
        print("Ошибка при отправке в Telegram:", e)

# ─── Git Commit State File ───────────────────────────────────────────────────────
# Устанавливаем новый origin с токеном
def set_authenticated_git_remote():
    remote_url = f"https://{GIT_USERNAME}:{GIT_TOKEN}@github.com/{GIT_USERNAME}/{GIT_REPO}.git"
    subprocess.run(["git", "remote", "set-url", "origin", remote_url], check=True)

def git_commit_state(today: str):
    try:
        set_authenticated_git_remote()
        subprocess.run(["git", "config", "user.name", "StateFileUpdateBot"], check=True)
        subprocess.run(["git", "config", "user.email", "statefileupdate@bot.com"], check=True)
        subprocess.run(["git", "add", STATE_FILE], check=True)
        subprocess.run(["git", "commit", "-m", f"Update state for {today}"], check=True)
        subprocess.run(["git", "push"], check=True)
        print("✅ Коммит и пуш состояния выполнен")
    except subprocess.CalledProcessError as e:
        print(f"⚠️ Ошибка Git: {e}")

# ─── Работа с состоянием ─────────────────────────────────────────────────────────
def load_name_map() -> dict:
    if not os.path.exists(ASSOCIATIONS_FILE):
        with open(ASSOCIATIONS_FILE, "w") as f:
            json.dump({}, f, indent=2)
    try:
        with open(ASSOCIATIONS_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error reading associations.json: {e}")
        return {}

def load_last_state(today: str) -> list:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
                return data.get("games", []) if data.get("date") == today else []
        except Exception:
            pass
    return []

def save_current_state(games: list, today: str):
    with open(STATE_FILE, "w") as f:
        json.dump({"date": today, "games": games}, f, indent=2)
    git_commit_state(today)

# ─── Получение данных ────────────────────────────────────────────────────────────
def get_today_games(rows, today: str) -> list:
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

# ─── Форматирование сообщений ─────────────────────────────────────────────────────
def format_mention(name: str, name_map: dict) -> str:
    return "❓" if name.strip().startswith("Ingen") else name_map.get(name, name)

def generate_message(today: str, current: list, previous: list, name_map: dict) -> str:
    if not previous:
        if not current:
            return f"😱 No games planned ({today})"
        lines = [f"{EMOJI_MAP.get(g['game'][:3], '')}{g['game'][:3]} | {g['time']} | {format_mention(g['responsible'], name_map)}" for g in current]
        return f"🗓️ Today's games ({today}):\n\n" + "\n".join(lines)

    # Compare states
    added, removed, changed = [], [], []
    old_map = {(g["game"], g["time"]): g for g in previous}
    new_map = {(g["game"], g["time"]): g for g in current}

    for key, val in new_map.items():
        if key not in old_map:
            added.append(val)
        elif val["responsible"] != old_map[key]["responsible"]:
            changed.append((old_map[key], val))

    for key, val in old_map.items():
        if key not in new_map:
            removed.append(val)

    if not (added or changed or removed):
        return ""

    sections = []

    if added:
        lines = ["➕ New booking(s):"] + [
            f"{EMOJI_MAP.get(g['game'][:3], '')}{g['game'][:3]} | {g['time']} | {format_mention(g['responsible'], name_map)}"
            for g in added
        ]
        sections.append("\n".join(lines))

    if changed:
        lines = ["🕴️ Game master assigned (changed):"] + [
            f"{EMOJI_MAP.get(n['game'][:3], '')}{n['game'][:3]} | {n['time']} | {format_mention(o['responsible'], name_map)} → {format_mention(n['responsible'], name_map)}"
            for o, n in changed
        ]
        sections.append("\n".join(lines))

    if removed:
        lines = ["❌ Game booking cancelled:"] + [
            f"{EMOJI_MAP.get(g['game'][:3], '')}{g['game'][:3]} | {g['time']} | {format_mention(g['responsible'], name_map)}"
            for g in removed
        ]
        sections.append("\n".join(lines))

    return f"📅 Сhanges in game bookings {today}:\n\n" + "\n\n".join(sections)

# ─── Основная логика ──────────────────────────────────────────────────────────────
def main():
    name_map = load_name_map()
    date_offset = 0 if MODE == "today" else 1
    today = (datetime.now() + timedelta(days=date_offset)).strftime("%Y-%m-%d")

    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

    try:
        driver.get("https://brain.quezzle.se/")
        wait = WebDriverWait(driver, 10)

        wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Logga in')]"))).click()
        wait.until(EC.visibility_of_element_located((By.NAME, "email"))).send_keys(BRAIN_QUEZZLE_USERNAME)
        driver.find_element(By.NAME, "password").send_keys(BRAIN_QUEZZLE_PASSWORD + Keys.RETURN)
        wait.until(EC.visibility_of_element_located((By.CLASS_NAME, "avatar-img")))
        print("Авторизация прошла успешно!")

        rows = wait.until(EC.visibility_of_element_located((By.CLASS_NAME, "table-responsive"))).find_elements(By.TAG_NAME, "tr")
        current_games = get_today_games(rows, today)
        previous_games = load_last_state(today)

        message = generate_message(today, current_games, previous_games, name_map)
        if message:
            send_telegram_message(message)
            print(message)
            save_current_state(current_games, today)
        else:
            print("Изменений не обнаружено.")
    except Exception as e:
        error_msg = f"❗️Script error: {e}"
        print(error_msg)
        send_telegram_message(error_msg)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
from selenium import webdriver  # type: ignore
from selenium.webdriver.common.by import By  # type: ignore
from selenium.webdriver.common.keys import Keys  # type: ignore
from selenium.webdriver.chrome.service import Service  # type: ignore
from selenium.webdriver.support.ui import WebDriverWait  # type: ignore
from selenium.webdriver.support import expected_conditions as EC  # type: ignore
from webdriver_manager.chrome import ChromeDriverManager  # type: ignore
from datetime import datetime, timedelta
from dotenv import load_dotenv
import requests  # type: ignore
import json
import os
import sys
import subprocess

load_dotenv()

# ─── Константы и конфигурация ───────────────────────────────────────────────────
BRAIN_QUEZZLE_USERNAME=os.getenv("BRAIN_QUEZZLE_USERNAME")
BRAIN_QUEZZLE_PASSWORD=os.getenv("BRAIN_QUEZZLE_PASSWORD")

GIT_USERNAME = os.getenv("GIT_USERNAME")
GIT_TOKEN = os.getenv("GIT_TOKEN")
GIT_REPO = os.getenv("GIT_REPO")


MODE = sys.argv[1].lower() if len(sys.argv) > 1 and sys.argv[1].lower() in ["today", "tomorrow"] else "today"
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE_DIR, "last_state.json")
ASSOCIATIONS_FILE = os.path.join(BASE_DIR, "associations.json")

EMOJI_MAP = {
    "SHE": "🕵️",
    "FRO": "⚱️",
    "BNK": "💰",
    "APO": "☣️"
}

# ─── Telegram ────────────────────────────────────────────────────────────────────
def send_telegram_message(message: str):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": message})
    except Exception as e:
        print("Ошибка при отправке в Telegram:", e)

# ─── Git Commit State File ───────────────────────────────────────────────────────
# Устанавливаем новый origin с токеном
def set_authenticated_git_remote():
    remote_url = f"https://{GIT_USERNAME}:{GIT_TOKEN}@github.com/{GIT_USERNAME}/{GIT_REPO}.git"
    subprocess.run(["git", "remote", "set-url", "origin", remote_url], check=True)

def git_commit_state(today: str):
    try:
        set_authenticated_git_remote()
        subprocess.run(["git", "config", "user.name", "StateFileUpdateBot"], check=True)
        subprocess.run(["git", "config", "user.email", "statefileupdate@bot.com"], check=True)
        subprocess.run(["git", "add", STATE_FILE], check=True)
        subprocess.run(["git", "commit", "-m", f"Update state for {today}"], check=True)
        subprocess.run(["git", "push"], check=True)
        print("✅ Коммит и пуш состояния выполнен")
    except subprocess.CalledProcessError as e:
        print(f"⚠️ Ошибка Git: {e}")

# ─── Работа с состоянием ─────────────────────────────────────────────────────────
def load_name_map() -> dict:
    if not os.path.exists(ASSOCIATIONS_FILE):
        with open(ASSOCIATIONS_FILE, "w") as f:
            json.dump({}, f, indent=2)
    try:
        with open(ASSOCIATIONS_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error reading associations.json: {e}")
        return {}

def load_last_state(today: str) -> list:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
                return data.get("games", []) if data.get("date") == today else []
        except Exception:
            pass
    return []

def save_current_state(games: list, today: str):
    with open(STATE_FILE, "w") as f:
        json.dump({"date": today, "games": games}, f, indent=2)
    git_commit_state(today)

# ─── Получение данных ────────────────────────────────────────────────────────────
def get_today_games(rows, today: str) -> list:
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

# ─── Форматирование сообщений ─────────────────────────────────────────────────────
def format_mention(name: str, name_map: dict) -> str:
    return "❓" if name.strip().startswith("Ingen") else name_map.get(name, name)

def generate_message(today: str, current: list, previous: list, name_map: dict) -> str:
    if not previous:
        if not current:
            return f"😱 No games planned ({today})"
        lines = [f"{EMOJI_MAP.get(g['game'][:3], '')}{g['game'][:3]} | {g['time']} | {format_mention(g['responsible'], name_map)}" for g in current]
        return f"🗓️ Today's games ({today}):\n\n" + "\n".join(lines)

    # Compare states
    added, removed, changed = [], [], []
    old_map = {(g["game"], g["time"]): g for g in previous}
    new_map = {(g["game"], g["time"]): g for g in current}

    for key, val in new_map.items():
        if key not in old_map:
            added.append(val)
        elif val["responsible"] != old_map[key]["responsible"]:
            changed.append((old_map[key], val))

    for key, val in old_map.items():
        if key not in new_map:
            removed.append(val)

    if not (added or changed or removed):
        return ""

    sections = []

    if added:
        lines = ["➕ New booking(s):"] + [
            f"{EMOJI_MAP.get(g['game'][:3], '')}{g['game'][:3]} | {g['time']} | {format_mention(g['responsible'], name_map)}"
            for g in added
        ]
        sections.append("\n".join(lines))

    if changed:
        lines = ["🕴️ Game master assigned (changed):"] + [
            f"{EMOJI_MAP.get(n['game'][:3], '')}{n['game'][:3]} | {n['time']} | {format_mention(o['responsible'], name_map)} → {format_mention(n['responsible'], name_map)}"
            for o, n in changed
        ]
        sections.append("\n".join(lines))

    if removed:
        lines = ["❌ Game booking cancelled:"] + [
            f"{EMOJI_MAP.get(g['game'][:3], '')}{g['game'][:3]} | {g['time']} | {format_mention(g['responsible'], name_map)}"
            for g in removed
        ]
        sections.append("\n".join(lines))

    return f"📅 Сhanges in game bookings {today}:\n\n" + "\n\n".join(sections)

# ─── Основная логика ──────────────────────────────────────────────────────────────
def main():
    name_map = load_name_map()
    date_offset = 0 if MODE == "today" else 1
    today = (datetime.now() + timedelta(days=date_offset)).strftime("%Y-%m-%d")

    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

    try:
        driver.get("https://brain.quezzle.se/")
        wait = WebDriverWait(driver, 10)

        wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Logga in')]"))).click()
        wait.until(EC.visibility_of_element_located((By.NAME, "email"))).send_keys(BRAIN_QUEZZLE_USERNAME)
        driver.find_element(By.NAME, "password").send_keys(BRAIN_QUEZZLE_PASSWORD + Keys.RETURN)
        wait.until(EC.visibility_of_element_located((By.CLASS_NAME, "avatar-img")))
        print("Авторизация прошла успешно!")

        rows = wait.until(EC.visibility_of_element_located((By.CLASS_NAME, "table-responsive"))).find_elements(By.TAG_NAME, "tr")
        current_games = get_today_games(rows, today)
        previous_games = load_last_state(today)

        message = generate_message(today, current_games, previous_games, name_map)
        if message:
            send_telegram_message(message)
            print(message)
            save_current_state(current_games, today)
        else:
            print("Изменений не обнаружено.")
    except Exception as e:
        error_msg = f"❗️Script error: {e}"
        print(error_msg)
        send_telegram_message(error_msg)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()

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

# ─── Константы ─────────────────────────────────────────────────────────────────
BRAIN_QUEZZLE_USERNAME = os.getenv("BRAIN_QUEZZLE_USERNAME")
BRAIN_QUEZZLE_PASSWORD = os.getenv("BRAIN_QUEZZLE_PASSWORD")
BRAIN_QUEZZLE_LINK = os.getenv("BRAIN_QUEZZLE_LINK")
GIT_USERNAME = os.getenv("GIT_USERNAME")
GIT_TOKEN = os.getenv("GIT_TOKEN")
GIT_REPO = os.getenv("GIT_REPO")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE_DIR, "last_state.json")
ASSOCIATIONS_FILE = os.path.join(BASE_DIR, "associations.json")

EMOJI_MAP = {"SHE": "🕵️", "FRO": "⚱️", "BNK": "💰", "APO": "☣️"}

# ─── Утилиты ───────────────────────────────────────────────────────────────────
def setup_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--log-level=3")
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

def login_and_get_rows(driver):
    driver.get(BRAIN_QUEZZLE_LINK)
    wait = WebDriverWait(driver, 10)
    wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Logga in')]"))).click()
    wait.until(EC.visibility_of_element_located((By.NAME, "email"))).send_keys(BRAIN_QUEZZLE_USERNAME)
    driver.find_element(By.NAME, "password").send_keys(BRAIN_QUEZZLE_PASSWORD + Keys.RETURN)
    wait.until(EC.visibility_of_element_located((By.CLASS_NAME, "avatar-img")))
    return wait.until(EC.visibility_of_element_located((By.CLASS_NAME, "table-responsive"))).find_elements(By.TAG_NAME, "tr")

def get_games_by_date(rows, target_date):
    games = []
    for row in rows:
        cells = row.find_elements(By.TAG_NAME, "td")
        if len(cells) < 9:
            continue
        if cells[1].text.strip()[:10] == target_date:
            games.append({
                "game": cells[0].text.strip(),
                "time": cells[2].text.strip(),
                "responsible": cells[3].text.strip()
            })
    return games

def load_name_map():
    if not os.path.exists(ASSOCIATIONS_FILE):
        with open(ASSOCIATIONS_FILE, "w") as f:
            json.dump({}, f, indent=2)
    try:
        with open(ASSOCIATIONS_FILE, "r") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"⚠️ Ошибка JSON в файле {ASSOCIATIONS_FILE}: {e}")
        return {}
    except Exception as e:
        print(f"⚠️ Ошибка чтения файла {ASSOCIATIONS_FILE}: {e}")
        return {}

def load_last_state(today):
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
                if data.get("date") == today:
                    return data.get("games", [])
                else:
                    return []
        except json.JSONDecodeError as e:
            print(f"⚠️ Ошибка JSON в файле {STATE_FILE}: {e}")
            return []
        except Exception as e:
            print(f"⚠️ Ошибка чтения файла {STATE_FILE}: {e}")
            return []
    return []

def save_current_state(games, today):
    with open(STATE_FILE, "w") as f:
        json.dump({"date": today, "games": games}, f, indent=2)
    git_commit_state(today)

def git_commit_state(today):
    try:
        subprocess.run(["git", "remote", "set-url", "origin", f"https://{GIT_USERNAME}:{GIT_TOKEN}@github.com/{GIT_USERNAME}/{GIT_REPO}.git"], check=True)
        subprocess.run(["git", "config", "user.name", "StateFileUpdateBot"], check=True)
        subprocess.run(["git", "config", "user.email", "statefileupdate@bot.com"], check=True)
        subprocess.run(["git", "add", STATE_FILE], check=True)
        subprocess.run(["git", "commit", "-m", f"Update state for {today}"], check=True)
        subprocess.run(["git", "push"], check=True)
        print("✅ Коммит и пуш состояния выполнен")
    except subprocess.CalledProcessError as e:
        print(f"⚠️ Ошибка Git: {e}")

def format_mention(name, name_map):
    return "❓" if name.strip().startswith("Ingen") else name_map.get(name, name)

def generate_message(today, current, previous, name_map):
    if not previous:
        if not current:
            return f"😱 No games planned ({today})"
        return "🗓️ Today's games ({}):\n\n".format(today) + "\n".join([
            f"{EMOJI_MAP.get(g['game'][:3], '')}{g['game'][:3]} | {g['time']} | {format_mention(g['responsible'], name_map)}"
            for g in current
        ])

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
        sections.append("\n".join(["➕ New booking(s):"] + [
            f"{EMOJI_MAP.get(g['game'][:3], '')}{g['game'][:3]} | {g['time']} | {format_mention(g['responsible'], name_map)}"
            for g in added
        ]))
    if changed:
        sections.append("\n".join(["🕴️ Game master assigned (changed):"] + [
            f"{EMOJI_MAP.get(n['game'][:3], '')}{n['game'][:3]} | {n['time']} | {format_mention(o['responsible'], name_map)} → {format_mention(n['responsible'], name_map)}"
            for o, n in changed
        ]))
    if removed:
        sections.append("\n".join(["❌ Game booking cancelled:"] + [
            f"{EMOJI_MAP.get(g['game'][:3], '')}{g['game'][:3]} | {g['time']} | {format_mention(g['responsible'], name_map)}"
            for g in removed
        ]))
    return f"📅 Сhanges in game bookings {today}:\n\n" + "\n\n".join(sections)

def get_schedule_message(mode, name_map):
    date_offset = 0 if mode == "today" else 1
    target_date = (datetime.now() + timedelta(days=date_offset)).strftime("%Y-%m-%d")
    print ("Target date: {target_date}")
    driver = setup_driver()
    try:
        rows = login_and_get_rows(driver)
        games = get_games_by_date(rows, target_date)
        if mode == "tomorrow":
            if not games:
                return f"😱 No games planned for tomorrow ({target_date})"
            return f"👀 Tomorrow's games ({target_date}):\n\n" + "\n".join([
                f"{EMOJI_MAP.get(g['game'][:3], '')}{g['game'][:3]} | {g['time']} | {format_mention(g['responsible'], name_map)}"
                for g in games
            ])
        # Today mode
        previous = load_last_state(target_date)
        return generate_message(target_date, games, previous, name_map) or "No changes detected for today's schedule."
    except Exception as e:
        return f"❗ Ошибка при получении расписания: {e}"
    finally:
        driver.quit()

def main():
    today = datetime.now().strftime("%Y-%m-%d")
    name_map = load_name_map()
    driver = setup_driver()
    try:
        rows = login_and_get_rows(driver)
        current_games = get_games_by_date(rows, today)
        previous_games = load_last_state(today)
        message = generate_message(today, current_games, previous_games, name_map)
        if message:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                data={"chat_id": CHAT_ID, "text": message}
            )
            save_current_state(current_games, today)
        else:
            print("Нет изменений в расписании на сегодня.")
    except Exception as e:
        print(f"Ошибка в main: {e}", file=sys.stderr)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()

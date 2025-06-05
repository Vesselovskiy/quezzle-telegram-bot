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
os.environ["ABSL_LOG_LEVEL"] = "3"
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
CHAT_IDS_FILE = os.path.join(BASE_DIR, "telegram_chat_ids.json")

EMOJI_MAP = {"SHE": "🔍", "FRO": "🐪", "BNK": "💲", "APO": "💀"}

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
        if len(cells) < 10:
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

def load_chat_ids():
    if os.path.exists(CHAT_IDS_FILE):
        try:
            with open(CHAT_IDS_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ Ошибка чтения {CHAT_IDS_FILE}: {e}")
            return []
    return []

def send_telegram_message(text):
    chat_ids = load_chat_ids()
    if not chat_ids:
        print("⚠️ Нет chat_id для рассылки.")
        return
    for chat_id in chat_ids:
        print(f"Отправка сообщения в Telegram chat_id={chat_id}")
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={"chat_id": chat_id, "text": text}
        )

def load_last_state(today):
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
                if data.get("date") == today:
                    return data.get("games", []), True  # уже был запуск
                else:
                    return [], False
        except json.JSONDecodeError as e:
            print(f"⚠️ Ошибка JSON в файле {STATE_FILE}: {e}")
            return [], False
        except Exception as e:
            print(f"⚠️ Ошибка чтения файла {STATE_FILE}: {e}")
            return [], False
    return [], False

def save_current_state(games, today):
    print (f"Сохранение состояния для {today} в файл {STATE_FILE}")
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
    for username, real_name in name_map.items():
        if real_name == name:
            return f"@{username}"
    return "❓" if name.strip().startswith("Ingen") else name

def generate_message(today, current, previous, name_map, state_exists):
    # Если игр нет
    if not current:
        if not state_exists:
            # Первый запуск — сообщаем, что игр нет
            print(f"Нет игр на {today}, но это первый запуск, надо отправить сообщение")
            return f"😱 No games planned for today ({today})"
        else:
            # Повторный запуск — ничего не отправляем
            print(f"Нет игр на {today}, но это повторный запуск, сообщение надо отправить")
            return ""

    # Если ранее не было состояния (первый запуск), но игры есть — отправляем все
    if not previous:
        print(f"Первый запуск, надо отправить сообщение со всеми играми за сегодня ({today})")
        return "🗓️ Today's games ({}):\n\n".format(today) + "\n".join([
            f"{EMOJI_MAP.get(g['game'][:3], '')}{g['game'][:3]} | {g['time']} | {format_mention(g['responsible'], name_map)}"
            for g in current
        ])

    # Сравниваем текущие и предыдущие
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

    # Нет изменений — ничего не отправляем
    if not (added or changed or removed):
        print(f"Нет изменений в расписании на {today}, сообщение нет нужды отправлять")
        return ""

    # Формируем сообщение об изменениях
    sections = []
    print(f"Изменения в расписании на {today}, отправим сообщение")
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

    return f"🆕 Сhanges in game bookings {today}:\n\n" + "\n\n".join(sections)


def main(mode="today", no_save=False, no_send=False):
    # Определяем целевую дату
    if mode == "today":
        target_date = datetime.now().strftime("%Y-%m-%d")
        target_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    elif mode == "tomorrow":
        target_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    elif mode.startswith("date "):
        try:
            target_date = mode.split(" ", 1)[1]
            # Проверяем формат даты
            datetime.strptime(target_date, "%Y-%m-%d")
        except (IndexError, ValueError):
            print("❗ Неверный формат даты. Должно быть: date YYYY-MM-DD")
            return
    else:
        print("❗ Неизвестный режим. Можно: today, tomorrow или date YYYY-MM-DD")
        return

    name_map = load_name_map()

    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--log-level=3")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

    try:
        driver.get(BRAIN_QUEZZLE_LINK)
        wait = WebDriverWait(driver, 10)
        print(f"WebDriver инициализирован")
        wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Logga in')]"))).click()
        wait.until(EC.visibility_of_element_located((By.NAME, "email"))).send_keys(BRAIN_QUEZZLE_USERNAME)
        driver.find_element(By.NAME, "password").send_keys(BRAIN_QUEZZLE_PASSWORD + Keys.RETURN)
        wait.until(EC.visibility_of_element_located((By.CLASS_NAME, "avatar-img")))
        print(f"Авторизация успешна")
        rows = wait.until(EC.visibility_of_element_located((By.CLASS_NAME, "table-responsive"))).find_elements(By.TAG_NAME, "tr")
        print(f"Бронирования игр загружены из таблицы (всего {len(rows)})")
        current_games = get_games_by_date(rows, target_date)
        print(f"Брониворвания отфильтрованы для даты: {target_date} (всего {len(current_games)})")

        if mode == "tomorrow" or mode.startswith("date ") or ((mode == "today") and no_save):
            message_lines = []
            for g in current_games:
                abbr = g["game"][:3]
                emoji = EMOJI_MAP.get(abbr, "")
                name = g["responsible"]
                mention = format_mention(name, name_map)
                message_lines.append(f"{emoji}{abbr} | {g['time']} | {mention}")
                if mode == "tomorrow":
                    msg_date = "tomorrow "
                elif mode == "today":
                    msg_date = "today "
                else:
                    msg_date = ""
            if message_lines:
                full_message = f"🗓️ Games for {msg_date}{target_date}:\n\n" + "\n".join(message_lines)
            else:
                full_message = f"😱 No games planned for {msg_date}{target_date}"
            print(full_message)
            if not no_send:
                send_telegram_message(full_message)
                return
            else:
                return (full_message)

        # mode == "today"
        previous_games, state_exists = load_last_state(target_date)
        message = generate_message(target_date, current_games, previous_games, name_map, state_exists)

        if message:
            print(message)
            if not no_send:
                send_telegram_message(message)
            else:
                return (full_message)
            if not no_save:
                print(f"Сохранение текущего состояния в файл {STATE_FILE}")
                # Сохраняем текущее состояние и пушим в git
                save_current_state(current_games, target_date)
        else:
            print(f"Нет изменений в расписании на сегодня ({target_date})")

    except Exception as e:
        print(f"❗ Ошибка в main: {e}", file=sys.stderr)

    finally:
        driver.quit()


if __name__ == "__main__":
    import sys
    mode = "today"
    no_save = False
    no_send = False

    if len(sys.argv) > 1:
        mode = sys.argv[1]
    if len(sys.argv) > 2 and sys.argv[2] == "--no-save":
        no_save = True
    if len(sys.argv) > 3 and sys.argv[3] == "--no-send":
        no_send = True

    main(mode, no_save, no_send)
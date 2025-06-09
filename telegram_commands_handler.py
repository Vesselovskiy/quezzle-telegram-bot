import os
import json
import requests
import subprocess
from io import StringIO
import sys
from typing import List, Dict, Any, Optional
from quezzle_schedule import main as quezzle_main
from dotenv import load_dotenv
os.environ["ABSL_LOG_LEVEL"] = "3"
load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN")
GIT_USERNAME = os.getenv("GIT_USERNAME")
GIT_TOKEN = os.getenv("GIT_TOKEN")
GIT_REPO = os.getenv("GIT_REPO")

ASSOCIATIONS_FILE = "associations.json"
OFFSET_FILE = "last_update_id.txt"
CHAT_IDS_FILE = "telegram_chat_ids.json"

# ─── Git Commit ───────────────────────────────────────────────────────────────
def set_authenticated_git_remote() -> None:
    remote_url = f"https://{GIT_USERNAME}:{GIT_TOKEN}@github.com/{GIT_USERNAME}/{GIT_REPO}.git"
    subprocess.run(["git", "remote", "set-url", "origin", remote_url], check=True)

def git_commit_files(files: List[str], message: str) -> None:
    try:
        set_authenticated_git_remote()
        subprocess.run(["git", "config", "user.name", "TelegramBot"], check=True)
        subprocess.run(["git", "config", "user.email", "telegram@bot.com"], check=True)
        subprocess.run(["git", "add"] + files, check=True)
        subprocess.run(["git", "commit", "-m", message], check=True)
        subprocess.run(["git", "pull", "--rebase"], check=True) 
        subprocess.run(["git", "push"], check=True)
        print("✅ Изменения (телеграм команды) закоммичены и запушены")
    except subprocess.CalledProcessError as e:
        print(f"⚠️ Git ошибка: {e}")

# ─── Работа с ассоциациями ────────────────────────────────────────────────────
def load_json_file(path: str, default: Any) -> Any:
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception:
            return default
    return default

def save_json_file(path: str, data: Any) -> None:
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def load_associations() -> Dict[str, str]:
    return load_json_file(ASSOCIATIONS_FILE, {})

def save_associations(data: Dict[str, str]) -> None:
    save_json_file(ASSOCIATIONS_FILE, data)

# ─── Работа с offset ──────────────────────────────────────────────────────────
def load_offset() -> int:
    if os.path.exists(OFFSET_FILE):
        with open(OFFSET_FILE, "r") as f:
            content = f.read().strip()
            if content.isdigit():
                return int(content)
    return 0

def save_offset(offset: int) -> None:
    with open(OFFSET_FILE, "w") as f:
        f.write(str(offset))

# ─── Работа с chat_ids ────────────────────────────────────────────────────────
def load_chat_ids() -> List[int]:
    return load_json_file(CHAT_IDS_FILE, [])

def save_chat_ids(chat_ids: List[int]) -> None:
    save_json_file(CHAT_IDS_FILE, chat_ids)

def add_chat_id(chat_id: int) -> bool:
    chat_ids = set(load_chat_ids())
    if chat_id not in chat_ids:
        chat_ids.add(chat_id)
        save_chat_ids(list(chat_ids))
        print(f"Добавлен новый chat_id: {chat_id}")
        return True
    return False

# ─── Отправка сообщения в Telegram ─────────────────────────────────────────────
def send_message(chat_id: int, text: str, parse_mode: str = None) -> None:
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = {"chat_id": chat_id, "text": text}
    if parse_mode:
        data["parse_mode"] = parse_mode
    requests.post(url, data=data)

# ─── Вызов скрипта расписания с аргументом ─────────────────────────────────────
def get_schedule_message(mode: str, ) -> str:
    try:
        old_stdout = sys.stdout
        sys.stdout = mystdout = StringIO()
        mesage = quezzle_main(mode, no_save=True, no_send=True)
        sys.stdout = old_stdout
        output = mystdout.getvalue().strip()
        print(output)
        return mesage if (output or mesage)  else "🤷 No schedule info found."
    except Exception as e:
        return f"❗️ Failed to get schedule: {e}"

# ─── Основная логика ──────────────────────────────────────────────────────────
def main() -> None:
    url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"
    params = {"offset": load_offset() + 1}
    res = requests.get(url, params=params)
    updates = res.json().get("result", [])

    if not updates:
        print ("Команд не было... пронесло...")
        return

    associations = load_associations()
    max_update_id = 0
    changed = False
    chat_ids_changed = False

    for update in updates:
        max_update_id = max(max_update_id, update["update_id"])
        message = update.get("message")
        if not message:
            continue

        text = message.get("text", "").strip()
        username = message["from"].get("username")
        if not username or not text:
            continue

        chat_id = message["chat"]["id"]
        # Автоматически добавляем chat_id в рассылку
        if add_chat_id(chat_id):
            chat_ids_changed = True

        if text in ("/start", "/help"):
            welcome_message = (
                "👋 Hello! I'm Quzzle Schedule Bot that Sergey Veselovsky made for his beloved wife.\n\n"
                "Use:\n"
                "/today to get today's schedule,\n"
                "/tomorrow to see tomorrow's schedule,\n"
                "/date YYYY-MM-DD to get schedule for any date,\n"
                "/iam to set your name (e.g. /iam John D),\n"
                "/whoami to see your current name,\n"
                "/forgetme to remove your association."
            )
            send_message(chat_id, welcome_message)

        elif text.startswith("/iam "):
            claimed_name = text[5:].strip()
            associations[username] = claimed_name
            changed = True
            print(f"📝 Связал @{username} → {claimed_name}")
            send_message(chat_id, f"✅ Got it, {claimed_name}! I will now mention you by this name in schedules.")

        elif text == "/whoami":
            if username in associations:
                real_name = associations[username]
                send_message(chat_id, f"🪪 You are currently identified as *{real_name}*.", parse_mode="Markdown")
            else:
                send_message(chat_id, "🤷 I don't know who you are yet. Use `/iam Your Name` to introduce yourself.")

        elif text == "/forgetme":
            if username in associations:
                del associations[username]
                changed = True
                print(f"🗑️ Удалена ассоциация @{username}")
                send_message(chat_id, "❌ Your association has been removed.")
            else:
                send_message(chat_id, "🤷 I don’t have any record of you.")

        elif text == "/today":
            print(f"Запрошено сегодняшнее расписание @{username}")
            schedule_message = get_schedule_message("today")
            send_message(chat_id, schedule_message)

        elif text == "/tomorrow":
            print(f"Запрошено завтрашнее расписание @{username}")
            schedule_message = get_schedule_message("tomorrow")
            send_message(chat_id, schedule_message)

        elif text.startswith("/date "):
            print(f"Запрошено расписание на определенную дату @{username}")
            schedule_message = get_schedule_message(text[1:])
            send_message(chat_id, schedule_message)

        else:
            send_message(chat_id, "❓ Unknown command. Try /today, /tomorrow, /date YYYY-MM-DD, or /iam YourName (e.g. /iam John D)")

    if changed or chat_ids_changed:
        files = [ASSOCIATIONS_FILE, OFFSET_FILE]
        if chat_ids_changed:
            files.append(CHAT_IDS_FILE)
        save_associations(associations)
        save_offset(max_update_id)
        git_commit_files(files, "Update associations, chat_ids and offset")
    else:
        save_offset(max_update_id)
        git_commit_files([OFFSET_FILE], "Update offset")

if __name__ == "__main__":
    main()
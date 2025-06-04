import os
import json
import requests
import subprocess
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GIT_USERNAME = os.getenv("GIT_USERNAME")
GIT_TOKEN = os.getenv("GIT_TOKEN")
GIT_REPO = os.getenv("GIT_REPO")

ASSOCIATIONS_FILE = "associations.json"
OFFSET_FILE = "last_update_id.txt"

# ─── Git Commit ───────────────────────────────────────────────────────────────
def set_authenticated_git_remote():
    remote_url = f"https://{GIT_USERNAME}:{GIT_TOKEN}@github.com/{GIT_USERNAME}/{GIT_REPO}.git"
    subprocess.run(["git", "remote", "set-url", "origin", remote_url], check=True)

def git_commit_files(files: list, message: str):
    try:
        set_authenticated_git_remote()
        subprocess.run(["git", "config", "user.name", "TelegramBot"], check=True)
        subprocess.run(["git", "config", "user.email", "telegram@bot.com"], check=True)
        subprocess.run(["git", "add"] + files, check=True)
        subprocess.run(["git", "commit", "-m", message], check=True)
        subprocess.run(["git", "push"], check=True)
        print("✅ Изменения закоммичены и запушены")
    except subprocess.CalledProcessError as e:
        print(f"⚠️ Git ошибка: {e}")

# ─── Работа с ассоциациями ────────────────────────────────────────────────────
def load_associations():
    if os.path.exists(ASSOCIATIONS_FILE):
        with open(ASSOCIATIONS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_associations(data):
    with open(ASSOCIATIONS_FILE, "w") as f:
        json.dump(data, f, indent=2)

# ─── Работа с offset ──────────────────────────────────────────────────────────
def load_offset():
    if os.path.exists(OFFSET_FILE):
        with open(OFFSET_FILE, "r") as f:
            content = f.read().strip()
            if content.isdigit():
                return int(content)
            else:
                return 0
    return 0

def save_offset(offset):
    with open(OFFSET_FILE, "w") as f:
        f.write(str(offset))

# ─── Отправка сообщения в Telegram ─────────────────────────────────────────────
def send_message(chat_id, text, parse_mode=None):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = {"chat_id": chat_id, "text": text}
    if parse_mode:
        data["parse_mode"] = parse_mode
    requests.post(url, data=data)

# ─── Вызов скрипта расписания с аргументом ──────────────────────────────────────
def get_schedule_message(mode):
    import sys
    import subprocess

    python_exe = sys.executable
    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "quezzle_schedule.py")

    try:
        result = subprocess.run(
            [python_exe, script_path, mode],
            capture_output=True,
            text=True,
            timeout=60
        )
        if result.returncode == 0:
            output_lines = result.stdout.strip().splitlines()
            for line in reversed(output_lines):
                if line.strip():
                    return line.strip()
            return "🤷 No schedule info found."
        else:
            return f"❗️ Schedule script error:\n{result.stderr}"
    except Exception as e:
        return f"❗️ Failed to get schedule: {e}"

# ─── Основная логика ──────────────────────────────────────────────────────────
def main():
    url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"
    params = {"offset": load_offset() + 1}
    res = requests.get(url, params=params)
    updates = res.json().get("result", [])

    if not updates:
        return

    associations = load_associations()
    max_update_id = 0
    changed = False

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

        if (text == "/start") or (text == "/help"):
            welcome_message = (
            "👋 Hello! I'm Quzzle Schedule Bot that Sergey Veselovsky made for his beloved wife.\n \n"
            "Use \n"
            "/today to get today's schedule, \n"
            "/tomorrow to see tomorrow's schedule, and \n"
            "/iam to set your name (e.g. /iam John D), \n"
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

        else:
            send_message(chat_id, "❓ Unknown command. Try /today or /tomorrow or /iam YourName (e.g. /iam John D)")

    if changed:
        save_associations(associations)
        save_offset(max_update_id)
        git_commit_files([ASSOCIATIONS_FILE, OFFSET_FILE], "Update associations and offset")
    else:
        save_offset(max_update_id)

if __name__ == "__main__":
    main()

import os
import json
import requests
from dotenv import load_dotenv
load_dotenv()

# Укажи свой токен и чат ID
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN") 
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE_DIR, "last_state.json")

def download_last_state(today: str):
    """Скачивает last_state.json из Telegram и возвращает список игр (если дата совпадает)"""
    try:
        updates_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
        resp = requests.get(updates_url).json()
        for result in reversed(resp.get("result", [])):
            doc = result.get("message", {}).get("document")
            if doc and doc.get("file_name") == "last_state.json":
                file_id = doc["file_id"]
                file_info = requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getFile?file_id={file_id}").json()
                file_path = file_info["result"]["file_path"]
                file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
                content = requests.get(file_url).content
                with open(STATE_FILE, "wb") as f:
                    f.write(content)
                print("✅ Загружен last_state.json из Telegram")
                break
    except Exception as e:
        print(f"⚠️ Не удалось загрузить файл: {e}")

    # Чтение состояния после загрузки
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
                if data.get("date") == today:
                    return data.get("games", [])
        except Exception:
            pass
    return []

def save_state(games: list, today: str):
    """Сохраняет текущее состояние в JSON и отправляет в Telegram"""
    try:
        with open(STATE_FILE, "w") as f:
            json.dump({"date": today, "games": games}, f, indent=2)

        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"
        with open(STATE_FILE, "rb") as f:
            files = {"document": f}
            data = {"chat_id": CHAT_ID}
            requests.post(url, files=files, data=data)
        print("✅ Состояние отправлено в Telegram")
    except Exception as e:
        print(f"⚠️ Не удалось сохранить/отправить состояние: {e}")

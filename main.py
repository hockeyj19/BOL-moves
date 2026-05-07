import os
import time
import json
import datetime
import requests
from bs4 import BeautifulSoup

# ========================= CONFIG =========================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
URL = "https://www.betonline.ag/sportsbook/martial-arts/mma"
DATA_FILE = "/tmp/ufc_odds_history.json"
POLL_INTERVAL_SECONDS = 600   # 10 minutes
MIN_MOVEMENT_POINTS = 10
# ========================================================

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    raise ValueError("❌ Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID environment variables!")

def parse_american_odds(odds_str):
    if not odds_str:
        return None
    cleaned = odds_str.strip()
    if cleaned.startswith(('+', '-')) and cleaned[1:].isdigit():
        return int(cleaned)
    return None

def is_ufc_fight(row_text):
    return "UFC" in row_text.upper()

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

def scrape_ufc_moneyline():
    print(f"🌐 Scraping at {datetime.datetime.now().strftime('%H:%M:%S')}")
    try:
        r = requests.get(URL, headers=headers, timeout=30)
        r.raise_for_status()
    except Exception as e:
        print("Request failed:", e)
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    fights = []

    rows = soup.select("div, tr, li, section")

    for row in rows:
        try:
            row_text = row.get_text()
            if not is_ufc_fight(row_text):
                continue

            names = [t.get_text(strip=True) for t in row.select("span, div, a") if len(t.get_text(strip=True)) > 4]
            if len(names) < 2:
                continue
            fighter1, fighter2 = names[0], names[1]

            odds = [o.get_text(strip=True) for o in row.select("span, button, div") 
                    if o.get_text(strip=True).startswith(('+', '-'))]

            if len(odds) >= 2:
                fight_key = f"{fighter1} vs {fighter2}"
                fights.append({
                    "fight": fight_key,
                    "fighter1": fighter1,
                    "fighter1_odds": odds[0],
                    "fighter2": fighter2,
                    "fighter2_odds": odds[1],
                    "timestamp": datetime.datetime.now().isoformat()
                })
        except:
            continue

    print(f"✅ Scraped {len(fights)} potential UFC fights")
    return fights

# ====================== Rest of the code ======================
def load_history():
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_history(current_fights):
    with open(DATA_FILE, "w") as f:
        json.dump({f["fight"]: f for f in current_fights}, f, indent=2)

def detect_movements(old_data, new_fights):
    messages = []
    for fight in new_fights:
        key = fight["fight"]
        if key in old_data:
            old = old_data[key]
            for fk in ["fighter1", "fighter2"]:
                old_odds = old.get(f"{fk}_odds")
                new_odds = fight.get(f"{fk}_odds")
                if old_odds != new_odds:
                    old_val = parse_american_odds(old_odds)
                    new_val = parse_american_odds(new_odds)
                    if old_val is not None and new_val is not None:
                        diff = abs(new_val - old_val)
                        if diff >= MIN_MOVEMENT_POINTS:
                            direction = '↑' if new_val > old_val else '↓'
                            msg = f"🔄 **{key}**\n{fight[fk]} odds moved: {old_odds} → **{new_odds}** ({direction}{diff} pts)"
                            messages.append(msg)
    return messages

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
        print("📨 Telegram sent")
    except Exception as e:
        print("Telegram error:", e)

if __name__ == "__main__":
    print("🚀 UFC BetOnline Monitor started (LIGHT version - requests only)!")
    while True:
        current_fights = scrape_ufc_moneyline()
        if current_fights:
            old_data = load_history()
            movements = detect_movements(old_data, current_fights)
            for msg in movements:
                print(msg)
                send_telegram(msg)
            save_history(current_fights)
        else:
            print("⚠️ No fights found this cycle")

        print(f"⏳ Sleeping {POLL_INTERVAL_SECONDS//60} minutes...")
        time.sleep(POLL_INTERVAL_SECONDS)

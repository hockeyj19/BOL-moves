import os
import time
import json
import datetime
import requests
from bs4 import BeautifulSoup
import re

print("🚀 UFC BetOnline Monitor started (LIGHT version - STRONG PARSER)")

# ========================= CONFIG =========================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
URL = "https://www.betonline.ag/sportsbook/martial-arts/mma"
DATA_FILE = "/tmp/ufc_odds_history.json"
POLL_INTERVAL_SECONDS = 600
MIN_MOVEMENT_POINTS = 10
# ========================================================

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    print("❌ Missing Telegram credentials!")
    raise ValueError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

def scrape_ufc_moneyline():
    print(f"🌐 Scraping at {datetime.datetime.now().strftime('%H:%M:%S')}")
    try:
        r = requests.get(URL, headers=headers, timeout=20)
        r.raise_for_status()
        print(f"✅ Page loaded ({len(r.text):,} characters)")
    except Exception as e:
        print(f"❌ Request failed: {e}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    fights = []

    odds_pattern = re.compile(r'([+-]\d{2,4})')

    # Look for any text block containing "UFC" and at least 2 odds
    for block in soup.find_all(string=lambda text: text and "UFC" in text.upper()):
        try:
            block_text = str(block).strip()
            odds_in_block = odds_pattern.findall(block_text)
            if len(odds_in_block) >= 2:
                # Extract fighter names (long sequences of letters, spaces, apostrophes)
                names = re.findall(r'([A-Za-z][A-Za-z\s\.\'-]{5,40})', block_text)
                if len(names) >= 2:
                    fighter1 = names[0].strip()
                    fighter2 = names[1].strip()
                    fight_key = f"{fighter1} vs {fighter2}"
                    fights.append({
                        "fight": fight_key,
                        "fighter1": fighter1,
                        "fighter1_odds": odds_in_block[0],
                        "fighter2": fighter2,
                        "fighter2_odds": odds_in_block[1],
                        "timestamp": datetime.datetime.now().isoformat()
                    })
        except:
            continue

    print(f"✅ Scraped {len(fights)} potential UFC fights")
    if fights:
        print("✅ First fight detected:", fights[0]["fight"], fights[0]["fighter1_odds"], fights[0]["fighter2_odds"])
    else:
        print("🔍 Still no fights - page structure may have changed")

    return fights

# ====================== Rest of code ======================
def load_history():
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_history(current_fights):
    with open(DATA_FILE, "w") as f:
        json.dump({f["fight"]: f for f in current_fights}, f, indent=2)

def parse_american_odds(odds_str):
    if not odds_str:
        return None
    cleaned = str(odds_str).strip()
    if cleaned.startswith(('+', '-')) and cleaned[1:].isdigit():
        return int(cleaned)
    return None

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
        time.sleep(POLL_INTERVAL_SECONDS)                send_telegram(msg)
            save_history(current_fights)
        else:
            print("⚠️ No fights found this cycle")

        print(f"⏳ Sleeping {POLL_INTERVAL_SECONDS//60} minutes...")
        time.sleep(POLL_INTERVAL_SECONDS)

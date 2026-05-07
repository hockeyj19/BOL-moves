import os
import time
import json
import datetime
import requests
from bs4 import BeautifulSoup
import re

print("🚀 UFC BetOnline Monitor started (LIGHT version)")

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
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
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

    # Improved detection: look for odds first
    odds_pattern = re.compile(r'([+-]\d{2,4})')
    all_odds = odds_pattern.findall(r.text)

    print(f"📊 Found {len(all_odds)} potential odds numbers on the page")

    # Try to find fights with broader logic
    rows = soup.find_all(string=lambda text: text and "UFC" in text.upper())
    print(f"📊 Found {len(rows)} text blocks containing 'UFC'")

    # Fallback broad search
    rows = soup.select("div, section, tr, li, span")

    for row in rows:
        try:
            row_text = row.get_text(strip=True)
            if not row_text or "UFC" not in row_text.upper():
                continue

            # Look for American odds in this row
            odds_in_row = odds_pattern.findall(row_text)
            if len(odds_in_row) >= 2:
                # Try to extract fighter names
                names = re.findall(r'([A-Za-z\s\.-]{4,30})', row_text)
                if len(names) >= 2:
                    fighter1, fighter2 = names[0].strip(), names[1].strip()
                    fight_key = f"{fighter1} vs {fighter2}"
                    fights.append({
                        "fight": fight_key,
                        "fighter1": fighter1,
                        "fighter1_odds": odds_in_row[0],
                        "fighter2": fighter2,
                        "fighter2_odds": odds_in_row[1],
                        "timestamp": datetime.datetime.now().isoformat()
                    })
        except:
            continue

    print(f"✅ Scraped {len(fights)} potential UFC fights")
    if len(fights) == 0:
        print("🔍 DEBUG: No fights found - page may be JS-heavy or structure changed")

    return fights

# ====================== Rest of the code (same as before) ======================
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

def parse_american_odds(odds_str):
    if not odds_str:
        return None
    cleaned = str(odds_str).strip()
    if cleaned.startswith(('+', '-')) and cleaned[1:].isdigit():
        return int(cleaned)
    return None

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
        time.sleep(POLL_INTERVAL_SECONDS)

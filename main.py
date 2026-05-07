import os
import time
import json
import datetime
from playwright.sync_api import sync_playwright
import requests
from bs4 import BeautifulSoup

print("🚀 UFC BetOnline Monitor started (Playwright version)")

# ========================= CONFIG =========================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
URL = "https://www.betonline.ag/sportsbook/martial-arts/mma"
DATA_FILE = "/tmp/ufc_odds_history.json"
POLL_INTERVAL_SECONDS = 600
MIN_MOVEMENT_POINTS = 10
# ========================================================

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

def scrape_ufc_moneyline():
    print(f"🌐 Scraping at {datetime.datetime.now().strftime('%H:%M:%S')}")
    fights = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_extra_http_headers(headers)
        page.goto(URL, wait_until="networkidle", timeout=60000)
        time.sleep(8)  # let JS load fights

        html = page.content()
        soup = BeautifulSoup(html, "html.parser")
        browser.close()

        rows = soup.select("div, section, tr, li")
        for row in rows:
            try:
                row_text = row.get_text(strip=True)
                if "UFC" not in row_text.upper():
                    continue

                # Extract fighter names and odds
                names = [t.strip() for t in row_text.split() if len(t) > 4 and t[0].isalpha()]
                odds = [o for o in row_text.split() if o.startswith(('+', '-')) and o[1:].isdigit()]

                if len(names) >= 2 and len(odds) >= 2:
                    fighter1, fighter2 = names[0], names[1]
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
        time.sleep(POLL_INTERVAL_SECONDS)

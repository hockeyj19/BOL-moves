import os
import time
import json
import datetime
from playwright.sync_api import sync_playwright
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
    if not odds_str: return None
    cleaned = odds_str.strip()
    if cleaned.startswith(('+', '-')) and cleaned[1:].isdigit():
        return int(cleaned)
    return None

def is_ufc_fight(text):
    upper = text.upper()
    if "UFC" not in upper: return False
    bad = ["PFL","BELLATOR","ONE","RIZIN","INVICTA","LFA","CAGE WARRIORS","KSW","BKFC","BJJ","ACA","TITAN"]
    return not any(x in upper for x in bad)

def get_playwright_page():
    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    page = context.new_page()
    return playwright, browser, context, page

def scrape_ufc_moneyline(page):
    print(f"🌐 Scraping at {datetime.datetime.now().strftime('%H:%M:%S')}")
    page.goto(URL, wait_until="networkidle", timeout=60000)
    time.sleep(12)   # give it time to fully load

    soup = BeautifulSoup(page.content(), "html.parser")
    fights = []

    # Very broad search for any row that might contain fights
    rows = soup.select("div, tr, li, section")

    for row in rows:
        try:
            text = row.get_text()
            if not is_ufc_fight(text): continue

            # Try to extract fighter names
            candidates = row.select("span, div, a")
            names = [n.get_text(strip=True) for n in candidates if len(n.get_text(strip=True)) > 5][:2]
            if len(names) < 2: continue

            fighter1, fighter2 = names[0], names[1]

            # Extract odds
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

    print(f"✅ Found {len(fights)} potential UFC fights")
    return fights

# ==================== Rest of the code ====================
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
                    diff = abs(parse_american_odds(new_odds or 0) - parse_american_odds(old_odds or 0))
                    if diff >= MIN_MOVEMENT_POINTS and diff < 500:   # prevent crazy numbers
                        direction = '↑' if parse_american_odds(new_odds) > parse_american_odds(old_odds) else '↓'
                        msg = f"🔄 **{key}**\n{fight[fk]} odds moved: {old_odds} → **{new_odds}** ({direction}{diff} pts)"
                        messages.append(msg)
    return messages

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
        print("📨 Telegram sent")
    except:
        print("Telegram failed")

if __name__ == "__main__":
    print("🚀 UFC BetOnline Monitor started!")
    pw, browser, context, page = get_playwright_page()

    try:
        while True:
            current_fights = scrape_ufc_moneyline(page)
            if current_fights:
                old_data = load_history()
                movements = detect_movements(old_data, current_fights)
                for msg in movements:
                    print(msg)
                    send_telegram(msg)
                save_history(current_fights)
            else:
                print("⚠️ No fights found this cycle - page may still be loading or changed")

            print(f"⏳ Sleeping {POLL_INTERVAL_SECONDS//60} minutes...")
            time.sleep(POLL_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        print("🛑 Stopped")
    finally:
        page.close()
        context.close()
        browser.close()
        pw.stop()

import os
import time
import json
import datetime
from playwright.sync_api import sync_playwright
import requests
from bs4 import BeautifulSoup
from playwright_stealth import stealth_sync

# ========================= CONFIG =========================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
URL = "https://www.betonline.ag/sportsbook/martial-arts/mma"
DATA_FILE = "/tmp/ufc_odds_history.json"
POLL_INTERVAL_SECONDS = 300
MIN_MOVEMENT_POINTS = 10

IGNORED_PROMOTIONS = [
    "PFL", "BELLATOR", "ONE CHAMPIONSHIP", "ONE FC", "RIZIN",
    "INVICTA", "LFA", "CAGE WARRIORS", "KSW", "BKFC",
    "MVP", "CFFC", "FFC", "HEX", "ROAD TO UFC",
    "BJJ", "ACA", "TITAN FC"
]
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
    text_upper = row_text.upper()
    if "UFC" not in text_upper:
        return False
    for promo in IGNORED_PROMOTIONS:
        if promo in text_upper:
            return False
    return True

def get_playwright_page():
    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    page = context.new_page()
    stealth_sync(page)
    return playwright, browser, context, page

def scrape_ufc_moneyline(page):
    print(f"🌐 Scraping at {datetime.datetime.now().strftime('%H:%M:%S')}")
    page.goto(URL, wait_until="domcontentloaded")
    page.wait_for_selector("div.market-row, tr.odds-row, div.event-container, span.odds-value", timeout=15000)
    time.sleep(5)

    soup = BeautifulSoup(page.content(), "html.parser")
    fights = []
    fight_rows = soup.select("div.market-row, tr.odds-row, div.event-container, div.market, div.fight-row")

    for row in fight_rows:
        try:
            row_text = row.get_text()
            if not is_ufc_fight(row_text):
                continue

            names = row.select("span.participant-name, div.team-name, div.fighter-name, .name")
            if len(names) < 2: continue
            fighter1 = names[0].get_text(strip=True)
            fighter2 = names[1].get_text(strip=True)

            odds_elements = row.select("span.odds-value, div.moneyline, button.odds-button, .odds")
            if len(odds_elements) >= 2:
                odds1_str = odds_elements[0].get_text(strip=True)
                odds2_str = odds_elements[1].get_text(strip=True)

                if parse_american_odds(odds1_str) is None or parse_american_odds(odds2_str) is None:
                    continue

                fight_key = f"{fighter1} vs {fighter2}"
                fights.append({
                    "fight": fight_key,
                    "fighter1": fighter1,
                    "fighter1_odds": odds1_str,
                    "fighter2": fighter2,
                    "fighter2_odds": odds2_str,
                    "timestamp": datetime.datetime.now().isoformat()
                })
        except:
            continue

    print(f"✅ Scraped {len(fights)} UFC fights")
    return fights

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
            for fighter_key in ["fighter1", "fighter2"]:
                old_odds_str = old.get(f"{fighter_key}_odds")
                new_odds_str = fight.get(f"{fighter_key}_odds")
                if old_odds_str != new_odds_str:
                    old_odds = parse_american_odds(old_odds_str)
                    new_odds = parse_american_odds(new_odds_str)
                    if old_odds is not None and new_odds is not None:
                        diff = abs(new_odds - old_odds)
                        if diff >= MIN_MOVEMENT_POINTS:
                            direction = '↑' if new_odds > old_odds else '↓'
                            msg = f"🔄 **{key}**\n{fight[fighter_key]} odds moved: {old_odds_str} → **{new_odds_str}** ({direction}{diff} pts)"
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
                print("⚠️ No UFC fights found")

            print(f"⏳ Sleeping {POLL_INTERVAL_SECONDS//60} minutes...")
            time.sleep(POLL_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        print("🛑 Shutting down...")
    finally:
        page.close()
        context.close()
        browser.close()
        pw.stop()

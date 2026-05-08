import os
import time
import json
import datetime
import requests
import re
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

print("🚀 UFC BetOnline Monitor started (PLAYWRIGHT v15 - FIXED PAIRING AFTER MONEYLINE)")

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
URL = "https://www.betonline.ag/sportsbook/martial-arts/mma"
DATA_FILE = "/tmp/ufc_odds_history.json"
POLL_INTERVAL_SECONDS = 90
MIN_MOVEMENT_POINTS = 10

if not DISCORD_WEBHOOK_URL:
    print("❌ Missing DISCORD_WEBHOOK_URL!")
    raise ValueError("Missing DISCORD_WEBHOOK_URL")

GARBAGE = {"betonline", "sportsbook", "betting world", "vip", "rewards", "crypto", "tutorial", "privacy", "policy", "wrapper", "jds", "js", "betslip", "feature_", "webappconfig", "chashout", "new_relic", "sas_rollout", "kameleoon", "diffusion", "bff_", "key_cloak", "newrelic", "gtm", "intercom", "xtremepush", "strapi", "cashoutapi", "edgetier", "surveymonkey", "widget", "cash", "drop", "enter", "code", "promo", "bonus", "reward"}

def scrape_ufc_moneyline():
    print(f"🌐 Scraping at {datetime.datetime.now().strftime('%H:%M:%S')}")
    fights = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            page = browser.new_page()
            print("🌍 Navigating to BetOnline...")
            page.goto(URL, wait_until="load", timeout=60000)
            print("⏳ Waiting for dynamic content...")
            page.wait_for_timeout(15000)

            content = page.content()
            browser.close()

        soup = BeautifulSoup(content, "html.parser")
        full_text = soup.get_text(separator=" ", strip=True)

        odds_pattern = re.compile(r'([+-]\d{2,4})')
        name_pattern = re.compile(r'([A-Z][A-Za-z\']{4,40}\s[A-Z][A-Za-z\']{4,40})')

        # v15 change: look for the block RIGHT AFTER "Moneyline"
        for block in re.split(r'Moneyline', full_text):
            if "UFC" not in block.upper():
                continue

            names = name_pattern.findall(block)
            odds = odds_pattern.findall(block)

            if len(names) >= 2 and len(odds) >= 2:
                fighter1 = names[0].strip()
                fighter2 = names[1].strip()
                fight_key = f"{fighter1} vs {fighter2}"

                if any(g in fight_key.lower() for g in GARBAGE):
                    continue

                fights.append({
                    "fight": fight_key,
                    "fighter1": fighter1,
                    "fighter1_odds": odds[0],
                    "fighter2": fighter2,
                    "fighter2_odds": odds[1],
                    "timestamp": datetime.datetime.now().isoformat()
                })
                print(f"✅ Found fight: {fight_key} | {odds[0]} vs {odds[1]}")

        print(f"✅ Scraped {len(fights)} potential fights")

        if len(fights) == 0:
            print("🔍 DEBUG: Still 0 real fights - dumping first 12,000 chars:")
            print(repr(full_text[:12000]))

        return fights

    except Exception as e:
        print(f"❌ Playwright error: {e}")
        return []

# ====================== REST OF CODE ======================
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
    if not odds_str: return None
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

def send_discord(message):
    payload = {"content": message}
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        print("📨 Discord message sent")
    except Exception as e:
        print("Discord error:", e)

if __name__ == "__main__":
    while True:
        current_fights = scrape_ufc_moneyline()
        if current_fights:
            old_data = load_history()
            movements = detect_movements(old_data, current_fights)
            for msg in movements:
                print(msg)
                send_discord(msg)
            save_history(current_fights)
        else:
            print("⚠️ No fights found this cycle")

        print(f"⏳ Sleeping {POLL_INTERVAL_SECONDS} seconds...")
        time.sleep(POLL_INTERVAL_SECONDS)

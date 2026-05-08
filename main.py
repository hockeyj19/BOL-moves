import os
import time
import json
import datetime
import requests
from bs4 import BeautifulSoup
import re

print("🚀 UFC BetOnline Monitor started (DISCORD - TEST MODE)")

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
URL = "https://www.betonline.ag/sportsbook/martial-arts/mma"
DATA_FILE = "/tmp/ufc_odds_history.json"
POLL_INTERVAL_SECONDS = 60   # shortened for testing
MIN_MOVEMENT_POINTS = 10

if not DISCORD_WEBHOOK_URL:
    print("❌ Missing DISCORD_WEBHOOK_URL!")
    raise ValueError("Missing DISCORD_WEBHOOK_URL")

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

print("✅ Starting scrape loop...")

def scrape_ufc_moneyline():
    print(f"🌐 Scraping at {datetime.datetime.now().strftime('%H:%M:%S')}")
    try:
        r = requests.get(URL, headers=headers, timeout=15)
        r.raise_for_status()
        print(f"✅ Page loaded ({len(r.text):,} characters)")
    except Exception as e:
        print(f"❌ Request failed: {e}")
        return []

    # ... (rest of the scrape function remains the same)
    soup = BeautifulSoup(r.text, "html.parser")
    print(f"📊 'UFC' in page? → {'UFC' in r.text.upper()}")
    odds_pattern = re.compile(r'([+-]\d{2,4})')
    all_odds = odds_pattern.findall(r.text)
    print(f"📊 Found {len(all_odds)} potential odds")

    fights = []
    for block in soup.find_all(string=lambda text: text and "UFC" in text.upper()):
        try:
            block_text = str(block).strip()
            odds_in_block = odds_pattern.findall(block_text)
            if len(odds_in_block) >= 2:
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
                    print(f"✅ Found fight: {fight_key}")
        except:
            continue

    print(f"✅ Scraped {len(fights)} fights")
    return fights

# (rest of the code stays the same - load_history, save_history, detect_movements, send_discord, etc.)

def send_discord(message):
    payload = {"content": message}
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        print("📨 Discord sent")
    except Exception as e:
        print("Discord error:", e)

# ====================== Rest of code ======================
# ... (keep the rest of your functions exactly as they were)

if __name__ == "__main__":
    while True:
        current_fights = scrape_ufc_moneyline()
        # ... (keep the rest of the loop the same)
        print(f"⏳ Sleeping {POLL_INTERVAL_SECONDS} seconds...")
        time.sleep(POLL_INTERVAL_SECONDS)

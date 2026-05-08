import os
import time
import json
import datetime
import requests
import re

print("🚀 UFC BetOnline Monitor started (DISCORD - FINAL v4 - FULL TEXT PARSER)")

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
URL = "https://www.betonline.ag/sportsbook/martial-arts/mma"
DATA_FILE = "/tmp/ufc_odds_history.json"
POLL_INTERVAL_SECONDS = 60
MIN_MOVEMENT_POINTS = 10

if not DISCORD_WEBHOOK_URL:
    print("❌ Missing DISCORD_WEBHOOK_URL!")
    raise ValueError("Missing DISCORD_WEBHOOK_URL")

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
}

def scrape_ufc_moneyline():
    print(f"🌐 Scraping at {datetime.datetime.now().strftime('%H:%M:%S')}")
    try:
        r = requests.get(URL, headers=headers, timeout=25)
        r.raise_for_status()
        print(f"✅ Page loaded ({len(r.text):,} characters)")
    except Exception as e:
        print(f"❌ Request failed: {e}")
        return []

    full_text = r.text

    print(f"📊 'UFC' in page? → {'UFC' in full_text.upper()}")
    print(f"📊 Found {len(re.findall(r'([+-]\d{2,4})', full_text))} potential odds in full text")

    # Broad search for fights: look for 2 fighter names near 2 odds
    fights = []
    odds_pattern = re.compile(r'([+-]\d{2,4})')
    name_pattern = re.compile(r'([A-Z][A-Za-z\s\.\'-]{5,40})')

    # Split into lines/blocks and search
    for line in full_text.splitlines():
        if "UFC" not in line.upper():
            continue
        odds = odds_pattern.findall(line)
        names = name_pattern.findall(line)
        if len(odds) >= 2 and len(names) >= 2:
            fighter1 = names[0].strip()
            fighter2 = names[1].strip()
            fight_key = f"{fighter1} vs {fighter2}"
            fights.append({
                "fight": fight_key,
                "fighter1": fighter1,
                "fighter1_odds": odds[0],
                "fighter2": fighter2,
                "fighter2_odds": odds[1],
                "timestamp": datetime.datetime.now().isoformat()
            })
            print(f"✅ Found fight: {fight_key} | {odds[0]} vs {odds[1]}")

    print(f"✅ Scraped {len(fights)} potential UFC fights")
    if len(fights) == 0:
        print("🔍 DEBUG: Still 0 fights - dumping first 800 chars of page for diagnosis:")
        print(repr(full_text[:800]))

    return fights

# ====================== HISTORY & MOVEMENT ======================
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

def send_discord(message):
    payload = {"content": message}
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        print("📨 Discord message sent")
    except Exception as e:
        print("Discord error:", e)

# ====================== MAIN LOOP ======================
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

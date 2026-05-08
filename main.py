# ================================= UFC BETONLINE MONITOR (PLAYWRIGHT v18 - FIXED UFC PARSER) =================================

import os
import time
import json
import datetime
import requests
import re

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

print("🚀 UFC BetOnline Monitor started (PLAYWRIGHT v18 - FIXED UFC PARSER)")

# ================================= CONFIG =================================

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

URL = "https://www.betonline.ag/sportsbook/martial-arts/mma"

DATA_FILE = "/tmp/ufc_odds_history.json"

POLL_INTERVAL_SECONDS = 90

MIN_MOVEMENT_POINTS = 10

# ================================= VALIDATION =================================

if not DISCORD_WEBHOOK_URL:
    print("❌ Missing DISCORD_WEBHOOK_URL!")
    raise ValueError("Missing DISCORD_WEBHOOK_URL")

# ================================= GARBAGE FILTER =================================

GARBAGE = {
    "betonline",
    "sportsbook",
    "betting world",
    "vip",
    "rewards",
    "crypto",
    "tutorial",
    "privacy",
    "policy",
    "wrapper",
    "jds",
    "js",
    "betslip",
    "feature_",
    "webappconfig",
    "cashoutapi",
    "new_relic",
    "newrelic",
    "gtm",
    "intercom",
    "widget",
    "promo",
    "bonus",
    "reward"
}

# ================================= HELPERS =================================

def parse_american_odds(odds_str):
    if not odds_str:
        return None

    cleaned = str(odds_str).strip()

    if cleaned.startswith(("+", "-")) and cleaned[1:].isdigit():
        return int(cleaned)

    return None

# ================================= SCRAPER =================================

def scrape_ufc_moneyline():

    print(f"\n🌐 Scraping at {datetime.datetime.now().strftime('%H:%M:%S')}")

    fights = []

    try:

        with sync_playwright() as p:

            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox"]
            )

            page = browser.new_page()

            print("🌍 Navigating to BetOnline...")

            page.goto(URL, wait_until="domcontentloaded", timeout=60000)

            # allow sportsbook hydration
            page.wait_for_timeout(5000)

            # force lazy-loaded fights to render
            page.mouse.wheel(0, 6000)

            page.wait_for_timeout(2000)

            content = page.content()

            browser.close()

        soup = BeautifulSoup(content, "html.parser")

        full_text = soup.get_text(separator=" ", strip=True)

        # ================================= UFC REGEX EXTRACTION =================================

        ufc_pattern = re.compile(
            r'(\d+)\s*-\s*([A-Za-zÀ-ÿ\-\'. ]+?)\s+'
            r'(\d+)\s*-\s*([A-Za-zÀ-ÿ\-\'. ]+?)\s+'
            r'Moneyline\s+'
            r'\2\s+([+-]\d+)\s+'
            r'\4\s+([+-]\d+)',
            re.MULTILINE
        )

        matches = ufc_pattern.findall(full_text)

        print(f"🔍 Regex matches found: {len(matches)}")

        seen = set()

        for match in matches:

            fighter1 = " ".join(match[1].split()).strip()
            fighter2 = " ".join(match[3].split()).strip()

            odds1 = match[4].strip()
            odds2 = match[5].strip()

            fight_key = f"{fighter1} vs {fighter2}"

            # dedupe
            if fight_key in seen:
                continue

            seen.add(fight_key)

            # garbage filter
            if any(g in fight_key.lower() for g in GARBAGE):
                continue

            fights.append({
                "fight": fight_key,
                "fighter1": fighter1,
                "fighter1_odds": odds1,
                "fighter2": fighter2,
                "fighter2_odds": odds2,
                "timestamp": datetime.datetime.now().isoformat()
            })

            print(f"✅ Found fight: {fight_key} | {odds1} vs {odds2}")

        print(f"\n✅ FINAL UFC FIGHTS SCRAPED: {len(fights)}")

        # debug dump if nothing found
        if len(fights) == 0:
            print("\n🔍 DEBUG DUMP (first 8000 chars):\n")
            print(repr(full_text[:8000]))

        return fights

    except Exception as e:

        print(f"❌ Playwright error: {e}")

        return []

# ================================= HISTORY =================================

def load_history():

    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)

    except:
        return {}

def save_history(current_fights):

    with open(DATA_FILE, "w") as f:
        json.dump(
            {f["fight"]: f for f in current_fights},
            f,
            indent=2
        )

# ================================= MOVEMENT DETECTION =================================

def detect_movements(old_data, new_fights):

    messages = []

    for fight in new_fights:

        key = fight["fight"]

        if key not in old_data:
            continue

        old = old_data[key]

        for fk in ["fighter1", "fighter2"]:

            old_odds = old.get(f"{fk}_odds")
            new_odds = fight.get(f"{fk}_odds")

            if old_odds == new_odds:
                continue

            old_val = parse_american_odds(old_odds)
            new_val = parse_american_odds(new_odds)

            if old_val is None or new_val is None:
                continue

            diff = abs(new_val - old_val)

            if diff < MIN_MOVEMENT_POINTS:
                continue

            direction = "↑" if new_val > old_val else "↓"

            msg = (
                f"🔄 **{key}**\n"
                f"{fight[fk]} odds moved: "
                f"{old_odds} → **{new_odds}** "
                f"({direction}{diff} pts)"
            )

            messages.append({
                "text": msg,
                "movement": diff
            })

    # biggest movement first
    messages.sort(
        key=lambda x: x["movement"],
        reverse=True
    )

    return messages

# ================================= DISCORD =================================

def send_discord(message):

    payload = {
        "content": message
    }

    try:

        response = requests.post(
            DISCORD_WEBHOOK_URL,
            json=payload,
            timeout=10
        )

        if response.status_code in [200, 204]:
            print("📨 Discord message sent")
        else:
            print(f"⚠️ Discord HTTP {response.status_code}")

    except Exception as e:

        print("❌ Discord error:", e)

# ================================= MAIN LOOP =================================

if __name__ == "__main__":

    while True:

        current_fights = scrape_ufc_moneyline()

        if current_fights:

            old_data = load_history()

            movements = detect_movements(
                old_data,
                current_fights
            )

            for movement in movements:

                print("\n" + movement["text"])

                send_discord(movement["text"])

            save_history(current_fights)

        else:

            print("⚠️ No fights found this cycle")

        print(f"\n⏳ Sleeping {POLL_INTERVAL_SECONDS} seconds...\n")

        time.sleep(POLL_INTERVAL_SECONDS)

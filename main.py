import os
import time
import json
import datetime
import requests
import re
from playwright.sync_api import sync_playwright

print("🚀 UFC BetOnline Monitor started (PLAYWRIGHT v37 - CLEAN UFC ONLY)")

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
URL = "https://www.betonline.ag/sportsbook/martial-arts/mma"
DATA_FILE = "/tmp/ufc_odds_history.json"
POLL_INTERVAL_SECONDS = 90
MIN_MOVEMENT_POINTS = 10

if not DISCORD_WEBHOOK_URL:
    print("❌ Missing DISCORD_WEBHOOK_URL!")
    raise ValueError("Missing DISCORD_WEBHOOK_URL")

def scrape_ufc_moneyline():
    print(f"🌐 Scraping at {datetime.datetime.now().strftime('%H:%M:%S')}")
    fights = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            page = browser.new_page()

            def handle_response(response):
                if "offering-by-league" in response.url.lower():
                    try:
                        data = response.json()
                        game_offering = data.get("GameOffering", {}) or data.get("data", {}).get("GameOffering", {})
                        games = game_offering.get("GamesDescription", [])

                        # CLEAN UFC-ONLY FILTER: check top-level JSON once
                        full_json = str(data).upper()
                        is_ufc_event = "UFC" in full_json

                        print(f"   📌 Found {len(games)} games | UFC event detected: {is_ufc_event}")

                        if not is_ufc_event:
                            return  # skip everything if not a UFC card

                        for game in games:
                            f1 = (game.get("AwayTeam") or game.get("Participant1") or game.get("Team1") or game.get("Away") or "Unknown")
                            f2 = (game.get("HomeTeam") or game.get("Participant2") or game.get("Team2") or game.get("Home") or "Unknown")

                            fight_key = f"{f1} vs {f2}"

                            away_line = game.get("AwayLine") or game.get("AwayTeamLine") or {}
                            home_line = game.get("HomeLine") or game.get("HomeTeamLine") or {}

                            odds1 = (away_line.get("MoneyLine", {}).get("Line") or 
                                     away_line.get("MoneyLine") or 
                                     away_line.get("Line") or "N/A")
                            odds2 = (home_line.get("MoneyLine", {}).get("Line") or 
                                     home_line.get("MoneyLine") or 
                                     home_line.get("Line") or "N/A")

                            if f1 != "Unknown" and f2 != "Unknown" and odds1 != "N/A" and odds2 != "N/A":
                                fights.append({
                                    "fight": fight_key,
                                    "fighter1": f1,
                                    "fighter1_odds": str(odds1),
                                    "fighter2": f2,
                                    "fighter2_odds": str(odds2),
                                    "timestamp": datetime.datetime.now().isoformat()
                                })
                                print(f"✅ Found fight: {fight_key} | {odds1} vs {odds2}")

                    except Exception as e:
                        print(f"   JSON parse error: {e}")

            page.on("response", handle_response)

            page.goto(URL, wait_until="load", timeout=60000)
            page.wait_for_timeout(20000)
            browser.close()

        print(f"✅ Scraped {len(fights)} potential fights")
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

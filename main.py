import os
import time
import json
import datetime
import requests
from playwright.sync_api import sync_playwright

print("🚀 UFC BetOnline Monitor started (v46 - YOUR EXACT DISCORD FORMAT)")

# ========================= CONFIG =========================
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
URL = "https://www.betonline.ag/sportsbook/martial-arts/mma"
DATA_FILE = "/tmp/ufc_odds_history.json"
POLL_INTERVAL_SECONDS = 90
MIN_MOVEMENT_POINTS = 10
# ========================================================

if not DISCORD_WEBHOOK_URL:
    print("❌ Missing DISCORD_WEBHOOK_URL environment variable!")
    raise ValueError("Missing DISCORD_WEBHOOK_URL")

def parse_american_odds(odds):
    """Safely convert int, float, or str odds"""
    if odds is None or odds == "N/A" or odds == "":
        return None
    if isinstance(odds, (int, float)):
        return int(odds)
    if isinstance(odds, str):
        cleaned = odds.strip()
        if cleaned.startswith(('+', '-')) and cleaned[1:].isdigit():
            return int(cleaned)
    return None

def load_history():
    """Load history as dict. Handles old list format automatically."""
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                data = json.load(f)
            if isinstance(data, list):
                print("🔄 Migrating old history list → dict format...")
                return {fight.get("key"): fight for fight in data if isinstance(fight, dict) and "key" in fight}
            return data
        except Exception as e:
            print(f"⚠️ History load error: {e}")
            return {}
    return {}

def save_history(current_fights):
    """Always save as dict {fight_key: fight_data}"""
    history_dict = {fight["key"]: fight for fight in current_fights if "key" in fight}
    try:
        with open(DATA_FILE, "w") as f:
            json.dump(history_dict, f, indent=2)
    except Exception as e:
        print(f"⚠️ Failed to save history: {e}")

def detect_movements(old_data, current_fights):
    messages = []
    for fight in current_fights:
        key = fight["key"]                    # full matchup
        old = old_data.get(key, {})
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
                        # YOUR EXACT REQUESTED FORMAT
                        msg = f"{fight[fk]} {old_odds} → {new_odds} ({direction}{diff} pts)\n{key}"
                        messages.append(msg)
    return messages

def send_discord(message):
    payload = {"content": message}
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        print("📨 Discord message sent")
    except Exception as e:
        print("Discord error:", e)

def scrape_ufc_moneyline():
    print(f"🌐 Scraping at {datetime.datetime.now().strftime('%H:%M:%S')}")
    fights = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            page = browser.new_page()

            def handle_response(response):
                nonlocal fights
                if "offering-by-league" in response.url.lower():
                    print(f"🔥 FOUND OFFERING-BY-LEAGUE → {response.url}")
                    try:
                        data = response.json()
                        games = data.get("GameOffering", {}).get("GamesDescription", [])
                        print(f"   📌 Found {len(games)} games in GameOffering")

                        for g in games:
                            game = g.get("Game", g)
                            schedule = game.get("ScheduleText", "New MMA Odds").strip()

                            if "UFC" not in schedule.upper():
                                continue

                            fighter1 = game.get("AwayTeam", "Unknown")
                            fighter2 = game.get("HomeTeam", "Unknown")

                            away_line = game.get("AwayLine", {}) or {}
                            home_line = game.get("HomeLine", {}) or {}
                            odds1 = (away_line.get("MoneyLine", {}).get("Line") or 
                                    away_line.get("Line") or "N/A")
                            odds2 = (home_line.get("MoneyLine", {}).get("Line") or 
                                    home_line.get("Line") or "N/A")

                            if fighter1 == "Unknown" or fighter2 == "Unknown":
                                continue

                            fight_key = f"{fighter1} vs {fighter2}"
                            fights.append({
                                "key": fight_key,
                                "fighter1": fighter1,
                                "fighter2": fighter2,
                                "fighter1_odds": str(odds1),
                                "fighter2_odds": str(odds2),
                                "schedule": schedule
                            })
                            print(f"✅ Found UFC fight: {fight_key} | {odds1} vs {odds2} | {schedule}")

                        print(f"✅ FINAL UFC FIGHTS SCRAPED: {len(fights)}")
                    except Exception as e:
                        print(f"❌ JSON parse error: {e}")

            page.on("response", handle_response)
            page.goto(URL, wait_until="load", timeout=30000)
            page.wait_for_timeout(15000)
            browser.close()
    except Exception as e:
        print(f"❌ Playwright error: {e}")

    return fights

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
            print("⚠️ No UFC fights found this cycle")

        print(f"⏳ Sleeping {POLL_INTERVAL_SECONDS} seconds...")
        time.sleep(POLL_INTERVAL_SECONDS)

import os
import time
import json
import datetime
import requests
import re
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

print("🚀 UFC BetOnline Monitor started (PLAYWRIGHT v20 - OFFER-BY-LEAGUE JSON INTERCEPT)")

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

            # v20: Intercept network responses for offer-by-league JSON
            def handle_response(response):
                if "offer-by-league" in response.url.lower():
                    print(f"🔥 FOUND OFFER-BY-LEAGUE JSON → {response.url}")
                    try:
                        data = response.json()
                        print("✅ Successfully parsed JSON (first 500 chars):")
                        print(repr(str(data)[:500]))

                        # Extract UFC fights from the structured JSON
                        if isinstance(data, dict):
                            # Common structure: leagues → events → offers
                            leagues = data.get("leagues") or data.get("data", {}).get("leagues", [])
                            for league in leagues:
                                league_name = league.get("name", "") or league.get("leagueName", "")
                                if "UFC" not in league_name.upper():
                                    continue
                                print(f"📌 Found UFC league: {league_name}")

                                events = league.get("events") or league.get("eventList", [])
                                for event in events:
                                    event_name = event.get("name", "")
                                    offers = event.get("offers") or event.get("offerList", [])
                                    for offer in offers:
                                        if offer.get("type") == "moneyline" or "moneyline" in str(offer.get("name", "")).lower():
                                            sides = offer.get("sides") or offer.get("sideList", [])
                                            if len(sides) >= 2:
                                                f1 = sides[0].get("name", "")
                                                o1 = sides[0].get("price", "")
                                                f2 = sides[1].get("name", "")
                                                o2 = sides[1].get("price", "")
                                                fight_key = f"{f1} vs {f2}"
                                                fights.append({
                                                    "fight": fight_key,
                                                    "fighter1": f1,
                                                    "fighter1_odds": str(o1),
                                                    "fighter2": f2,
                                                    "fighter2_odds": str(o2),
                                                    "timestamp": datetime.datetime.now().isoformat()
                                                })
                                                print(f"✅ Found fight: {fight_key} | {o1} vs {o2}")
                    except Exception as json_err:
                        print(f"JSON parse error: {json_err}")

            page.on("response", handle_response)

            print("🌍 Navigating to BetOnline...")
            page.goto(URL, wait_until="load", timeout=60000)
            print("⏳ Waiting for dynamic content (API calls)...")
            page.wait_for_timeout(15000)   # give time for the JSON to load

            browser.close()

        print(f"✅ Scraped {len(fights)} potential fights from JSON")

        if len(fights) == 0:
            print("🔍 No fights found yet — check the logs above for the offer-by-league URL")

        return fights

    except Exception as e:
        print(f"❌ Playwright error: {e}")
        return []

# ====================== REST OF CODE (unchanged) ======================
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

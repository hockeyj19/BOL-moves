import os
import re
import time
import logging
import sqlite3
import datetime
import requests

from playwright.sync_api import sync_playwright

# =========================================================
# CONFIG
# =========================================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

URL = "https://www.betonline.ag/sportsbook/martial-arts/mma"

POLL_INTERVAL_SECONDS = 600
MIN_MOVEMENT_POINTS = 10
ALERT_COOLDOWN_MINUTES = 30

DB_FILE = "ufc_monitor.db"

# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger(__name__)

# =========================================================
# VALIDATION
# =========================================================

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    raise ValueError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")

# =========================================================
# DATABASE
# =========================================================

def init_db():

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS odds (
        fight_key TEXT PRIMARY KEY,
        fighter1 TEXT,
        fighter2 TEXT,
        fighter1_odds INTEGER,
        fighter2_odds INTEGER,
        updated_at TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS alerts (
        fight_key TEXT PRIMARY KEY,
        last_alert_time TEXT
    )
    """)

    conn.commit()
    conn.close()

# =========================================================
# TELEGRAM
# =========================================================

def send_telegram(message):

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    }

    try:

        r = requests.post(
            url,
            json=payload,
            timeout=15
        )

        r.raise_for_status()

        logger.info("Telegram alert sent")

    except Exception as e:

        logger.error(f"Telegram error: {e}")

# =========================================================
# HELPERS
# =========================================================

def normalize_fight_key(f1, f2):

    fighters = sorted([
        f1.strip(),
        f2.strip()
    ])

    return f"{fighters[0]} vs {fighters[1]}"

def parse_odds(value):

    if not value:
        return None

    value = value.strip()

    if re.match(r'^[+-]\d+$', value):
        return int(value)

    return None

def should_alert(fight_key):

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute("""
    SELECT last_alert_time
    FROM alerts
    WHERE fight_key = ?
    """, (fight_key,))

    row = c.fetchone()

    conn.close()

    if not row:
        return True

    last_alert = datetime.datetime.fromisoformat(row[0])

    diff = datetime.datetime.utcnow() - last_alert

    return diff.total_seconds() > (
        ALERT_COOLDOWN_MINUTES * 60
    )

def update_alert_timestamp(fight_key):

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    now = datetime.datetime.utcnow().isoformat()

    c.execute("""
    INSERT OR REPLACE INTO alerts (
        fight_key,
        last_alert_time
    ) VALUES (?, ?)
    """, (
        fight_key,
        now
    ))

    conn.commit()
    conn.close()

# =========================================================
# SCRAPER
# =========================================================

def scrape_ufc_fights():

    logger.info("Launching browser")

    fights = []

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled"
            ]
        )

        page = browser.new_page()

        page.set_extra_http_headers({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/134.0.0.0 Safari/537.36"
            )
        })

        try:

            logger.info("Opening BetOnline MMA page")

            page.goto(
                URL,
                wait_until="networkidle",
                timeout=60000
            )

            page.wait_for_timeout(5000)

            body_text = page.locator("body").inner_text()

            lines = body_text.split("\n")

            cleaned = []

            for line in lines:

                line = line.strip()

                if not line:
                    continue

                cleaned.append(line)

            logger.info(
                f"Collected {len(cleaned)} text lines"
            )

            odds_pattern = re.compile(r'^[+-]\d+$')

            banned_words = [
                "UFC",
                "Bellator",
                "PFL",
                "ONE",
                "BJJ",
                "Main Card",
                "Prelims",
                "Fight Props",
                "Method",
                "Round"
            ]

            for i in range(len(cleaned) - 3):

                try:

                    fighter1 = cleaned[i]
                    fighter2 = cleaned[i + 1]

                    odds1 = cleaned[i + 2]
                    odds2 = cleaned[i + 3]

                    if (
                        odds_pattern.match(odds1)
                        and odds_pattern.match(odds2)
                    ):

                        if len(fighter1) < 3:
                            continue

                        if len(fighter2) < 3:
                            continue

                        if any(
                            word.lower() in fighter1.lower()
                            for word in banned_words
                        ):
                            continue

                        if any(
                            word.lower() in fighter2.lower()
                            for word in banned_words
                        ):
                            continue

                        fight_key = normalize_fight_key(
                            fighter1,
                            fighter2
                        )

                        fights.append({
                            "fight_key": fight_key,
                            "fighter1": fighter1,
                            "fighter2": fighter2,
                            "fighter1_odds": int(odds1),
                            "fighter2_odds": int(odds2)
                        })

                except Exception:
                    continue

            browser.close()

        except Exception as e:

            logger.error(f"Scraper failure: {e}")

            try:
                browser.close()
            except:
                pass

    unique = {}

    for fight in fights:
        unique[fight["fight_key"]] = fight

    final_fights = list(unique.values())

    logger.info(
        f"Detected {len(final_fights)} UFC fights"
    )

    return final_fights

# =========================================================
# ODDS MOVEMENT
# =========================================================

def process_movements(fights):

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    for fight in fights:

        fight_key = fight["fight_key"]

        c.execute("""
        SELECT
            fighter1_odds,
            fighter2_odds
        FROM odds
        WHERE fight_key = ?
        """, (fight_key,))

        old = c.fetchone()

        if old:

            old_f1 = old[0]
            old_f2 = old[1]

            new_f1 = fight["fighter1_odds"]
            new_f2 = fight["fighter2_odds"]

            diff1 = abs(new_f1 - old_f1)
            diff2 = abs(new_f2 - old_f2)

            if diff1 >= MIN_MOVEMENT_POINTS:

                if should_alert(fight_key):

                    direction = (
                        "↑"
                        if new_f1 > old_f1
                        else "↓"
                    )

                    msg = (
                        f"🔄 {fight['fighter1']} "
                        f"vs "
                        f"{fight['fighter2']}\n"
                        f"{fight['fighter1']}: "
                        f"{old_f1} → {new_f1} "
                        f"({direction}{diff1})"
                    )

                    logger.info(msg)

                    send_telegram(msg)

                    update_alert_timestamp(
                        fight_key
                    )

            if diff2 >= MIN_MOVEMENT_POINTS:

                if should_alert(fight_key):

                    direction = (
                        "↑"
                        if new_f2 > old_f2
                        else "↓"
                    )

                    msg = (
                        f"🔄 {fight['fighter1']} "
                        f"vs "
                        f"{fight['fighter2']}\n"
                        f"{fight['fighter2']}: "
                        f"{old_f2} → {new_f2} "
                        f"({direction}{diff2})"
                    )

                    logger.info(msg)

                    send_telegram(msg)

                    update_alert_timestamp(
                        fight_key
                    )

        c.execute("""
        INSERT OR REPLACE INTO odds (
            fight_key,
            fighter1,
            fighter2,
            fighter1_odds,
            fighter2_odds,
            updated_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            fight["fight_key"],
            fight["fighter1"],
            fight["fighter2"],
            fight["fighter1_odds"],
            fight["fighter2_odds"],
            datetime.datetime.utcnow().isoformat()
        ))

    conn.commit()
    conn.close()

# =========================================================
# MAIN LOOP
# =========================================================

def main():

    logger.info(
        "Starting UFC BetOnline Monitor"
    )

    init_db()

    send_telegram(
        "✅ UFC BetOnline Monitor started"
    )

    while True:

        cycle_start = time.time()

        try:

            logger.info(
                "Beginning scrape cycle"
            )

            fights = scrape_ufc_fights()

            if fights:
                process_movements(fights)
            else:
                logger.warning(
                    "No fights detected"
                )

        except Exception as e:

            logger.error(
                f"Main loop error: {e}"
            )

        elapsed = time.time() - cycle_start

        sleep_time = max(
            0,
            POLL_INTERVAL_SECONDS - elapsed
        )

        logger.info(
            f"Sleeping "
            f"{round(sleep_time)} seconds"
        )

        time.sleep(sleep_time)

# =========================================================

if __name__ == "__main__":
    main()

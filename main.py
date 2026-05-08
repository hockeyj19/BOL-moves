def scrape_ufc_moneyline():

    print(f"\n🌐 Scraping at {datetime.datetime.now().strftime('%H:%M:%S')}")

    fights = []

    captured_json = []

    try:

        with sync_playwright() as p:

            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox"]
            )

            page = browser.new_page()

            # ================================= RESPONSE INTERCEPT =================================

            def handle_response(response):

                url = response.url.lower()

                if "offer-by-league" in url:

                    print(f"🎯 Captured endpoint: {response.url}")

                    try:

                        data = response.json()

                        captured_json.append(data)

                    except Exception as e:

                        print("❌ JSON parse failed:", e)

            page.on("response", handle_response)

            print("🌍 Navigating to BetOnline...")

            page.goto(
                URL,
                wait_until="networkidle",
                timeout=60000
            )

            page.wait_for_timeout(8000)

            browser.close()

        print(f"📦 Captured JSON payloads: {len(captured_json)}")

        seen = set()

        # ================================= MMA FILTER =================================

        MMA_KEYWORDS = [
            "ufc",
            "mma",
            "martial arts",
            "rizin",
            "bellator",
            "pfl",
            "one championship",
            "cage warriors",
            "dwcs"
        ]

        for payload in captured_json:

            payload_text = json.dumps(payload).lower()

            # SKIP non-MMA payloads entirely
            if not any(k in payload_text for k in MMA_KEYWORDS):
                continue

            print("🥋 MMA payload detected")

            # ================================= REGEX EXTRACTION =================================

            #
            # Matches:
            #
            # Marco Tulio -183 Roman Kopylov +158
            #
            # Sean Strickland +420 Khamzat Chimaev -550
            #

            matches = re.findall(
                r'([A-Z][A-Za-zÀ-ÿ\-\'. ]{2,40})\s+([+-]\d+)\s+'
                r'([A-Z][A-Za-zÀ-ÿ\-\'. ]{2,40})\s+([+-]\d+)',
                payload_text,
                re.IGNORECASE
            )

            print(f"📊 Regex matches: {len(matches)}")

            for match in matches:

                fighter1 = " ".join(match[0].split()).title().strip()
                odds1 = match[1].strip()

                fighter2 = " ".join(match[2].split()).title().strip()
                odds2 = match[3].strip()

                # reject obvious non-fights
                banned = [
                    "moneyline",
                    "spread",
                    "total",
                    "over",
                    "under",
                    "tie"
                ]

                if any(b in fighter1.lower() for b in banned):
                    continue

                if any(b in fighter2.lower() for b in banned):
                    continue

                # sanity
                if len(fighter1.split()) < 2:
                    continue

                if len(fighter2.split()) < 2:
                    continue

                fight_key = f"{fighter1} vs {fighter2}"

                if fight_key in seen:
                    continue

                seen.add(fight_key)

                fights.append({
                    "fight": fight_key,
                    "fighter1": fighter1,
                    "fighter1_odds": odds1,
                    "fighter2": fighter2,
                    "fighter2_odds": odds2,
                    "timestamp": datetime.datetime.now().isoformat()
                })

                print(
                    f"✅ Found fight: "
                    f"{fight_key} | {odds1} vs {odds2}"
                )

        print(f"\n✅ FINAL UFC FIGHTS SCRAPED: {len(fights)}")

        # ================================= DEBUG =================================

        if len(fights) == 0:

            print("\n⚠️ NO UFC FIGHTS FOUND")

            if captured_json:

                try:

                    sample = json.dumps(captured_json[0], indent=2)

                    print(sample[:5000])

                except:
                    pass

        return fights

    except Exception as e:

        print(f"❌ Playwright error: {e}")

        return []

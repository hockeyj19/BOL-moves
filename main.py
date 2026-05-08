import os
import time
import datetime

print("🚀 TEST MODE - UFC BetOnline Monitor starting...")
print(f"✅ Python is running! Time: {datetime.datetime.now().strftime('%H:%M:%S')}")

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
if not DISCORD_WEBHOOK_URL:
    print("❌ Missing DISCORD_WEBHOOK_URL environment variable!")
else:
    print("✅ DISCORD_WEBHOOK_URL found")

print("🔄 This is a test loop. It will print every 30 seconds.")

count = 0
while True:
    count += 1
    print(f"✅ Test loop #{count} - Script is alive at {datetime.datetime.now().strftime('%H:%M:%S')}")
    time.sleep(30)

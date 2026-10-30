import os
import json
import urllib.request

token = os.environ["TELEGRAM_BOT_TOKEN"]
channel = os.environ["TELEGRAM_CHANNEL"]

data = json.dumps({
    "chat_id": channel,
    "text": "✅ টেস্ট: Opportunity Finder Bot কাজ করছে!"
}).encode("utf-8")

req = urllib.request.Request(
    f"https://api.telegram.org/bot{token}/sendMessage",
    data=data,
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(req) as resp:
    print(resp.status, resp.read().decode())

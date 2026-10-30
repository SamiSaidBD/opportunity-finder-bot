import os
import json
import urllib.request
import urllib.error

GEMINI_KEY = os.environ["GEMINI_API_KEY"]
TG_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TG_CHANNEL = os.environ["TELEGRAM_CHANNEL"]
BASE = "https://generativelanguage.googleapis.com/v1beta"


def call(url, body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"x-goog-api-key": GEMINI_KEY, "Content-Type": "application/json"}
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


models = call(f"{BASE}/models?pageSize=200").get("models", [])
skip = ["image", "tts", "audio", "live", "embedding", "robotics", "computer"]
names = []
for m in models:
    name = m["name"].replace("models/", "")
    if "flash" in name and "generateContent" in m.get("supportedGenerationMethods", []):
        if not any(s in name for s in skip):
            names.append(name)

lite = sorted([n for n in names if "lite" in n], reverse=True)
others = sorted([n for n in names if "lite" not in n], reverse=True)
order = (lite + others)[:8]
print("চেষ্টা করা হবে:", order)

working = None
reply = ""
for name in order:
    try:
        out = call(
            f"{BASE}/models/{name}:generateContent",
            {"contents": [{"parts": [{"text": "বাংলায় ছোট করে বলো: তুমি কাজ করছো?"}]}]},
        )
        parts = out["candidates"][0]["content"]["parts"]
        reply = "".join(p.get("text", "") for p in parts)
        working = name
        break
    except urllib.error.HTTPError as e:
        print(name, "ব্যর্থ:", e.code, e.read().decode("utf-8")[:300])
    except Exception as e:
        print(name, "ব্যর্থ:", e)

if not working:
    raise SystemExit("কোনো মডেলই কাজ করেনি, উপরের লাইনগুলো দেখুন")

text = f"✅ Gemini কাজ করছে\nমডেল: {working}\nউত্তর: {reply}"
tg = json.dumps({"chat_id": TG_CHANNEL, "text": text}).encode("utf-8")
req = urllib.request.Request(
    f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
    data=tg,
    headers={"Content-Type": "application/json"},
)
urllib.request.urlopen(req, timeout=60)
print("সফল। মডেল:", working)

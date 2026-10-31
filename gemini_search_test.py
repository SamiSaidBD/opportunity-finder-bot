import os
import re
import json
import urllib.request
import urllib.error

GEMINI_KEY = os.environ["GEMINI_API_KEY"]
TG_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TG_CHANNEL = os.environ["TELEGRAM_CHANNEL"]
BASE = "https://generativelanguage.googleapis.com/v1beta"
GH = {"x-goog-api-key": GEMINI_KEY}

PROMPT = """Use Google Search to find recent Reddit discussions (from the last 30 days if possible) where people complain about a specific problem, or ask for a tool or solution that doesn't seem to exist.
List 5 different discussions. For each one give: the subreddit, a one-line description of the problem, and what people in the comments said.
Only report what you actually found in the search results. Do not invent anything.
উত্তর বাংলায় দাও, তবে সাবরেডিটের নাম আর পরিচিত ইংরেজি শব্দ ইংরেজিতেই রাখো।"""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def real_url(u):
    # Google-এর ঘুরপথের লিংক থেকে আসল ঠিকানা বের করা
    try:
        opener = urllib.request.build_opener(NoRedirect)
        opener.open(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=20)
    except urllib.error.HTTPError as e:
        loc = e.headers.get("Location")
        if loc:
            return loc
    except Exception as e:
        print("লিংক খোলা যায়নি:", e)
    return u


def request_json(url, body=None, headers=None):
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=h)
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def send(text):
    request_json(
        f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
        {
            "chat_id": TG_CHANNEL,
            "text": text[:4000],
            "link_preview_options": {"is_disabled": True},
        },
    )


# ১. উপলব্ধ Flash মডেলের তালিকা (gemini-2 ধরনেরগুলো আগে)
models = request_json(f"{BASE}/models?pageSize=200", headers=GH).get("models", [])
skip = ["image", "tts", "audio", "live", "embedding", "robotics", "computer", "native"]
names = []
for m in models:
    n = m["name"].replace("models/", "")
    if "flash" in n and "generateContent" in m.get("supportedGenerationMethods", []):
        if not any(s in n for s in skip):
            names.append(n)
names = sorted(set(names), key=lambda n: (0 if "gemini-2" in n else 1, n))[:12]
print("চেষ্টা করা হবে:", names)

# ২. একে একে চেষ্টা
result = None
used = ""
errors = []
for model in names:
    try:
        result = request_json(
            f"{BASE}/models/{model}:generateContent",
            {
                "contents": [{"parts": [{"text": PROMPT}]}],
                "tools": [{"google_search": {}}],
            },
            GH,
        )
        used = model
        break
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        errors.append(f"{model}: {e.code}")
        print("ব্যর্থ:", model, e.code)
        print(body[:1500])
    except Exception as e:
        errors.append(f"{model}: {e}")
        print("ব্যর্থ:", model, e)

if result is None:
    send("❌ Search grounding কোনো মডেলে চলেনি\n\nচেষ্টা করা মডেল:\n" + "\n".join(errors or ["(কোনো মডেল পাওয়া যায়নি)"]))
    raise SystemExit("সব মডেল ব্যর্থ")

# ৩. ফলাফল
cand = result["candidates"][0]
text = "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", []))
gm = cand.get("groundingMetadata", {})
queries = gm.get("webSearchQueries", [])
chunks = gm.get("groundingChunks", [])

urls = []
for ch in chunks[:12]:
    web = ch.get("web", {})
    if web.get("uri"):
        urls.append((web.get("title", ""), real_url(web["uri"])))
reddit = [u for t, u in urls if "reddit.com" in u or "reddit.com" in t]

print("সার্চ কোয়েরি:", queries)
print("সব সোর্স:", urls)

lines = [
    f"🧪 Search grounding টেস্ট সফল (মডেল: {used})",
    "সার্চ কোয়েরি: " + (" | ".join(queries[:5]) or "(কোনোটা নেই)"),
    f"মোট সোর্স: {len(urls)}, এর মধ্যে Reddit: {len(reddit)}",
]
if errors:
    lines.append("আগে ব্যর্থ: " + ", ".join(errors))
if not chunks:
    lines.append("⚠️ গ্রাউন্ডিং তথ্য আসেনি, মডেল সম্ভবত সার্চই করেনি")
lines += ["", "Reddit লিংক:"]
lines += reddit[:8] or ["(কোনো Reddit লিংক পাওয়া যায়নি)"]
lines += ["", "Gemini-র উত্তর:", text[:1800]]
send("\n".join(lines))
print("পাঠানো হয়েছে")

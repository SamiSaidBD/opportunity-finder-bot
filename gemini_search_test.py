import os
import re
import json
import urllib.request
import urllib.error

GEMINI_KEY = os.environ["GEMINI_API_KEY"]
TG_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TG_CHANNEL = os.environ["TELEGRAM_CHANNEL"]
MODELS = [
    "gemini-flash-lite-latest",
    "gemini-flash-latest",
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
]

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


def post_json(url, body, headers=None):
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=h)
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def send(text):
    post_json(
        f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
        {
            "chat_id": TG_CHANNEL,
            "text": text[:4000],
            "link_preview_options": {"is_disabled": True},
        },
    )


result = None
used = ""
errors = []
for model in MODELS:
    try:
        result = post_json(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            {
                "contents": [{"parts": [{"text": PROMPT}]}],
                "tools": [{"google_search": {}}],
            },
            {"x-goog-api-key": GEMINI_KEY},
        )
        used = model
        break
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            msg = json.loads(body)["error"]["message"][:100]
        except Exception:
            msg = body[:100]
        quota = re.findall(r'"quota(?:Metric|Id|Value)":\s*"([^"]+)"', body)
        errors.append(f"{model}: {e.code} {msg}\n   {' | '.join(quota[:4])}")
        print("ব্যর্থ:", model, e.code)
        print(body[:2000])
    except Exception as e:
        errors.append(f"{model}: {e}")
        print("ব্যর্থ:", model, e)

if result is None:
    send("❌ Search grounding টেস্ট ব্যর্থ\n\n" + "\n\n".join(errors))
    raise SystemExit("সব মডেল ব্যর্থ")

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
    lines.append("আগের ব্যর্থ মডেল: " + ", ".join(e.split(":")[0] for e in errors))
if not chunks:
    lines.append("⚠️ গ্রাউন্ডিং তথ্য আসেনি, মডেল সম্ভবত সার্চই করেনি")
lines += ["", "Reddit লিংক:"]
lines += reddit[:8] or ["(কোনো Reddit লিংক পাওয়া যায়নি)"]
lines += ["", "Gemini-র উত্তর:", text[:1800]]
send("\n".join(lines))
print("পাঠানো হয়েছে")

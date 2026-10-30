import os
import re
import json
import html
import time
import urllib.request
import urllib.error
import urllib.parse

GEMINI_KEY = os.environ["GEMINI_API_KEY"]
TG_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TG_CHANNEL = os.environ["TELEGRAM_CHANNEL"]
MODEL = "gemini-flash-lite-latest"

# প্রতিটি শিরোনামের জন্য ইমোজি
LABELS = {
    "শিরোনাম": "🎯",
    "সমস্যাটি কী": "🧩",
    "কারা সমস্যায় পড়ছে": "👥",
    "বাস্তব প্রমাণ": "🔍",
    "বর্তমান সমাধানের দুর্বলতা": "⚠️",
    "সম্ভাব্য ডিজিটাল সমাধান ও প্রস্তাবিত পণ্য": "💡",
    "প্রাথমিক সংস্করণের ফিচার": "🛠️",
    "টার্গেট গ্রাহক ও আয়ের পদ্ধতি": "💰",
    "প্রতিযোগী ও বিকল্প": "🏁",
    "ঝুঁকি ও চ্যালেঞ্জ": "🚧",
    "কীভাবে যাচাই করব": "✅",
    "Opportunity Score": "📊",
    "প্রমাণের মান": "🧪",
}


def esc(s):
    return html.escape(s, quote=False)


def get_json(url, headers=None, body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, headers=h)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def clean(t, n):
    t = html.unescape(re.sub(r"<[^>]+>", " ", t or ""))
    t = re.sub(r"\s+", " ", t).strip()
    return t[:n]


def comments_of(story_id):
    try:
        item = get_json(f"https://hn.algolia.com/api/v1/items/{story_id}")
    except Exception as e:
        print("কমেন্ট আনা যায়নি:", e)
        return []
    out = []
    for c in item.get("children", [])[:6]:
        t = clean(c.get("text"), 400)
        if t:
            out.append(t)
    return out


def ask_gemini(prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
    out = get_json(
        url,
        headers={"x-goog-api-key": GEMINI_KEY},
        body={"contents": [{"parts": [{"text": prompt}]}]},
    )
    parts = out["candidates"][0]["content"]["parts"]
    return "".join(p.get("text", "") for p in parts).strip()


def to_html(post):
    post = post.replace("*", "").replace("`", "")[:3800]
    lines = []
    for line in post.splitlines():
        line = re.sub(r"^#+\s*", "", line.strip())
        if not line:
            continue
        matched = False
        for label, emoji in LABELS.items():
            m = re.match(rf"^{re.escape(label)}\s*[:：]\s*(.*)$", line)
            if m:
                rest = esc(m.group(1))
                if label == "শিরোনাম":
                    lines.append(f"{emoji} <b>{rest}</b>")
                else:
                    lines.append(f"\n{emoji} <b>{esc(label)}:</b> {rest}".rstrip())
                matched = True
                break
        if not matched:
            lines.append(esc(line))
    return "\n".join(lines).strip()


def send_telegram(text):
    get_json(
        f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
        body={
            "chat_id": TG_CHANNEL,
            "text": text,
            "parse_mode": "HTML",
            "link_preview_options": {"is_disabled": True},
        },
    )


PROMPT = """তুমি একজন স্টার্টআপ গবেষক। নিচে Hacker News-এর একটা আলোচনার তথ্য দেওয়া আছে। শুধু এই তথ্যের ওপর ভিত্তি করে বাংলায় একটা গবেষণা পোস্ট লেখো।

নিয়ম:
- যদি এই আলোচনায় এমন কোনো বাস্তব সমস্যা না থাকে যা সফটওয়্যার, অ্যাপ বা AI দিয়ে সমাধান করে ব্যবসা করা যায়, তাহলে শুধু একটা শব্দ লেখো: NONE
- কোনো সংখ্যা, বাজারের আকার, প্রতিযোগীর নাম বা তথ্য বানিয়ে লিখবে না। নিশ্চিত না হলে লেখো "তথ্য অপর্যাপ্ত, যাচাই প্রয়োজন"।
- প্রমাণ মাত্র একটা আলোচনা থেকে এলে প্রমাণের মান "নিম্ন" বা "মাঝারি" লেখো।
- পুরো লেখা ৩০০০ অক্ষরের মধ্যে রাখো। মার্কডাউন চিহ্ন (*, #, _) ব্যবহার করবে না।

ভাষার ধরন:
- বন্ধুসুলভ কিন্তু পেশাদার সুরে লেখো, যেন একজন অভিজ্ঞ মেন্টর সহজ ভাষায় পরিষ্কারভাবে বোঝাচ্ছেন। উষ্ণ আর আন্তরিক থাকো, কিন্তু আড্ডার মতো হালকা বা ইয়ার্কির ভাষা (যেমন "দোস্ত", "ভাই", "জমজমাট") ব্যবহার করবে না।
- বাক্য ছোট ও স্পষ্ট রাখো। চাইলে একটা সহজ উপমা দিতে পারো, কিন্তু প্রমাণ আর তথ্যের ব্যাপারে কঠোর থাকো, কিছু বানাবে না।
- প্রযুক্তি ও ব্যবসার পরিচিত ইংরেজি শব্দ অনুবাদ না করে ইংরেজিতেই লেখো। যেমন: black box, SaaS, MVP, API, workflow, dashboard, startup, subscription, feedback, automation। যে শব্দ বাংলা করলে অর্থ বদলে যায় বা অদ্ভুত শোনায়, সেটাও ইংরেজিতেই রাখো।
- ইমোজি খুব কম ব্যবহার করো, পুরো পোস্টে সর্বোচ্চ ২টা। নিচের শিরোনামগুলোর আগে ইমোজি দিতে হবে না, সেটা আমরা নিজেই বসাই।
- ফিচারগুলো আলাদা লাইনে "• " দিয়ে শুরু করে লেখো।

পোস্টের কাঠামো (প্রতিটি শিরোনাম হুবহু এই নামে, নতুন লাইনে, শেষে কোলন দিয়ে):
শিরোনাম: (এক বাক্যে সমস্যা, আকর্ষণীয়ভাবে)
সমস্যাটি কী:
কারা সমস্যায় পড়ছে:
বাস্তব প্রমাণ: (আলোচনার সারাংশ, কমেন্টে মানুষ কী বলেছে)
বর্তমান সমাধানের দুর্বলতা:
সম্ভাব্য ডিজিটাল সমাধান ও প্রস্তাবিত পণ্য:
প্রাথমিক সংস্করণের ফিচার: (৩–৫টি)
টার্গেট গ্রাহক ও আয়ের পদ্ধতি:
প্রতিযোগী ও বিকল্প:
ঝুঁকি ও চ্যালেঞ্জ:
কীভাবে যাচাই করব: (বড় বিনিয়োগের আগে বাস্তব পদক্ষেপ)
Opportunity Score: (১০০-এর মধ্যে, এক লাইনে কারণসহ)
প্রমাণের মান: (উচ্চ/মাঝারি/নিম্ন, কারণসহ)

আলোচনার তথ্য:
শিরোনাম: {title}
তারিখ: {date}
পয়েন্ট: {points}, কমেন্ট: {ncom}
বিবরণ: {body}
কিছু কমেন্ট:
{comments}
"""

# ১. Hacker News থেকে সাম্প্রতিক আলোচনা খোঁজা
queries = [
    "frustrated with",
    "is there a tool",
    "how do you deal with",
    "wish there was",
    "struggling with",
    "pain point",
]
since = int(time.time()) - 14 * 24 * 3600
found = {}
for q in queries:
    params = urllib.parse.urlencode({
        "query": q,
        "tags": "ask_hn",
        "hitsPerPage": 20,
        "numericFilters": f"created_at_i>{since},num_comments>=8",
    })
    try:
        for hit in get_json("https://hn.algolia.com/api/v1/search?" + params).get("hits", []):
            found[hit["objectID"]] = hit
    except Exception as e:
        print("HN থেকে আনা ব্যর্থ:", q, e)

# ২. সবচেয়ে আলোচিত ৩টা বাছাই
cands = sorted(
    found.values(),
    key=lambda h: (h.get("points") or 0) + 2 * (h.get("num_comments") or 0),
    reverse=True,
)[:3]
print("প্রার্থী:", [c.get("title") for c in cands])
if not cands:
    raise SystemExit("কোনো আলোচনা পাওয়া যায়নি")

# ৩. Gemini দিয়ে পোস্ট লেখানো
for c in cands:
    prompt = PROMPT.format(
        title=c.get("title"),
        date=(c.get("created_at") or "")[:10],
        points=c.get("points"),
        ncom=c.get("num_comments"),
        body=clean(c.get("story_text"), 1500) or "(কোনো বিবরণ নেই)",
        comments="\n".join("- " + t for t in comments_of(c["objectID"])),
    )
    try:
        post = ask_gemini(prompt)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"Gemini ব্যর্থ: {e.code} {e.read().decode('utf-8')[:300]}")
    if post.strip().upper().startswith("NONE"):
        print("উপযুক্ত নয়, পরেরটা:", c.get("title"))
        continue
    link = f"https://news.ycombinator.com/item?id={c['objectID']}"
    try:
        send_telegram(to_html(post) + "\n\n🔗 <b>মূল সোর্স:</b> " + esc(link))
    except urllib.error.HTTPError as e:
        raise SystemExit(f"টেলিগ্রাম ব্যর্থ: {e.code} {e.read().decode('utf-8')[:300]}")
    print("পোস্ট হয়েছে:", c.get("title"))
    break
else:
    print("তিনটার কোনোটাই উপযুক্ত মনে হয়নি, কিছু পোস্ট হয়নি")

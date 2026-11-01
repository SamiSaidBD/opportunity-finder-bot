import os
import re
import sys
import json
import html
import time
import urllib.request
import urllib.error
import urllib.parse

PROVIDER = os.environ.get("LLM_PROVIDER", "groq")
GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-flash-lite-latest"
TG_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TG_CHANNEL = os.environ["TELEGRAM_CHANNEL"]
RECORD_FILE = "data/posted.json"

if PROVIDER == "groq" and not GROQ_KEY:
    raise SystemExit("GROQ_API_KEY সেট করা নেই")

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

# সিকিউরিটি/exploit ধরনের আলোচনা বাদ
BLOCK = re.compile(
    r"\b(rce|cve(?:-\d+)*s?|exploits?|zero-?days?|0-?days?|malware|ransomware|"
    r"vulnerabilit(?:y|ies)|ddos|backdoors?|embargo)\b",
    re.I,
)


def esc(s):
    return html.escape(s, quote=False)


def load_records():
    try:
        with open(RECORD_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_records(rec):
    os.makedirs("data", exist_ok=True)
    with open(RECORD_FILE, "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, indent=1)


def get_json(url, headers=None, body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    h = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (compatible; opportunity-bot/1.0)",
    }
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, headers=h)
    with urllib.request.urlopen(req, timeout=90) as r:
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
    for c in item.get("children", [])[:5]:
        t = clean(c.get("text"), 350)
        if t:
            out.append(t)
    return out


def ask_gemini(prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    out = get_json(
        url,
        headers={"x-goog-api-key": GEMINI_KEY},
        body={"contents": [{"parts": [{"text": prompt}]}]},
    )
    parts = out["candidates"][0]["content"]["parts"]
    return "".join(p.get("text", "") for p in parts).strip()


def ask_groq(prompt):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_KEY}"}
    body = {
        "model": GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_completion_tokens": 3000,
        "reasoning_effort": "low",
    }
    try:
        out = get_json(url, headers=headers, body=body)
    except urllib.error.HTTPError as e:
        if e.code == 400:
            body.pop("reasoning_effort")
            out = get_json(url, headers=headers, body=body)
        else:
            raise
    return (out["choices"][0]["message"].get("content") or "").strip()


def ask_llm(prompt):
    if PROVIDER == "gemini":
        return ask_gemini(prompt)
    for attempt in range(2):
        try:
            return ask_groq(prompt)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and attempt == 0:
                print("সাময়িক সমস্যা, ২৫ সেকেন্ড অপেক্ষা:", e.code)
                time.sleep(25)
                continue
            raise


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


PROMPT = """You are a startup researcher. Below is information about one Hacker News discussion. Write ONE research post in Bengali, based ONLY on this information.

Rules:
- If the discussion does not contain a real problem that could be solved with software, an app or AI and turned into a business, reply with only one word: NONE
- Never invent numbers, market sizes, competitor names or facts. If you are not sure, write "তথ্য অপর্যাপ্ত, যাচাই প্রয়োজন".
- If the evidence comes from only one discussion, rate the evidence quality "নিম্ন" or "মাঝারি".
- Keep the whole post under 3000 characters. Do not use markdown symbols (*, #, _).

Language style (the post must be in Bengali):
- Friendly but professional, like a smart, experienced friend explaining things clearly in simple language. Warm and sincere, but organized and professional.
- Use very simple Bengali: short sentences, everyday words. Avoid hard words and a stiff word-for-word translation feel.
- Use 1-2 clever jokes or simple analogies in the whole post so it is fun to read. No slang such as "দোস্ত", "ভাই", "জমজমাট" and no over-the-top tone.
- Be strict about evidence and facts, invent nothing.
- Keep well-known English tech and business words in English, do not translate them: black box, SaaS, MVP, API, workflow, dashboard, startup, subscription, feedback, automation. Also keep any word in English if its Bengali translation would change the meaning or sound odd.
- Use very few emojis: at most 2 in the whole post. Do not put emojis before the section titles (we add those ourselves).
- Write the features on separate lines starting with "• ".

Post structure (each section title exactly as written below, on a new line, ending with a colon):
শিরোনাম: (one sentence stating the problem, in an engaging way)
সমস্যাটি কী:
কারা সমস্যায় পড়ছে:
বাস্তব প্রমাণ: (summary of the discussion and what people said in the comments)
বর্তমান সমাধানের দুর্বলতা:
সম্ভাব্য ডিজিটাল সমাধান ও প্রস্তাবিত পণ্য:
প্রাথমিক সংস্করণের ফিচার: (3 to 5 features)
টার্গেট গ্রাহক ও আয়ের পদ্ধতি:
প্রতিযোগী ও বিকল্প:
ঝুঁকি ও চ্যালেঞ্জ:
কীভাবে যাচাই করব: (real steps to validate before a big investment)
Opportunity Score: (out of 100, one line with the reason)
প্রমাণের মান: (উচ্চ/মাঝারি/নিম্ন, with the reason)

Discussion information:
Title: {title}
Date: {date}
Points: {points}, comments: {ncom}
Description: {body}
Some comments:
{comments}
"""

records = load_records()
today = time.strftime("%Y-%m-%d", time.gmtime())

# ১. Hacker News থেকে সাম্প্রতিক আলোচনা খোঁজা
queries = [
    "frustrated with",
    "is there a tool",
    "how do you deal with",
    "wish there was",
    "struggling with",
    "pain point",
]
since = int(time.time()) - 30 * 24 * 3600
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

if not found:
    raise SystemExit("HN থেকে কোনো আলোচনা পাওয়া যায়নি")

# ২. আগে দেখা আর সিকিউরিটি-ধরনের আলোচনা বাদ দিয়ে সেরা ৩টা বাছাই
fresh = []
for h in found.values():
    oid = h["objectID"]
    if oid in records:
        continue
    if BLOCK.search(h.get("title") or ""):
        records[oid] = {"title": h.get("title"), "date": today, "status": "skipped"}
        continue
    fresh.append(h)
save_records(records)

cands = sorted(
    fresh,
    key=lambda h: (h.get("points") or 0) + 2 * (h.get("num_comments") or 0),
    reverse=True,
)[:3]
print("প্রার্থী:", [c.get("title") for c in cands])
if not cands:
    print("নতুন কোনো আলোচনা নেই, এবার পোস্ট হয়নি")
    sys.exit(0)

# ৩. AI দিয়ে পোস্ট লেখানো
for c in cands:
    oid = c["objectID"]
    prompt = PROMPT.format(
        title=c.get("title"),
        date=(c.get("created_at") or "")[:10],
        points=c.get("points"),
        ncom=c.get("num_comments"),
        body=clean(c.get("story_text"), 1200) or "(no description)",
        comments="\n".join("- " + t for t in comments_of(oid)),
    )
    try:
        post = ask_llm(prompt)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"AI ব্যর্থ: {e.code} {e.read().decode('utf-8')[:300]}")
    if post.strip().upper().startswith("NONE"):
        print("উপযুক্ত নয়, পরেরটা:", c.get("title"))
        records[oid] = {"title": c.get("title"), "date": today, "status": "skipped"}
        save_records(records)
        continue
    link = f"https://news.ycombinator.com/item?id={oid}"
    try:
        send_telegram(to_html(post) + "\n\n🔗 <b>মূল সোর্স:</b> " + esc(link))
    except urllib.error.HTTPError as e:
        raise SystemExit(f"টেলিগ্রাম ব্যর্থ: {e.code} {e.read().decode('utf-8')[:300]}")
    records[oid] = {"title": c.get("title"), "date": today, "status": "posted"}
    save_records(records)
    print("পোস্ট হয়েছে:", c.get("title"))
    break
else:
    print("তিনটার কোনোটাই উপযুক্ত মনে হয়নি, কিছু পোস্ট হয়নি")

import os, json, requests
from bs4 import BeautifulSoup

TOKEN = os.environ["TG_TOKEN"]
CHAT_ID = os.environ["TG_CHAT_ID"]
URL = "https://kman.kyiv.ua/ua/Poperedni-reziltati-2026-2027"
SEEN_FILE = "kman_seen.json"

def send(text):
    requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                  data={"chat_id": CHAT_ID, "text": text}, timeout=20)

def get_titles():
    r = requests.get(URL, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    text = BeautifulSoup(r.text, "html.parser").get_text("\n")
    return {" ".join(l.split()) for l in text.split("\n")
            if "попередні результати" in l.lower() and len(l.strip()) > 25}

titles = get_titles()

if not os.path.exists(SEEN_FILE):
    json.dump(sorted(titles), open(SEEN_FILE, "w", encoding="utf-8"), ensure_ascii=False)
    send(f"Моніторинг КМАН запущено. Зараз на сторінці {len(titles)} записів.")
    raise SystemExit

seen = set(json.load(open(SEEN_FILE, encoding="utf-8")))
new = titles - seen
for t in new:
    if "фізик" in t.lower():
        send(f"🔥 ФІЗИКА! {t}\n{URL}")
    else:
        send(f"Нові попередні результати: {t}\n{URL}")
if new:
    json.dump(sorted(seen | new), open(SEEN_FILE, "w", encoding="utf-8"), ensure_ascii=False)

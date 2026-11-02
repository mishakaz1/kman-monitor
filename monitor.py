import os, json, requests
from bs4 import BeautifulSoup

TOKEN = os.environ["TG_TOKEN"]
OWNER = os.environ.get("TG_CHAT_ID", "").strip()
URL = "https://kman.kyiv.ua/ua/Poperedni-reziltati-2026-2027"
STATE_FILE = "kman_seen.json"
API = f"https://api.telegram.org/bot{TOKEN}"


def send(chat, text):
    try:
        r = requests.post(f"{API}/sendMessage",
                          data={"chat_id": chat, "text": text}, timeout=20)
        return r.status_code
    except requests.RequestException:
        return 0


def broadcast(text, subs):
    for c in sorted(subs):
        if send(c, text) == 403:  # людина заблокувала бота
            subs.discard(c)


def get_titles():
    r = requests.get(URL, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    print("KMAN:", r.status_code, len(r.text), "bytes")
    r.raise_for_status()
    text = BeautifulSoup(r.text, "html.parser").get_text("\n")
    titles = {" ".join(l.split()) for l in text.split("\n")
              if "попередні результати" in l.lower() and len(l.strip()) > 25}
    print("KMAN: знайдено записів:", len(titles))
    if not titles:
        print(r.text[:500])
        raise RuntimeError("на сторінці не знайдено жодного запису")
    return titles


state = None
if os.path.exists(STATE_FILE):
    state = json.load(open(STATE_FILE, encoding="utf-8"))
    if isinstance(state, list):
        state = {"seen": state}
state = state or {}
first_run = not state.get("initialized")
seen = set(state.get("seen", []))
subs = set(state.get("subs", []))
offset = state.get("offset", 0)
if OWNER:
    subs.add(OWNER)

# Нові підписники: усі, хто написав боту (наприклад, натиснув Start)
try:
    resp = requests.get(f"{API}/getUpdates",
                        params={"offset": offset, "timeout": 0}, timeout=30).json()
    print("Telegram:", resp.get("ok"), resp.get("description", ""),
          "оновлень:", len(resp.get("result", [])))
    updates = resp.get("result", [])
except requests.RequestException as e:
    print("Telegram недоступний:", e)
    updates = []
for u in updates:
    offset = u["update_id"] + 1
    chat = (u.get("message") or {}).get("chat", {})
    cid = str(chat.get("id", ""))
    if cid and chat.get("type") == "private" and cid not in subs:
        subs.add(cid)
        send(cid, "Підписано. Напишу, коли на КМАН з'являться нові попередні результати.")

try:
    titles = get_titles()
except Exception as e:
    print("Не вдалося прочитати сторінку:", e)
    titles = None

if titles is not None:
    if first_run:
        seen = titles
        state["initialized"] = True
        broadcast(f"Моніторинг КМАН запущено. Зараз на сторінці {len(titles)} записів.", subs)
    else:
        new = titles - seen
        for t in sorted(new):
            if "фізик" in t.lower():
                broadcast(f"🔥 ФІЗИКА! {t}\n{URL}", subs)
            else:
                broadcast(f"Нові попередні результати: {t}\n{URL}", subs)
        seen |= new

print("Підписників:", len(subs))
json.dump({"initialized": state.get("initialized", False), "seen": sorted(seen),
           "subs": sorted(subs), "offset": offset},
          open(STATE_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

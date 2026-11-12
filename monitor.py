import os, json, requests
from urllib.parse import urljoin, unquote
from bs4 import BeautifulSoup

TOKEN = os.environ["TG_TOKEN"]
OWNER = os.environ.get("TG_CHAT_ID", "").strip()
URL_PRE = "https://kman.kyiv.ua/ua/Poperedni-reziltati-2026-2027"
URL_FIN = "https://kman.kyiv.ua/ua/Rezultati-Olimpiad-2026-2027"
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


def fetch(url):
    r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    r.encoding = "utf-8"
    print("KMAN:", url, r.status_code, len(r.text), "bytes")
    r.raise_for_status()
    return r.text


def get_pre():
    html = fetch(URL_PRE)
    text = BeautifulSoup(html, "html.parser").get_text("\n")
    titles = {" ".join(l.split()) for l in text.split("\n")
              if "попередні результати" in l.lower() and len(l.strip()) > 25}
    print("Попередні: знайдено записів:", len(titles))
    if not titles:
        print(html[:500])
        raise RuntimeError("на сторінці попередніх не знайдено жодного запису")
    return titles


def get_fin():
    """Остаточні: кожен опублікований файл (/f/...) — окремий запис.
    Повертає {повне посилання: назва}."""
    html = fetch(URL_FIN)
    soup = BeautifulSoup(html, "html.parser")
    items = {}
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.startswith("/f/") and "kman.kyiv.ua/f/" not in href:
            continue
        name = " ".join(a.get_text(" ").split()) or unquote(href.rsplit("/", 1)[-1])
        items[urljoin(URL_FIN, href)] = name
    print("Остаточні: знайдено файлів:", len(items))
    if not items:
        print(html[:500])
        raise RuntimeError("на сторінці остаточних не знайдено жодного файлу")
    return items


# Лише ці предмети (корені слів, щоб ловити «з фізики», «Фізика» тощо)
SUBJECTS = ["біолог", "фізик", "хімі", "математик", "інформатик"]


def norm(*parts):
    return " ".join(unquote(p) for p in parts).lower()


def is_physics(*parts):
    return "фізик" in norm(*parts)


def wanted(*parts):
    s = norm(*parts)
    return any(k in s for k in SUBJECTS)


state = None
if os.path.exists(STATE_FILE):
    state = json.load(open(STATE_FILE, encoding="utf-8"))
    if isinstance(state, list):
        state = {"seen": state}
state = state or {}
seen = set(state.get("seen", []))
seen_fin = set(state.get("seen_fin", []))
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
        send(cid, "Підписано. Напишу, коли на КМАН з'являться нові попередні "
                  "або остаточні результати з біології, фізики, хімії, "
                  "математики чи інформатики.")

# --- Попередні результати ---
try:
    titles = get_pre()
except Exception as e:
    print("Не вдалося прочитати попередні:", e)
    titles = None

if titles is not None:
    if not state.get("initialized"):
        seen = titles
        state["initialized"] = True
        broadcast(f"Моніторинг КМАН запущено. Зараз на сторінці попередніх "
                  f"{len(titles)} записів.", subs)
    else:
        new = titles - seen
        for t in sorted(new):
            if not wanted(t):
                continue
            if is_physics(t):
                broadcast(f"🔥 ФІЗИКА (попередні)! {t}\n{URL_PRE}", subs)
            else:
                broadcast(f"Нові попередні результати: {t}\n{URL_PRE}", subs)
        seen |= new

# --- Остаточні результати ---
try:
    files = get_fin()
except Exception as e:
    print("Не вдалося прочитати остаточні:", e)
    files = None

if files is not None:
    if not state.get("fin_initialized"):
        seen_fin = set(files)
        state["fin_initialized"] = True
        broadcast(f"Тепер слідкую й за остаточними результатами. Зараз на "
                  f"сторінці {len(files)} файлів, фізики ще немає."
                  if not any(is_physics(u, n) for u, n in files.items()) else
                  f"Тепер слідкую й за остаточними результатами. Зараз на "
                  f"сторінці {len(files)} файлів.", subs)
    else:
        for link in sorted(set(files) - seen_fin):
            name = files[link]
            seen_fin.add(link)
            if not wanted(link, name):
                continue
            if is_physics(link, name):
                broadcast(f"🔥🔥 ФІЗИКА — ОСТАТОЧНІ! {name}\n{link}", subs)
            else:
                broadcast(f"Нові остаточні результати: {name}\n{link}", subs)

print("Підписників:", len(subs))
json.dump({"initialized": state.get("initialized", False), "seen": sorted(seen),
           "fin_initialized": state.get("fin_initialized", False),
           "seen_fin": sorted(seen_fin),
           "subs": sorted(subs), "offset": offset},
          open(STATE_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

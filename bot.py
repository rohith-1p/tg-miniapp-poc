"""MediQuick Telegram Mini App bot (long polling, stdlib only). The page is static on GitHub Pages.

  BOT_TOKEN=123:abc WEBAPP_URL=https://rohith-1p.github.io/tg-miniapp-poc/ python3 bot.py
  python3 bot.py test   # self-check
"""
import fcntl
import json
import os
import random
import sys
import threading
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCTS = {p["id"]: p for p in json.load(open(os.path.join(HERE, "products.json")))}
FREE_DELIVERY_FROM, DELIVERY_FEE = 199, 25  # keep in sync with index.html
# seconds after the order: keep in sync with STEPS in index.html (demo time, compressed)
STATUS = [(15, "📦 Order {id} packed at {store}"), (35, "🛵 Order {id} is out for delivery"),
          (75, "✅ Order {id} delivered. Get well soon! 💚")]


def summarize(cart):
    # cart comes from the client: ignore unknown ids/bad qty, price from our own catalog
    lines, items, total = [], {}, 0
    for pid, qty in cart.items():
        p = PRODUCTS.get(pid)
        if not p or not isinstance(qty, int) or not 0 < qty <= 99:
            continue
        lines.append(f"{p['emoji']} {p['name']} × {qty} = ₹{p['price'] * qty}")
        items[pid] = qty
        total += p["price"] * qty
    if total and total < FREE_DELIVERY_FROM:
        lines.append(f"🛵 Delivery = ₹{DELIVERY_FEE}")
        total += DELIVERY_FEE
    return lines, items, total


def log(event):
    print(json.dumps(event, ensure_ascii=False), flush=True)
    with open(os.path.join(HERE, "events.jsonl"), "a") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def call(method, **params):
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{os.environ['BOT_TOKEN']}/{method}",
        json.dumps(params).encode(), {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=60))["result"]


def later(delay, **params):
    t = threading.Timer(delay, lambda: call("sendMessage", **params))
    t.daemon = True
    t.start()


def order(chat, event, data):
    lines, items, total = summarize(data.get("items") if isinstance(data.get("items"), dict) else {})
    if not items:
        return call("sendMessage", chat_id=chat, text="Your cart was empty 🤷")
    oid = f"#MQ{random.randint(1000, 9999)}"
    store = str(data.get("store") or "MediQuick")[:60]
    log({**event, "action": "order", "order_id": oid, "items": items, "total": total, "pay": "gpay",
         "phone": data.get("phone"), "lat": data.get("lat"), "lon": data.get("lon"), "store": store,
         "rx": bool(data.get("rx"))})
    track = f"{os.environ['WEBAPP_URL']}?track={oid[1:]}&t={int(time.time())}&store={urllib.parse.quote(store)}"
    call("sendMessage", chat_id=chat,
         text=f"🧾 Order {oid} confirmed\n\n" + "\n".join(lines) + f"\n\nTotal: ₹{total}\n"
              "💳 Paid via GPay (UPI) · verification pending\n"
              + ("📄 Prescription attached\n" if data.get("rx") else "") + f"🏪 {store}",
         reply_markup={"inline_keyboard": [[{"text": "📍 Track order live", "web_app": {"url": track}}]]})
    for delay, text in STATUS:
        later(delay, chat_id=chat, text=text.format(id=oid, store=store))


def handle(msg):
    chat = msg["chat"]["id"]
    u = msg.get("from", {})
    event = {"ts": msg["date"], "user_id": u.get("id"), "name": u.get("first_name"),
             "username": u.get("username"), "lang": u.get("language_code")}
    if "web_app_data" in msg:
        try:
            data = json.loads(msg["web_app_data"]["data"])
        except ValueError:
            data = {}
        order(chat, event, data if isinstance(data, dict) else {})
    elif "contact" in msg:
        log({**event, "action": "contact", "phone": msg["contact"].get("phone_number")})
    else:
        log({**event, "action": "message", "text": msg.get("text")})
        call("sendMessage", chat_id=chat,
             text="💊 MediQuick: medicines delivered in minutes.\nTap below to order.",
             reply_markup={"keyboard": [[{"text": "💊 Order medicines", "web_app": {"url": os.environ["WEBAPP_URL"]}}]],
                           "resize_keyboard": True})


def main():
    # one poller per token, or Telegram returns 409 and hands the same update to several copies
    lock = open(os.path.join(HERE, ".bot.lock"), "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        sys.exit("bot.py is already running")
    print("bot polling…")
    offset = 0
    while True:
        try:
            for u in call("getUpdates", offset=offset, timeout=50):
                offset = u["update_id"] + 1
                if "message" in u:
                    handle(u["message"])
        except Exception as e:  # ponytail: log-and-retry loop, no backoff; fine for a demo
            print("error:", e)
            time.sleep(1)


if __name__ == "__main__":
    if sys.argv[1:] == ["test"]:
        lines, items, total = summarize({"dolo650": 2, "thermo": 1, "hack": 5})
        assert items == {"dolo650": 2, "thermo": 1} and total == 315 and len(lines) == 2
        lines, items, total = summarize({"vitc": 1})
        assert total == 25 + DELIVERY_FEE and lines[-1].startswith("🛵")
        assert summarize({"hack": 5, "ors": -3, "bandaid": "9"}) == ([], {}, 0)
        print("ok")
    else:
        main()

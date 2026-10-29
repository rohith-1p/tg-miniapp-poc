"""Telegram Mini App POC bot (long polling, stdlib only). The page is static on GitHub Pages.

  BOT_TOKEN=123:abc WEBAPP_URL=https://rohith-1p.github.io/tg-miniapp-poc/ python3 bot.py
  python3 bot.py test   # self-check
"""
import json
import os
import sys
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCTS = {p["id"]: p for p in json.load(open(os.path.join(HERE, "products.json")))}


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
    if not lines:
        return "Your cart was empty 🤷", items, total
    return "✅ Order received!\n\n" + "\n".join(lines) + f"\n\nTotal: ₹{total}", items, total


def log(event):
    print(json.dumps(event, ensure_ascii=False), flush=True)
    with open(os.path.join(HERE, "events.jsonl"), "a") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def call(method, **params):
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{os.environ['BOT_TOKEN']}/{method}",
        json.dumps(params).encode(), {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=60))["result"]


APP_URL = None  # WEBAPP_URL + ?invoice=<Stars invoice link>, built once at startup


def handle(msg):
    chat = msg["chat"]["id"]
    u = msg.get("from", {})
    event = {"ts": msg["date"], "user_id": u.get("id"), "name": u.get("first_name"),
             "username": u.get("username"), "lang": u.get("language_code")}
    if "web_app_data" in msg:
        try:
            cart = json.loads(msg["web_app_data"]["data"])
        except ValueError:
            cart = {}
        reply, items, total = summarize(cart if isinstance(cart, dict) else {})
        log({**event, "action": "order", "cart": cart, "items": items, "total": total})
        call("sendMessage", chat_id=chat, text=reply)
    elif "successful_payment" in msg:
        sp = msg["successful_payment"]
        try:  # demo: give the Star straight back
            refunded = call("refundStarPayment", user_id=u["id"],
                            telegram_payment_charge_id=sp["telegram_payment_charge_id"])
        except Exception as e:
            print("refund failed:", e)
            refunded = False
        log({**event, "action": "payment", "stars": sp["total_amount"],
             "charge_id": sp["telegram_payment_charge_id"], "refunded": bool(refunded)})
        call("sendMessage", chat_id=chat,
             text="⭐ Payment received!" + (" Refunded, since this is a demo." if refunded else ""))
    elif "contact" in msg:
        log({**event, "action": "contact", "phone": msg["contact"].get("phone_number")})
        call("sendMessage", chat_id=chat, text="📇 Got your contact, thanks!")
    elif "location" in msg:
        loc = msg["location"]
        log({**event, "action": "location", "lat": loc["latitude"], "lon": loc["longitude"]})
        call("sendMessage", chat_id=chat, text=f"📍 Got it: {loc['latitude']:.4f}, {loc['longitude']:.4f}")
    else:
        log({**event, "action": "message", "text": msg.get("text")})
        call("sendMessage", chat_id=chat, text="Tap the button below to open the Mini Café ☕",
             reply_markup={"keyboard": [[{"text": "🛒 Open Mini Café", "web_app": {"url": APP_URL}}],
                                        [{"text": "📍 Share location", "request_location": True}]],
                           "resize_keyboard": True})


def main():
    global APP_URL
    APP_URL = os.environ["WEBAPP_URL"]
    try:
        link = call("createInvoiceLink", title="Mini Café tip", description="Demo payment, refunded automatically",
                    payload="demo-tip", currency="XTR", prices=[{"label": "Tip", "amount": 1}])
        APP_URL += "?invoice=" + urllib.parse.quote(link, safe="")
    except Exception as e:
        print("no Stars invoice:", e)
    print("bot polling…", APP_URL)
    offset = 0
    while True:
        try:
            for u in call("getUpdates", offset=offset, timeout=50):
                offset = u["update_id"] + 1
                if "pre_checkout_query" in u:  # must be answered within 10 s or checkout fails
                    call("answerPreCheckoutQuery", pre_checkout_query_id=u["pre_checkout_query"]["id"], ok=True)
                elif "message" in u:
                    handle(u["message"])
        except Exception as e:  # ponytail: log-and-retry loop, no backoff; fine for a demo
            print("error:", e)


if __name__ == "__main__":
    if sys.argv[1:] == ["test"]:
        text, items, total = summarize({"chai": 2, "dosa": 1, "hack": 5})
        assert text.endswith("Total: ₹170") and items == {"chai": 2, "dosa": 1} and total == 170
        assert summarize({"hack": 5, "chai": -3, "samosa": "9"}) == ("Your cart was empty 🤷", {}, 0)
        print("ok")
    else:
        main()

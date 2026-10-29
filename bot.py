"""Telegram Mini App POC: serves index.html and runs the bot (long polling). Stdlib only.

  BOT_TOKEN=123:abc WEBAPP_URL=https://<tunnel>.trycloudflare.com python3 bot.py
  python3 bot.py test   # self-check
"""
import json
import os
import sys
import threading
import urllib.request
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCTS = {p["id"]: p for p in json.load(open(os.path.join(HERE, "products.json")))}
PORT = int(os.environ.get("PORT", 8080))


def summarize(cart):
    # cart comes from the client: ignore unknown ids/bad qty, price from our own catalog
    lines, total = [], 0
    for pid, qty in cart.items():
        p = PRODUCTS.get(pid)
        if not p or not isinstance(qty, int) or not 0 < qty <= 99:
            continue
        lines.append(f"{p['emoji']} {p['name']} × {qty} = ₹{p['price'] * qty}")
        total += p["price"] * qty
    if not lines:
        return "Your cart was empty 🤷"
    return "✅ Order received!\n\n" + "\n".join(lines) + f"\n\nTotal: ₹{total}"


def call(method, **params):
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{os.environ['BOT_TOKEN']}/{method}",
        json.dumps(params).encode(), {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=60))["result"]


def handle(msg):
    chat = msg["chat"]["id"]
    if "web_app_data" in msg:
        try:
            cart = json.loads(msg["web_app_data"]["data"])
        except ValueError:
            cart = {}
        call("sendMessage", chat_id=chat, text=summarize(cart if isinstance(cart, dict) else {}))
    else:
        call("sendMessage", chat_id=chat, text="Tap the button below to open the Mini Café ☕",
             reply_markup={"keyboard": [[{"text": "🛒 Open Mini Café",
                                          "web_app": {"url": os.environ["WEBAPP_URL"]}}]],
                           "resize_keyboard": True})


def main():
    server = ThreadingHTTPServer(("", PORT), partial(SimpleHTTPRequestHandler, directory=HERE))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"serving on :{PORT}, bot polling…")
    offset = 0
    while True:
        try:
            for u in call("getUpdates", offset=offset, timeout=50):
                offset = u["update_id"] + 1
                if "message" in u:
                    handle(u["message"])
        except Exception as e:  # ponytail: log-and-retry loop, no backoff; fine for a demo
            print("error:", e)


if __name__ == "__main__":
    if sys.argv[1:] == ["test"]:
        assert summarize({"chai": 2, "dosa": 1}).endswith("Total: ₹170")
        assert summarize({"hack": 5, "chai": -3, "samosa": "9"}) == "Your cart was empty 🤷"
        print("ok")
    else:
        main()

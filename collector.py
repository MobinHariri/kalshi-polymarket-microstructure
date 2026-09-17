import json, sqlite3, time, requests
from datetime import datetime, timezone

POLL_SECONDS = 20
DB = "crossvenue.db"
HEADERS = {"User-Agent": "crossvenue-research/0.1"}

with open("pairs.json") as f:
    PAIRS = json.load(f)
print(f"loaded {len(PAIRS)} pairs")

con = sqlite3.connect(DB)
con.execute("PRAGMA journal_mode=WAL")
con.execute("""CREATE TABLE IF NOT EXISTS quotes (
    ts TEXT NOT NULL, venue TEXT NOT NULL, pair_id TEXT NOT NULL,
    best_bid TEXT, best_ask TEXT, bid_size TEXT, ask_size TEXT,
    PRIMARY KEY (ts, venue, pair_id))""")
con.execute("CREATE INDEX IF NOT EXISTS idx_quotes_pair_ts ON quotes(pair_id, ts)")
con.commit()

def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def poll_once():
    ts = now_iso()
    rows = []

    # --- Kalshi: one request covering every pair ---
    by_kalshi = {v["kalshi"]: k for k, v in PAIRS.items()}
    try:
        url = ("https://external-api.kalshi.com/trade-api/v2/markets?tickers="
               + ",".join(by_kalshi.keys()))
        r = requests.get(url, timeout=15, headers=HEADERS)
        for m in r.json()["markets"]:
            pid = by_kalshi.get(m["ticker"])
            if pid:
                rows.append((ts, "kalshi", pid, m["yes_bid_dollars"],
                             m["yes_ask_dollars"], m["yes_bid_size_fp"],
                             m["yes_ask_size_fp"]))
    except Exception as e:
        print(ts, "kalshi failed:", type(e).__name__)

    # --- Polymarket: one request per token ---
    for pid, cfg in PAIRS.items():
        try:
            bk = requests.get("https://clob.polymarket.com/book",
                              params={"token_id": cfg["poly"]},
                              timeout=15, headers=HEADERS).json()
            bids, asks = bk.get("bids", []), bk.get("asks", [])
            bb = max(bids, key=lambda x: float(x["price"])) if bids else None
            ba = min(asks, key=lambda x: float(x["price"])) if asks else None
            rows.append((ts, "poly", pid,
                         bb["price"] if bb else None, ba["price"] if ba else None,
                         bb["size"] if bb else None, ba["size"] if ba else None))
        except Exception as e:
            print(ts, "poly failed", pid, type(e).__name__)

    if rows:
        con.executemany("INSERT OR IGNORE INTO quotes VALUES (?,?,?,?,?,?,?)", rows)
        con.commit()
    return len(rows)

print("collector started", now_iso(), "- ctrl+c to stop")
cycle = 0
while True:
    start = time.time()
    try:
        n = poll_once()
    except Exception as e:
        print("cycle failed:", type(e).__name__)
        n = 0
    cycle += 1
    if cycle == 1 or cycle % 15 == 0:
        total = con.execute("SELECT COUNT(*) FROM quotes").fetchone()[0]
        print(now_iso(), f"cycle {cycle}: {n} rows this cycle, {total} total")
    time.sleep(max(0, POLL_SECONDS - (time.time() - start)))
    
import json, sqlite3, time, requests
from datetime import datetime, timezone

POLL_SECONDS = 20
DEPTH_EVERY  = 3      # capture full book depth every Nth cycle (~60s)
DEPTH_LEVELS = 10     # how many levels per side to store
DB = "crossvenue.db"
HEADERS = {"User-Agent": "crossvenue-research/0.1"}
KALSHI = "https://external-api.kalshi.com/trade-api/v2"

with open("pairs.json") as f:
    PAIRS = json.load(f)
print(f"loaded {len(PAIRS)} pairs")

con = sqlite3.connect(DB)
con.execute("PRAGMA journal_mode=WAL")
con.execute("""CREATE TABLE IF NOT EXISTS quotes (
    ts TEXT NOT NULL, venue TEXT NOT NULL, pair_id TEXT NOT NULL,
    best_bid TEXT, best_ask TEXT, bid_size TEXT, ask_size TEXT,
    PRIMARY KEY (ts, venue, pair_id))""")
con.execute("""CREATE TABLE IF NOT EXISTS books (
    ts TEXT NOT NULL, venue TEXT NOT NULL, pair_id TEXT NOT NULL,
    side TEXT NOT NULL, level INTEGER NOT NULL, price TEXT, size TEXT,
    PRIMARY KEY (ts, venue, pair_id, side, level))""")
con.execute("CREATE INDEX IF NOT EXISTS idx_quotes_pair_ts ON quotes(pair_id, ts)")
con.execute("CREATE INDEX IF NOT EXISTS idx_books_pair_ts  ON books(pair_id, ts)")
con.commit()

def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def kalshi_yes_book(ticker):
    """Both sides on the YES price scale, best first: ([(price,size)], [(price,size)])."""
    r = requests.get(f"{KALSHI}/markets/{ticker}/orderbook",
                     timeout=15, headers=HEADERS).json()
    ob  = r.get("orderbook_fp") or {}
    yes = ob.get("yes_dollars") or []
    no  = ob.get("no_dollars")  or []
    # arrays are ascending, so reversing puts the best price first
    bids = [(p, s) for p, s in reversed(yes)]
    # a NO bid at p is a YES ask at 1-p; highest NO bid = lowest YES ask
    asks = [(f"{1 - float(p):.4f}", s) for p, s in reversed(no)]
    return bids, asks

def poly_book(token):
    bk = requests.get("https://clob.polymarket.com/book",
                      params={"token_id": token}, timeout=15, headers=HEADERS).json()
    bids = sorted(bk.get("bids", []), key=lambda x: float(x["price"]), reverse=True)
    asks = sorted(bk.get("asks", []), key=lambda x: float(x["price"]))
    return ([(b["price"], b["size"]) for b in bids],
            [(a["price"], a["size"]) for a in asks])

def poll_once(capture_depth):
    ts = now_iso()
    qrows, brows = [], []
    by_kalshi = {v["kalshi"]: k for k, v in PAIRS.items()}

    # --- Kalshi top of book: one request covering every pair ---
    try:
        url = f"{KALSHI}/markets?tickers=" + ",".join(by_kalshi.keys())
        for m in requests.get(url, timeout=15, headers=HEADERS).json()["markets"]:
            pid = by_kalshi.get(m["ticker"])
            if pid:
                qrows.append((ts, "kalshi", pid, m["yes_bid_dollars"], m["yes_ask_dollars"],
                              m["yes_bid_size_fp"], m["yes_ask_size_fp"]))
    except Exception as e:
        print(ts, "kalshi quotes failed:", type(e).__name__)

    # --- Kalshi depth: one request per market, depth cycles only ---
    if capture_depth:
        for pid, cfg in PAIRS.items():
            try:
                bids, asks = kalshi_yes_book(cfg["kalshi"])
                for i, (p, s) in enumerate(bids[:DEPTH_LEVELS]):
                    brows.append((ts, "kalshi", pid, "bid", i, p, s))
                for i, (p, s) in enumerate(asks[:DEPTH_LEVELS]):
                    brows.append((ts, "kalshi", pid, "ask", i, p, s))
            except Exception as e:
                print(ts, "kalshi book failed", pid, type(e).__name__)

    # --- Polymarket: one call gives top of book and depth together ---
    for pid, cfg in PAIRS.items():
        try:
            bids, asks = poly_book(cfg["poly"])
            qrows.append((ts, "poly", pid,
                          bids[0][0] if bids else None, asks[0][0] if asks else None,
                          bids[0][1] if bids else None, asks[0][1] if asks else None))
            if capture_depth:
                for i, (p, s) in enumerate(bids[:DEPTH_LEVELS]):
                    brows.append((ts, "poly", pid, "bid", i, p, s))
                for i, (p, s) in enumerate(asks[:DEPTH_LEVELS]):
                    brows.append((ts, "poly", pid, "ask", i, p, s))
        except Exception as e:
            print(ts, "poly failed", pid, type(e).__name__)

    if qrows:
        con.executemany("INSERT OR IGNORE INTO quotes VALUES (?,?,?,?,?,?,?)", qrows)
    if brows:
        con.executemany("INSERT OR IGNORE INTO books  VALUES (?,?,?,?,?,?,?)", brows)
    con.commit()
    return len(qrows), len(brows)

print("collector started", now_iso(), "- ctrl+c to stop")
cycle = 0
while True:
    start = time.time()
    cycle += 1
    capture_depth = (cycle % DEPTH_EVERY == 1)
    try:
        nq, nb = poll_once(capture_depth)
    except Exception as e:
        print("cycle failed:", type(e).__name__)
        nq = nb = 0
    if cycle == 1 or cycle % 15 == 0:
        q = con.execute("SELECT COUNT(*) FROM quotes").fetchone()[0]
        b = con.execute("SELECT COUNT(*) FROM books").fetchone()[0]
        el = time.time() - start
        print(now_iso(), f"cycle {cycle}: +{nq} quotes +{nb} book | "
                         f"{q} quotes, {b} book rows | {el:.1f}s")
    time.sleep(max(0, POLL_SECONDS - (time.time() - start)))

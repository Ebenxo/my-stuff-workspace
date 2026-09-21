"""Crypto paper-trading bot + backtester v2 (standard library only).

Strategy: fast/slow SMA crossover, long-only, stop loss, fees + slippage.
Data: Coinbase public candle API (no API key needed).

    python bot.py backtest --product BTC-USD --days 90
    python bot.py paper    --product BTC-USD

Never places real orders. There is no live-trading code by design.
Checklist references (#n) point to the owner's failure-mode list.
"""
import argparse
import json
import logging
import os
import time
import urllib.request
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

API = "https://api.exchange.coinbase.com/products/{product}/candles"
HERE = Path(__file__).parent
STATE_FILE = HERE / "paper_state.json"
LOG_FILE = HERE / "paper_log.txt"
MIN_TRADES = 30       # below this, results are noise (#53)
MAX_MISSING = 0.05    # refuse data with >5% missing candles (#44, #56)
log = logging.getLogger("bot")


# ---------- data ----------
def _get(url, retries=3):
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "paper-bot/2.0"})
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.load(r)
        except Exception:
            if i == retries - 1:
                raise
            time.sleep(2 ** i)


def fetch_candles(product, granularity, start=None, end=None):
    url = API.format(product=product) + f"?granularity={granularity}"
    if start and end:
        fmt = "%Y-%m-%dT%H:%M:%SZ"  # UTC everywhere (#48)
        url += f"&start={time.strftime(fmt, time.gmtime(start))}&end={time.strftime(fmt, time.gmtime(end))}"
    rows = _get(url)
    return [{"t": c[0], "low": c[1], "high": c[2], "open": c[3], "close": c[4]} for c in rows]


def fetch_history(product, granularity, days):
    end = int(time.time())
    cur, out = end - days * 86400, []
    while cur < end:
        out += fetch_candles(product, granularity, cur, min(cur + granularity * 300, end))
        cur += granularity * 300
        time.sleep(0.4)
    return out


def validate(candles, granularity):
    """Sort, dedupe, sanity-check OHLC, measure gaps. Raises if data is unfit."""
    by_t = {c["t"]: c for c in candles}  # dedupe (#57)
    out, bad = [], 0
    for t in sorted(by_t):
        c = by_t[t]
        ok = (min(c["open"], c["close"], c["low"], c["high"]) > 0
              and c["high"] >= max(c["open"], c["close"], c["low"])
              and c["low"] <= min(c["open"], c["close"], c["high"]))
        if ok:
            out.append(c)
        else:
            bad += 1  # (#45)
    if len(out) < 2:
        raise ValueError("not enough valid candles")
    expected = (out[-1]["t"] - out[0]["t"]) // granularity + 1
    missing = 1 - len(out) / expected
    if missing > MAX_MISSING:
        raise ValueError(f"{missing:.0%} of candles missing; data unfit for testing")
    if missing > 0 or bad:
        log.warning("data: %.1f%% missing candles, %d invalid dropped", missing * 100, bad)
    return out


# ---------- strategy ----------
def sma(values, n):
    return sum(values[-n:]) / n if len(values) >= n else None


def signal(closes, fast, slow):
    """'buy' when fast crosses above slow, 'sell' on the reverse. Closed candles only."""
    if len(closes) < slow + 1:
        return None
    f0, s0 = sma(closes[:-1], fast), sma(closes[:-1], slow)
    f1, s1 = sma(closes, fast), sma(closes, slow)
    if f0 <= s0 and f1 > s1:
        return "buy"
    if f0 >= s0 and f1 < s1:
        return "sell"
    return None


# ---------- portfolio ----------
@dataclass
class Portfolio:
    cash: float = 1000.0
    qty: float = 0.0
    entry: float = 0.0
    fee: float = 0.006      # per side
    peak: float = 0.0
    halted: bool = False
    last_t: int = 0         # last closed candle acted on (#97)
    trades: list = field(default_factory=list)

    def buy(self, price, t):
        if self.qty or self.cash <= 0:
            return
        self.qty = self.cash * (1 - self.fee) / price
        self.entry, self.cash = price, 0.0
        self.trades.append({"t": t, "side": "buy", "price": price})

    def sell(self, price, t, why="signal"):
        if not self.qty:
            return
        self.trades.append({"t": t, "side": "sell", "price": price, "why": why,
                            "pnl_pct": ((price * (1 - self.fee)) / (self.entry / (1 - self.fee)) - 1) * 100})
        self.cash, self.qty = self.qty * price * (1 - self.fee), 0.0

    def equity(self, price):
        return self.cash + self.qty * price * (1 - self.fee)  # net of exit fee (#147)


def stop_fill(entry, stop, o, slip):
    """Stop level, or the open if price gapped through it, minus slippage (#134, #141)."""
    return min(entry * (1 - stop), o) * (1 - slip)


# ---------- backtest ----------
def simulate(candles, a):
    p = Portfolio(cash=a.cash, fee=a.fee, peak=a.cash)
    closes, pending, max_dd = [], None, 0.0
    for c in candles:
        # orders decided on the previous close fill at THIS open (no look-ahead, #32)
        if pending == "buy":
            p.buy(c["open"] * (1 + a.slip), c["t"])
        elif pending == "sell":
            p.sell(c["open"] * (1 - a.slip), c["t"])
        pending = None
        if p.qty and c["low"] <= p.entry * (1 - a.stop):
            p.sell(stop_fill(p.entry, a.stop, c["open"], a.slip), c["t"], "stop")
        closes.append(c["close"])
        eq = p.equity(c["close"])
        p.peak = max(p.peak, eq)
        max_dd = max(max_dd, (p.peak - eq) / p.peak)
        if max_dd >= a.max_dd:  # kill switch
            p.sell(c["close"] * (1 - a.slip), c["t"], "kill")
            p.halted = True
            break
        s = signal(closes, a.fast, a.slow)
        pending = s if (s == "buy" and not p.qty) or (s == "sell" and p.qty) else None
    final = p.equity(closes[-1])
    sells = [t for t in p.trades if t["side"] == "sell"]
    pnls = [t["pnl_pct"] for t in sells]
    gains, losses = sum(x for x in pnls if x > 0), -sum(x for x in pnls if x < 0)
    buy_px = candles[0]["open"] * (1 + a.slip)
    hold = a.cash * (1 - a.fee) / buy_px * candles[-1]["close"] * (1 - a.slip) * (1 - a.fee)
    return {
        "candles": len(candles), "trades": len(sells), "halted": p.halted,
        "ret": (final / a.cash - 1) * 100, "hold": (hold / a.cash - 1) * 100,
        "win": (sum(1 for x in pnls if x > 0) / len(pnls) * 100) if pnls else 0,
        "pf": (gains / losses) if losses else float("inf") if gains else 0,
        "ex_best": sum(pnls) - max(pnls) if pnls else 0, "max_dd": max_dd * 100,
    }


def verdict(r):
    if r["trades"] < MIN_TRADES:
        return f"INCONCLUSIVE: only {r['trades']} trades (need {MIN_TRADES}+). Do not trust these numbers."
    if r["ret"] <= r["hold"]:
        return "NO EDGE: does not beat buy & hold after costs."
    if r["ex_best"] <= 0:
        return "FRAGILE: profit depends on one lucky trade (#23)."
    return "WEAK EVIDENCE ONLY: beat buy & hold here, which is not proof it will continue."


def show(name, r):
    print(f"\n[{name}] {r['candles']} candles, {r['trades']} trades, win rate {r['win']:.0f}%, profit factor {r['pf']:.2f}")
    print(f"  Bot {r['ret']:+.1f}%   Buy&hold {r['hold']:+.1f}%   Max drawdown {r['max_dd']:.1f}%"
          + ("   (KILL SWITCH HIT)" if r["halted"] else ""))
    print(f"  Verdict: {verdict(r)}")


def backtest(candles, a):
    candles = validate(candles, a.granularity)
    cut = int(len(candles) * a.split)
    print(f"{a.product}: {len(candles)} candles, in-sample {cut} / out-of-sample {len(candles) - cut}")
    show("in-sample (tune here)", simulate(candles[:cut], a))
    show("OUT-OF-SAMPLE (judge here, never tune on this)", simulate(candles[cut:], a))
    print("\nOnly one asset and one period were tested. Past results do not predict future results.")


# ---------- paper trading ----------
def load_state(a):
    if STATE_FILE.exists():
        d = json.loads(STATE_FILE.read_text())
        names = {f.name for f in fields(Portfolio)}
        return Portfolio(**{k: v for k, v in d.items() if k in names})
    return Portfolio(cash=a.cash, fee=a.fee, peak=a.cash)


def save_state(p):
    tmp = STATE_FILE.with_suffix(".tmp")  # atomic write (#96, #98)
    tmp.write_text(json.dumps(asdict(p), indent=2))
    os.replace(tmp, STATE_FILE)


def paper_step(p, candles, a, now):
    """One poll. Pure logic, no network or sleep, so it can be tested."""
    g = a.granularity
    closed = [c for c in candles if c["t"] + g <= now]  # drop the forming candle (#68)
    if not closed or now - (closed[-1]["t"] + g) > 3 * g:
        log.warning("STALE DATA: newest closed candle too old; not trading (#171)")
        return
    price = candles[-1]["close"]
    eq = p.equity(price)
    p.peak = max(p.peak, eq)
    if (p.peak - eq) / p.peak >= a.max_dd:
        p.sell(price * (1 - a.slip), now, "kill")
        p.halted = True
        log.error("KILL SWITCH: drawdown limit hit, flat and halted")
        return
    if p.qty and price <= p.entry * (1 - a.stop):
        p.sell(price * (1 - a.slip), now, "stop")
        log.info("STOP  sold @ %.2f", price)
    if closed[-1]["t"] == p.last_t:
        return  # already acted on this candle
    p.last_t = closed[-1]["t"]
    s = signal([c["close"] for c in closed], a.fast, a.slow)
    if s == "buy" and not p.qty:
        p.buy(price * (1 + a.slip), now)
        log.info("BUY   @ %.2f", price)
    elif s == "sell" and p.qty:
        p.sell(price * (1 - a.slip), now)
        log.info("SELL  @ %.2f", price)


def paper(a):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                        handlers=[logging.StreamHandler(), logging.FileHandler(LOG_FILE)])
    p = load_state(a)
    if p.halted:
        log.error("State is halted by kill switch. Review, then delete paper_state.json to reset.")
        return
    log.info("Paper trading %s %d/%d SMA. Ctrl+C to stop.", a.product, a.fast, a.slow)
    while not p.halted:
        try:
            candles = sorted(fetch_candles(a.product, a.granularity), key=lambda c: c["t"])
            paper_step(p, candles, a, int(time.time()))
            save_state(p)
            log.info("equity %.2f %s", p.equity(candles[-1]["close"]), "IN POSITION" if p.qty else "flat")
        except Exception as e:
            log.warning("poll failed: %s", e)
        time.sleep(a.poll)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("mode", choices=["backtest", "paper"])
    ap.add_argument("--product", default="BTC-USD")
    ap.add_argument("--granularity", type=int, default=3600, help="candle seconds: 60,300,900,3600,21600,86400")
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--fast", type=int, default=10)
    ap.add_argument("--slow", type=int, default=30)
    ap.add_argument("--stop", type=float, default=0.03, help="stop loss fraction")
    ap.add_argument("--fee", type=float, default=0.006, help="fee per side")
    ap.add_argument("--slip", type=float, default=0.0005, help="slippage+spread per side")
    ap.add_argument("--max-dd", dest="max_dd", type=float, default=0.15, help="kill switch drawdown")
    ap.add_argument("--split", type=float, default=0.7, help="in-sample fraction")
    ap.add_argument("--cash", type=float, default=1000.0)
    ap.add_argument("--poll", type=int, default=60)
    a = ap.parse_args()
    if a.mode == "backtest":
        logging.basicConfig(level=logging.INFO, format="%(message)s")
        backtest(fetch_history(a.product, a.granularity, a.days), a)
    else:
        paper(a)


if __name__ == "__main__":
    main()

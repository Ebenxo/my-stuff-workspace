import argparse
import random
import tempfile
import unittest
from pathlib import Path

import bot

ARGS = dict(cash=1000, fee=0.006, slip=0.0005, fast=3, slow=8, stop=0.03, max_dd=0.5,
            granularity=3600, split=0.7, product="TEST")


def A(**kw):
    return argparse.Namespace(**{**ARGS, **kw})


def candle(t, o, c=None, lo=None, hi=None):
    c = o if c is None else c
    return {"t": t * 3600, "open": o, "close": c,
            "low": min(o, c) if lo is None else lo, "high": max(o, c) if hi is None else hi}


def walk(n, seed=1, drift=0.0002):
    random.seed(seed)
    p, out = 100.0, []
    for i in range(n):
        o = p
        p *= 1 + random.gauss(drift, 0.01)
        out.append({"t": i * 3600, "open": o, "close": p, "high": max(o, p) * 1.002, "low": min(o, p) * 0.998})
    return out


class Tests(unittest.TestCase):
    def test_signal_crossover(self):
        self.assertEqual(bot.signal([10] * 9 + [20], 3, 8), "buy")
        self.assertEqual(bot.signal([20] * 9 + [10], 3, 8), "sell")
        self.assertIsNone(bot.signal([10] * 5, 3, 8))

    def test_no_lookahead_fill_at_next_open(self):
        # flat then a jump up: signal fires on the jump candle's close, fill must be NEXT open
        cs = [candle(i, 100) for i in range(10)] + [candle(10, 100, 130), candle(11, 131, 131)]
        p_trades = []
        orig = bot.Portfolio.buy
        bot.Portfolio.buy = lambda self, price, t: (p_trades.append((price, t)), orig(self, price, t))[1]
        try:
            bot.simulate(cs, A())
        finally:
            bot.Portfolio.buy = orig
        self.assertEqual(p_trades[0][1], 11 * 3600)
        self.assertAlmostEqual(p_trades[0][0], 131 * 1.0005)

    def test_stop_gap_fills_at_open_not_stop(self):
        self.assertAlmostEqual(bot.stop_fill(100, 0.03, 90, 0), 90)     # gapped through
        self.assertAlmostEqual(bot.stop_fill(100, 0.03, 100, 0), 97)    # normal

    def test_costs_reduce_result(self):
        cs = walk(600)
        free = bot.simulate(cs, A(fee=0, slip=0))["ret"]
        real = bot.simulate(cs, A())["ret"]
        self.assertLess(real, free)

    def test_kill_switch(self):
        cs = [candle(i, 100) for i in range(10)] + [candle(10, 100, 130)] + [candle(11 + i, 130 - i * 10) for i in range(10)]
        r = bot.simulate(cs, A(max_dd=0.05, stop=0.9))
        self.assertTrue(r["halted"])

    def test_validate_rejects_gappy_and_bad_data(self):
        gappy = [candle(i, 100) for i in range(0, 100, 3)]
        with self.assertRaises(ValueError):
            bot.validate(gappy, 3600)
        good = [candle(i, 100) for i in range(50)]
        dup_bad = good + [good[5], {"t": 99999999, "open": 1, "close": 1, "low": 5, "high": 2}]
        self.assertEqual(len(bot.validate(dup_bad, 3600)), 50)

    def test_verdict_small_sample_is_inconclusive(self):
        r = {"trades": 5, "ret": 50, "hold": 0, "ex_best": 10}
        self.assertIn("INCONCLUSIVE", bot.verdict(r))

    def test_paper_ignores_forming_candle_and_stale_data(self):
        g, now = 3600, 100 * 3600 + 1800  # halfway through candle 100
        cs = [candle(i, 100) for i in range(101)]
        cs[-1] = candle(100, 100, 500)  # forming candle spikes: must not trigger a signal
        p = bot.Portfolio()
        bot.paper_step(p, cs, A(), now)
        self.assertEqual(p.trades, [])
        p2 = bot.Portfolio()
        bot.paper_step(p2, cs, A(), now + 10 * g)  # data far too old
        self.assertEqual(p2.last_t, 0)

    def test_paper_acts_once_per_candle(self):
        cs = [candle(i, 100) for i in range(9)] + [candle(9, 100, 130), candle(10, 130)]
        now, p = 10 * 3600 + 60, bot.Portfolio()
        bot.paper_step(p, cs, A(), now)
        bot.paper_step(p, cs, A(), now + 60)
        self.assertEqual(len([t for t in p.trades if t["side"] == "buy"]), 1)

    def test_state_roundtrip_atomic(self):
        with tempfile.TemporaryDirectory() as d:
            bot.STATE_FILE = Path(d) / "s.json"
            p = bot.Portfolio(cash=5, last_t=7)
            bot.save_state(p)
            q = bot.load_state(A())
            self.assertEqual((q.cash, q.last_t), (5, 7))
            self.assertFalse(Path(d, "s.tmp").exists())


if __name__ == "__main__":
    unittest.main()

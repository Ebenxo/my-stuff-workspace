# Crypto paper-trading bot (v2)

Single file, Python standard library only. No API keys, no real orders, no live-trading code.

```
python bot.py backtest --product BTC-USD --days 90
python bot.py paper --product ETH-USD
python -m unittest -v
```

## What it does
- **Strategy:** fast/slow SMA crossover (10/30 hourly), long-only, 3% stop loss.
- **Realistic costs:** 0.6% fee + 0.05% slippage per side; signals fill at the *next* candle's open; stops fill at the open if price gapped through them.
- **Data checks:** dedupes, drops invalid OHLC, refuses data with >5% missing candles.
- **Honest reporting:** in-sample vs out-of-sample split, profit factor, dependence on best trade, and a verdict that says INCONCLUSIVE under 30 trades and NO EDGE if it doesn't beat buy & hold.
- **Paper mode:** acts only on closed candles, once per candle; halts on stale data; writes state atomically; kill switch at 15% drawdown (stays halted until you review and reset).

## Status
- 10 unit tests pass (look-ahead, stop gaps, costs, kill switch, stale data, duplicate candles, state file).
- Not yet run on real market data (build sandbox had no internet). Run the backtest yourself and judge only the out-of-sample line.
- Still open from the failure checklist: single asset/regime, no order-state reconciliation (n/a until live), no alerting, no regime filter.
- Simple SMA crossovers often lose to buy & hold. Do not tune parameters on the out-of-sample segment.

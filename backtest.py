"""
Replication of "Beat the Market: An Effective Intraday Momentum Strategy for S&P500 ETF (SPY)"
(Zarattini, Aziz & Barbon, 2024) on Nasdaq-100 (NQ) and S&P 500 (ES) futures, using 1-minute bars.

The rules are taken from the paper and not tuned:

1. Noise area. For every minute of the day, sigma = the average absolute move from the open
   at that minute over the previous 14 days.
       upper = max(today's open, yesterday's close) * (1 + sigma)
       lower = min(today's open, yesterday's close) * (1 - sigma)
2. Entries are only checked on the half hour (10:00, 10:30, ..., 15:30 New York time).
   Price above the upper band -> long. Below the lower band -> short.
3. Trailing stop, also checked on the half hour: a long exits below max(upper band, VWAP),
   a short exits above min(lower band, VWAP).
4. Always flat at the close.

Signals use the close of the bar that ends on the half hour; the trade is filled at the open of
the next bar. Costs per micro contract: $1.75 commission per round trip and 1 tick slippage per fill.

Usage:
    python backtest.py data/NQ_1min.parquet --symbol NQ
    python backtest.py data/ES_1min.csv --symbol ES

Input: 1-minute OHLCV bars with a timestamp (any timezone), columns open, high, low, close, volume.
"""
import argparse
import os

import numpy as np
import pandas as pd

LOOKBACK = 14                          # days used for the noise area
CHECK_MINUTES = range(30, 361, 30)     # minutes after 09:30 -> 10:00, 10:30, ..., 15:30
TICK = 0.25                            # index points
COMMISSION = 1.75                      # dollars per round trip, per micro contract
POINT_VALUE = {"NQ": 2.0, "ES": 5.0}   # dollars per index point for the micro contracts (MNQ, MES)


def load_bars(path):
    """Read 1-minute bars from a .parquet or .csv file and return them indexed by New York time."""
    if path.endswith(".parquet"):
        df = pd.read_parquet(path)
    else:
        df = pd.read_csv(path, index_col=0)
    df.index = pd.to_datetime(df.index, utc=True).tz_convert("America/New_York")
    df = df[~df.index.duplicated()].sort_index()
    return df[["open", "high", "low", "close", "volume"]]


def split_days(bars):
    """Cut the bars into regular trading sessions (09:30-15:59), one dict of 390 minutes per day.
    Days with fewer than 380 bars (holidays, half days, data gaps) are skipped."""
    rth = bars.between_time("09:30", "15:59")
    days = []
    for date, g in rth.groupby(rth.index.date):
        if len(g) < 380:
            continue
        minute = (g.index.hour * 60 + g.index.minute - 570).to_numpy()   # 0 = 09:30

        def column(name):
            a = np.full(390, np.nan)
            a[minute] = g[name].to_numpy(float)
            return pd.Series(a).ffill().bfill().to_numpy()   # fill the odd missing minute

        close = column("close")
        volume = np.zeros(390)
        volume[minute] = g["volume"].to_numpy(float)
        vwap = np.cumsum(close * volume) / np.maximum(np.cumsum(volume), 1)
        days.append({"date": date, "open": column("open"), "close": close, "vwap": vwap})
    return days


def noise_sigma(days, i):
    """Average absolute move from the open, per minute, over the LOOKBACK days before day i."""
    moves = [np.abs(days[j]["close"] / days[j]["open"][0] - 1) for j in range(i - LOOKBACK, i)]
    return np.mean(moves, axis=0)


def simulate_day(day, prev_close, sigma, point_value):
    """Trade one day with the paper's rules. Returns (profit in dollars, number of entries)."""
    open_price = day["open"][0]
    upper = max(open_price, prev_close) * (1 + sigma)
    lower = min(open_price, prev_close) * (1 - sigma)

    position, entry, profit, entries = 0, 0.0, 0.0, 0

    def close_trade(price):
        return position * (price - entry) * point_value - TICK * point_value - COMMISSION

    for m in CHECK_MINUTES:
        k = m - 1                                   # the bar that ends on the half hour
        price = day["close"][k]

        target = position
        if position == 1 and price < max(upper[k], day["vwap"][k]):
            target = 0                              # trailing stop for a long
        elif position == -1 and price > min(lower[k], day["vwap"][k]):
            target = 0                              # trailing stop for a short
        if price > upper[k]:
            target = 1
        elif price < lower[k]:
            target = -1

        if target != position:
            fill = day["open"][k + 1]               # filled at the next bar's open
            if position != 0:
                profit += close_trade(fill)
            if target != 0:
                entry = fill + target * TICK        # pay one tick on the way in
                entries += 1
            position = target

    if position != 0:                               # flat at the close
        profit += close_trade(day["close"][-1])
    return profit, entries


def backtest(days, point_value):
    rows = []
    for i in range(LOOKBACK + 1, len(days)):
        profit, entries = simulate_day(days[i], days[i - 1]["close"][-1], noise_sigma(days, i), point_value)
        rows.append({"date": days[i]["date"], "pnl": round(profit, 2), "entries": entries})
    return pd.DataFrame(rows)


def summary(pnl):
    """Days, total, average per day, t-statistic of the average, share of winning days, max drawdown."""
    x = pnl.to_numpy(float)
    t_stat = x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))
    equity = np.cumsum(x)
    max_drawdown = (equity - np.maximum.accumulate(equity)).min()
    return len(x), x.sum(), x.mean(), t_stat, (x > 0).mean(), max_drawdown


def money(v, decimals=0):
    return f"{'-' if v < 0 else ''}${abs(v):,.{decimals}f}"


def report(result, symbol):
    lines = [f"# {symbol}: yearly results (1 micro contract, after costs)", "",
             "| Period | Days | Net | Avg/day | t-stat | Winning days | Max drawdown |",
             "|---|---|---|---|---|---|---|"]

    def row(name, pnl):
        n, total, avg, t, win, dd = summary(pnl)
        lines.append(f"| {name} | {n} | {money(total)} | {money(avg, 2)} | {t:.2f} | {win:.0%} | {money(dd)} |")

    dates = pd.to_datetime(result["date"])
    for year, g in result.groupby(dates.dt.year):
        row(str(year), g["pnl"])
    row("**All**", result["pnl"])
    row("Before publication (< Jun 2024)", result.loc[dates < "2024-06-01", "pnl"])
    row("After publication (>= Jun 2024)", result.loc[dates >= "2024-06-01", "pnl"])
    traded = result[result["entries"] > 0]
    lines += ["", f"Days with at least one trade: {len(traded)} of {len(result)}."]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("data", nargs="+", help="one or more 1-minute bar files (.parquet or .csv)")
    parser.add_argument("--symbol", choices=POINT_VALUE, default="NQ")
    parser.add_argument("--out", default="results")
    args = parser.parse_args()

    bars = pd.concat([load_bars(p) for p in args.data])
    bars = bars[~bars.index.duplicated()].sort_index()
    days = split_days(bars)
    result = backtest(days, POINT_VALUE[args.symbol])

    os.makedirs(args.out, exist_ok=True)
    result.to_csv(os.path.join(args.out, f"{args.symbol}_daily.csv"), index=False)
    text = report(result, args.symbol)
    with open(os.path.join(args.out, f"{args.symbol}_yearly.md"), "w") as f:
        f.write(text)
    print(text)


if __name__ == "__main__":
    main()

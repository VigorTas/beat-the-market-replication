"""Small checks of the trading rules on made-up days. Run with:  python test_backtest.py"""
import numpy as np

from backtest import COMMISSION, TICK, simulate_day


def make_day(prices):
    prices = np.asarray(prices, float)
    return {"date": "test", "open": prices.copy(), "close": prices.copy(), "vwap": np.full(390, prices[0])}


def test_quiet_day_has_no_trades():
    day = make_day(np.full(390, 100.0))
    profit, entries = simulate_day(day, prev_close=100.0, sigma=np.full(390, 0.01), point_value=2.0)
    assert entries == 0 and profit == 0


def test_breakout_goes_long_and_holds_to_the_close():
    # Flat at 100 until 09:59, then a jump to 102 that keeps rising slowly. Band = 100 * 1.01 = 101.
    prices = np.r_[np.full(29, 100.0), np.linspace(102, 104, 361)]
    day = make_day(prices)
    profit, entries = simulate_day(day, prev_close=100.0, sigma=np.full(390, 0.01), point_value=2.0)
    assert entries == 1
    entry = prices[30] + TICK                       # signal on the 10:00 close, filled at the next open
    expected = (prices[-1] - entry) * 2.0 - TICK * 2.0 - COMMISSION
    assert abs(profit - expected) < 1e-9


def test_trailing_stop_exits_a_long():
    # Breaks out at 10:00, then falls back below the band and VWAP by 10:30 -> exit, no new trade.
    prices = np.r_[np.full(29, 100.0), np.full(30, 102.0), np.full(331, 100.5)]
    day = make_day(prices)
    profit, entries = simulate_day(day, prev_close=100.0, sigma=np.full(390, 0.01), point_value=2.0)
    assert entries == 1
    expected = (100.5 - (102.0 + TICK)) * 2.0 - TICK * 2.0 - COMMISSION
    assert abs(profit - expected) < 1e-9


if __name__ == "__main__":
    for name, test in list(globals().items()):
        if name.startswith("test_"):
            test()
            print("ok ", name)

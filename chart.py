"""Draw the cumulative profit of every results/<SYMBOL>_daily.csv as one SVG chart (no plotting library needed).

    python chart.py            -> results/equity.svg
"""
import glob
import os

import pandas as pd

W, H = 900, 420
LEFT, RIGHT, TOP, BOTTOM = 70, 20, 40, 40
COLORS = {"NQ": "#1f6feb", "ES": "#d1242f"}
PUBLISHED = pd.Timestamp("2024-06-01")


def dollars(v):
    return f"{'-' if v < 0 else ''}${abs(v):,.0f}"


def main(folder="results"):
    curves = {}
    for path in sorted(glob.glob(os.path.join(folder, "*_daily.csv"))):
        symbol = os.path.basename(path).split("_")[0]
        df = pd.read_csv(path, parse_dates=["date"])
        curves[symbol] = (df["date"], df["pnl"].cumsum())

    start = min(d.min() for d, _ in curves.values())
    end = max(d.max() for d, _ in curves.values())
    low = min(0, min(e.min() for _, e in curves.values()))
    high = max(e.max() for _, e in curves.values())

    def x(date):
        return LEFT + (date - start) / (end - start) * (W - LEFT - RIGHT)

    def y(value):
        return TOP + (high - value) / (high - low) * (H - TOP - BOTTOM)

    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" font-family="sans-serif" font-size="12">',
           f'<rect width="{W}" height="{H}" fill="white"/>',
           f'<text x="{LEFT}" y="22" font-size="15" font-weight="bold">Cumulative profit per micro contract, after costs</text>']

    step = 5000
    for level in range(int(low // step) * step, int(high) + step, step):
        if low <= level <= high:
            svg.append(f'<line x1="{LEFT}" x2="{W - RIGHT}" y1="{y(level):.1f}" y2="{y(level):.1f}" stroke="#e5e5e5"/>')
            svg.append(f'<text x="{LEFT - 8}" y="{y(level) + 4:.1f}" text-anchor="end" fill="#666">{dollars(level)}</text>')
    for year in range(start.year + 1, end.year + 1, 2):
        xx = x(pd.Timestamp(f"{year}-01-01"))
        svg.append(f'<text x="{xx:.1f}" y="{H - BOTTOM + 18}" text-anchor="middle" fill="#666">{year}</text>')

    xp = x(PUBLISHED)
    svg.append(f'<line x1="{xp:.1f}" x2="{xp:.1f}" y1="{TOP}" y2="{H - BOTTOM}" stroke="#999" stroke-dasharray="4 4"/>')
    svg.append(f'<text x="{xp - 6:.1f}" y="{TOP + 12}" text-anchor="end" fill="#666">paper published</text>')

    for i, (symbol, (dates, equity)) in enumerate(curves.items()):
        points = " ".join(f"{x(d):.1f},{y(v):.1f}" for d, v in zip(dates, equity))
        color = COLORS.get(symbol, "#333")
        svg.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="1.5"/>')
        svg.append(f'<text x="{LEFT + 12}" y="{TOP + 16 + 18 * i}" fill="{color}" font-weight="bold">'
                   f'{symbol}: {dollars(equity.iloc[-1])}</text>')

    svg.append("</svg>")
    out = os.path.join(folder, "equity.svg")
    with open(out, "w") as f:
        f.write("\n".join(svg))
    print("wrote", out)


if __name__ == "__main__":
    main()

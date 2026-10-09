from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd
import yfinance as yf


def load_watchlist(path: Path) -> List[str]:
    tickers = []
    for line in path.read_text().splitlines():
        symbol = line.strip().upper()
        if not symbol or symbol.startswith("#"):
            continue
        tickers.append(symbol)
    return list(dict.fromkeys(tickers))


def fetch_prices(tickers: List[str]) -> pd.DataFrame:
    data = yf.download(
        tickers=tickers,
        period="1y",
        interval="1d",
        auto_adjust=False,
        group_by="ticker",
        threads=True,
        progress=False,
    )
    return data


def get_series(data: pd.DataFrame, ticker: str, field: str) -> pd.Series:
    if isinstance(data.columns, pd.MultiIndex):
        if ticker in data.columns.get_level_values(0):
            return data[ticker][field].dropna()
        return pd.Series(dtype=float)
    if field in data.columns and ticker:
        return data[field].dropna()
    return pd.Series(dtype=float)


def first_trading_close_of_year(close_series: pd.Series) -> float:
    current_year = datetime.now().year
    year_data = close_series[close_series.index.year == current_year]
    if year_data.empty:
        return np.nan
    return float(year_data.iloc[0])


def safe_fast_info_value(ticker_obj: yf.Ticker, keys: List[str]):
    try:
        fast_info = ticker_obj.fast_info
        for key in keys:
            value = fast_info.get(key)
            if value is not None:
                return value
    except Exception:
        pass
    return None


def safe_info_value(ticker_obj: yf.Ticker, keys: List[str]):
    try:
        info = ticker_obj.info
        for key in keys:
            value = info.get(key)
            if value is not None:
                return value
    except Exception:
        pass
    return None


def build_rows(tickers: List[str], data: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for ticker in tickers:
        close_series = get_series(data, ticker, "Close")
        if close_series.empty:
            rows.append(
                {
                    "ticker": ticker,
                    "name": ticker,
                    "last_price": np.nan,
                    "price_gt_3": False,
                    "ytd_change_dollar": np.nan,
                    "ytd_gain_dollar": np.nan,
                    "ytd_loss_dollar": np.nan,
                    "sma_200": np.nan,
                    "above_sma_200": False,
                    "yield_pct": np.nan,
                    "status": "No price data",
                }
            )
            continue

        last_price = float(close_series.iloc[-1])
        ytd_start = first_trading_close_of_year(close_series)
        ytd_change = last_price - ytd_start if not np.isnan(ytd_start) else np.nan
        sma_200 = float(close_series.tail(200).mean()) if len(close_series) >= 200 else np.nan

        ticker_obj = yf.Ticker(ticker)
        name = safe_info_value(ticker_obj, ["longName", "shortName"]) or ticker
        dividend_yield = safe_info_value(ticker_obj, ["dividendYield", "yield"]) 
        if dividend_yield is None:
            dividend_yield = safe_fast_info_value(ticker_obj, ["lastPrice"]) and np.nan

        gain = ytd_change if pd.notna(ytd_change) and ytd_change > 0 else 0.0
        loss = abs(ytd_change) if pd.notna(ytd_change) and ytd_change < 0 else 0.0

        rows.append(
            {
                "ticker": ticker,
                "name": name,
                "last_price": last_price,
                "price_gt_3": last_price > 3,
                "ytd_change_dollar": ytd_change,
                "ytd_gain_dollar": gain,
                "ytd_loss_dollar": loss,
                "sma_200": sma_200,
                "above_sma_200": bool(pd.notna(sma_200) and last_price > sma_200),
                "yield_pct": dividend_yield * 100 if isinstance(dividend_yield, (int, float)) else np.nan,
                "status": "OK",
            }
        )

    df = pd.DataFrame(rows)
    return df.sort_values(["price_gt_3", "above_sma_200", "ytd_change_dollar"], ascending=[False, False, False])


def fmt_money(value):
    return "—" if pd.isna(value) else f"${value:,.2f}"


def fmt_pct(value):
    return "—" if pd.isna(value) else f"{value:.2f}%"


def render_html(df: pd.DataFrame, generated_at: str) -> str:
    total = len(df)
    above_3 = int(df["price_gt_3"].fillna(False).sum())
    above_200 = int(df["above_sma_200"].fillna(False).sum())
    avg_ytd = df["ytd_change_dollar"].dropna().mean()

    body_rows = []
    for _, row in df.iterrows():
        price_class = "pass" if row["price_gt_3"] else "fail"
        sma_class = "pass" if row["above_sma_200"] else "fail"
        ytd_class = "pass" if pd.notna(row["ytd_change_dollar"]) and row["ytd_change_dollar"] > 0 else "fail"
        body_rows.append(
            f"""
            <tr>
                <td><strong>{row['ticker']}</strong></td>
                <td>{row['name']}</td>
                <td>{fmt_money(row['last_price'])}</td>
                <td class=\"{price_class}\">{'Yes' if row['price_gt_3'] else 'No'}</td>
                <td class=\"{ytd_class}\">{fmt_money(row['ytd_gain_dollar'])}</td>
                <td>{fmt_money(row['ytd_loss_dollar'])}</td>
                <td>{fmt_money(row['sma_200'])}</td>
                <td class=\"{sma_class}\">{'Above' if row['above_sma_200'] else 'Below'}</td>
                <td>{fmt_pct(row['yield_pct'])}</td>
                <td>{row['status']}</td>
            </tr>
            """
        )

    return f"""
<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>Watchlist Report</title>
  <style>
    :root {{ color-scheme: light dark; }}
    body {{ font-family: Arial, sans-serif; margin: 0; padding: 24px; background:#0b1020; color:#e8ecf3; }}
    .wrap {{ max-width: 1400px; margin: 0 auto; }}
    h1 {{ margin: 0 0 8px; }}
    p {{ color:#b6c0d1; }}
    .cards {{ display:grid; grid-template-columns: repeat(4, minmax(180px, 1fr)); gap:16px; margin:24px 0; }}
    .card {{ background:#151c33; border:1px solid #2a3558; border-radius:12px; padding:16px; }}
    .label {{ font-size:12px; text-transform:uppercase; color:#9fb0cf; letter-spacing:.08em; }}
    .value {{ font-size:28px; margin-top:8px; font-weight:700; }}
    table {{ width:100%; border-collapse:collapse; background:#151c33; border:1px solid #2a3558; border-radius:12px; overflow:hidden; }}
    th, td {{ padding:12px 10px; border-bottom:1px solid #24304f; text-align:left; font-size:14px; }}
    th {{ position:sticky; top:0; background:#11182c; }}
    .pass {{ color:#59d98e; font-weight:600; }}
    .fail {{ color:#ff7b7b; font-weight:600; }}
    @media (max-width: 900px) {{ .cards {{ grid-template-columns: repeat(2, minmax(180px, 1fr)); }} body {{ padding:12px; }} th, td {{ font-size:12px; }} }}
  </style>
</head>
<body>
  <div class=\"wrap\">
    <h1>Daily Watchlist Report</h1>
    <p>Generated {generated_at}</p>
    <div class=\"cards\">
      <div class=\"card\"><div class=\"label\">Total tickers</div><div class=\"value\">{total}</div></div>
      <div class=\"card\"><div class=\"label\">Price above $3</div><div class=\"value\">{above_3}</div></div>
      <div class=\"card\"><div class=\"label\">Above 200 SMA</div><div class=\"value\">{above_200}</div></div>
      <div class=\"card\"><div class=\"label\">Average YTD $ change</div><div class=\"value\">{fmt_money(avg_ytd)}</div></div>
    </div>
    <table>
      <thead>
        <tr>
          <th>Ticker</th>
          <th>Name</th>
          <th>Last Price</th>
          <th>Price &gt; $3</th>
          <th>YTD Gain $</th>
          <th>YTD Loss $</th>
          <th>200 SMA</th>
          <th>Trend</th>
          <th>Yield</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody>
        {''.join(body_rows)}
      </tbody>
    </table>
  </div>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--watchlist", default="watchlist.txt")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    watchlist_path = Path(args.watchlist)
    tickers = load_watchlist(watchlist_path)
    if not tickers:
        raise SystemExit("Watchlist is empty.")

    data = fetch_prices(tickers)
    df = build_rows(tickers, data)

    reports_dir = Path("reports")
    reports_dir.mkdir(exist_ok=True)
    output_path = Path(args.output) if args.output else reports_dir / f"watchlist-report-{datetime.now().strftime('%Y-%m-%d')}.html"
    output_path.write_text(render_html(df, datetime.now().strftime("%Y-%m-%d %H:%M:%S")), encoding="utf-8")
    df.to_csv(reports_dir / f"watchlist-data-{datetime.now().strftime('%Y-%m-%d')}.csv", index=False)


if __name__ == "__main__":
    main()
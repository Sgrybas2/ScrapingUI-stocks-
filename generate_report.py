from __future__ import annotations

import argparse
import os
import smtplib
import ssl
import sys
from datetime import datetime
from email.message import EmailMessage
from getpass import getpass
from pathlib import Path

import pandas as pd
import yfinance as yf

# Replace this placeholder with the Gmail address receiving your report.
REPORT_TO = "silvergymguy35@gmail.com"
BASE_DIR = Path(__file__).resolve().parent


def load_watchlist(path):
    symbols = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        symbol = line.split("#", 1)[0].strip().upper()
        if symbol:
            symbols.append(symbol)
    return list(dict.fromkeys(symbols))


def build_rows(tickers):
    rows = []
    for start in range(0, len(tickers), 25):
        batch = tickers[start:start + 25]
        try:
            data = yf.download(
                batch, period="2y", interval="1d", auto_adjust=False,
                actions=True, group_by="ticker", threads=2, progress=False,
            )
        except Exception:
            data = pd.DataFrame()
        for ticker in batch:
            row = dict(ticker=ticker, name=ticker, currency="Unknown",
                       price_date="", last_price=None, price_gt_3=None,
                       ytd_change_dollar=None, ytd_gain_dollar=None,
                       ytd_loss_dollar=None, sma_200=None,
                       above_sma_200=None, yield_pct=None,
                       status="No price data")
            try:
                prices = data[ticker] if isinstance(data.columns, pd.MultiIndex) else data
                close = pd.to_numeric(prices["Close"], errors="coerce").dropna()
                if close.empty:
                    rows.append(row)
                    continue
                last_date = close.index[-1]
                last = float(close.iloc[-1])
                year = datetime.now().year
                baseline = close[close.index.year < year]
                current = close[close.index.year == year]
                change = last - float(baseline.iloc[-1]) if not baseline.empty and not current.empty else None
                sma = float(close.tail(200).mean()) if len(close) >= 200 else None
                trailing_yield = None
                if "Dividends" in prices:
                    dividends = pd.to_numeric(prices["Dividends"], errors="coerce")
                    cutoff = last_date - pd.DateOffset(years=1)
                    recent = dividends[(dividends.index > cutoff) & (dividends.index <= last_date)]
                    if last > 0 and recent.notna().any():
                        trailing_yield = float(recent.sum()) / last * 100
                row.update(
                    last_price=last, price_date=last_date.strftime("%Y-%m-%d"),
                    price_gt_3=last > 3, ytd_change_dollar=change,
                    ytd_gain_dollar=max(change, 0) if change is not None else None,
                    ytd_loss_dollar=max(-change, 0) if change is not None else None,
                    sma_200=sma, above_sma_200=last > sma if sma is not None else None,
                    yield_pct=trailing_yield,
                    status="OK" if change is not None and sma is not None else "Incomplete history",
                )
                try:
                    info = yf.Ticker(ticker).get_info()
                    row["name"] = info.get("longName") or info.get("shortName") or ticker
                    row["currency"] = info.get("currency") or "Unknown"
                except Exception:
                    pass
            except (KeyError, TypeError, ValueError, IndexError):
                row["status"] = "Unavailable or invalid price data"
            rows.append(row)
    return pd.DataFrame(rows).sort_values("ytd_change_dollar", ascending=False, na_position="last")


def render_text(df):
    columns = {
        "ticker": "Ticker", "currency": "CCY", "last_price": "Price",
        "ytd_gain_dollar": "YTD+", "ytd_loss_dollar": "YTD-",
        "sma_200": "SMA200", "yield_pct": "Yield%",
    }
    table = df[list(columns)].copy().rename(columns=columns)
    for column in ["Price", "YTD+", "YTD-", "SMA200", "Yield%"]:
        table[column] = pd.to_numeric(table[column], errors="coerce").map(
            lambda value: "N/A" if pd.isna(value) else f"{value:.2f}"
        )
    above = pd.to_numeric(df["last_price"], errors="coerce").gt(3).sum()
    return (
        f"DAILY WATCHLIST REPORT\nGenerated: {datetime.now():%Y-%m-%d %H:%M:%S}\n"
        f"Symbols: {len(df)} | Price above 3: {above}\n\n"
        "Latest available daily closes; not guaranteed live prices.\n"
        "Dollar changes are per share in listing currency, not account P&L.\n"
        "YTD compares with the prior year's final close; excludes dividends.\n"
        "Yield% is trailing 12-month cash dividends / latest close.\n"
        "All watchlist rows are included; the >3 rule is a flag, not a filter.\n"
        "Missing values are N/A. See CSV for names, dates and status.\n\n"
        + table.to_string(index=False, max_rows=None, max_cols=None) + "\n"
    )


def email_settings():
    sender = "silvergymguy35@gmail.com"
    password = "hdis gbbq afvq ypnk"
    if not sender or not password:
        raise SystemExit("Sender and App Password are required.")
    return sender, password


def send_email(body, csv_path, settings):
    sender, password = settings
    message = EmailMessage()
    message["Subject"] = f"Daily Watchlist Report - {datetime.now():%Y-%m-%d}"
    message["From"] = sender
    message["To"] = REPORT_TO
    message.set_content(body)
    message.add_attachment(csv_path.read_bytes(), maintype="text", subtype="csv", filename=csv_path.name)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context(), timeout=30) as server:
        server.login(sender, password)
        if server.send_message(message):
            raise RuntimeError("Recipient rejected")


def main():
    parser = argparse.ArgumentParser(description="Save watchlist CSV and email a plain-text table. No HTML.")
    parser.add_argument("--watchlist", default=str(BASE_DIR / "watchlist.txt"))
    parser.add_argument("--output", help="Output CSV path")
    parser.add_argument("--input-csv", help="Use a saved watchlist CSV instead of fetching prices")
    parser.add_argument("--csv-only", action="store_true", help="Save CSV/text without sending email")
    args = parser.parse_args()
    settings = None if args.csv_only else email_settings()
    if args.input_csv:
        df = pd.read_csv(args.input_csv)
        required = {"ticker", "last_price", "ytd_gain_dollar", "ytd_loss_dollar", "sma_200", "yield_pct"}
        missing = required - set(df.columns)
        if missing:
            raise SystemExit("Missing CSV columns: " + ", ".join(sorted(missing)))
        if "currency" not in df:
            df["currency"] = "Unknown"
    else:
        path = Path(args.watchlist)
        if not path.is_file():
            raise SystemExit(f"Watchlist not found: {path}")
        tickers = load_watchlist(path)
        if not tickers:
            raise SystemExit("Watchlist is empty.")
        df = build_rows(tickers)
    if df.empty:
        raise SystemExit("No rows to report.")
    output = Path(args.output) if args.output else BASE_DIR / "reports" / f"watchlist-data-{datetime.now():%Y-%m-%d}.csv"
    if output.suffix.lower() != ".csv":
        raise SystemExit("--output must end in .csv")
    if args.input_csv and output.resolve() == Path(args.input_csv).resolve():
        raise SystemExit("Choose a different --output to avoid overwriting the input CSV.")
    output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output, index=False, encoding="utf-8")
    body = render_text(df)
    output.with_suffix(".txt").write_text(body, encoding="utf-8")
    print(f"Saved CSV and plain-text table: {output.resolve()}")
    if settings:
        try:
            send_email(body, output, settings)
        except (smtplib.SMTPException, OSError, RuntimeError):
            raise SystemExit("Email failed. Files remain saved; check credentials and connection.")
        print(f"Email accepted for delivery to {REPORT_TO}")


if __name__ == "__main__":
    main()
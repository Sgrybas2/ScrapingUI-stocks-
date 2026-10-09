import argparse
from pathlib import Path

import pandas as pd

from generate_report import render_html


def main():
    parser = argparse.ArgumentParser(
        description="Convert a watchlist CSV into a readable HTML report."
    )
    parser.add_argument("csv_file", help="Path to your watchlist CSV")
    parser.add_argument("--output", help="Optional HTML output path")
    args = parser.parse_args()

    source = Path(args.csv_file)
    df = pd.read_csv(source, encoding="utf-8-sig")
    df.columns = df.columns.str.strip()

    numeric_columns = [
        "last_price",
        "ytd_change_dollar",
        "ytd_gain_dollar",
        "ytd_loss_dollar",
        "sma_200",
        "yield_pct",
    ]
    boolean_columns = ["price_gt_3", "above_sma_200"]
    required = ["ticker", "name", "status"] + numeric_columns + boolean_columns

    missing = [column for column in required if column not in df.columns]
    if missing:
        raise SystemExit(f"CSV is missing columns: {', '.join(missing)}")
    if df.empty:
        raise SystemExit("CSV has no data rows.")

    for column in numeric_columns:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    for column in boolean_columns:
        values = df[column].astype("string").str.strip().str.lower()
        parsed = values.map({
            "true": True, "false": False,
            "1": True, "0": False,
            "yes": True, "no": False,
        })
        if parsed.isna().any():
            raise SystemExit(f"Invalid or missing boolean values in {column}")
        df[column] = parsed.astype(bool)

    for column in ["ticker", "name", "status"]:
        df[column] = df[column].fillna("").astype(str).str.strip()

    df = df.sort_values(
        ["price_gt_3", "above_sma_200", "ytd_change_dollar"],
        ascending=[False, False, False],
        na_position="last",
    )

    output = Path(args.output) if args.output else source.with_suffix(".html")
    output.parent.mkdir(parents=True, exist_ok=True)

    html = render_html(df, f"from CSV: {source.name}")
    output.write_text(html, encoding="utf-8")
    print(f"HTML report saved to: {output.resolve()}")


if __name__ == "__main__":
    main()

# ScrapingUI-stocks-
Python shell project that reads creates a list of index of batch large scale-data computes
screening fields, and generates a daily HTML report.

watchlist.txt — one ticker per line
generate_report.py — fetches data and builds the HTML report
requirements.txt — Python dependencies
reports/ — generated HTML reports

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python generate_report.py
Optional arguments:
python generate_report.py --watchlist watchlist.txt --output reports/watchlist-report

One symbol per line:
AAPL
MSFT
NVDA
SPY
QQQ
Lines starting with # are ignored.
# TheCoder Finance App (Local-First)

A private, local-first spending tracker that **auto-fetches** from **Gmail**, **SMS**, and **bank statements**, then shows a **modern web dashboard** with **AI category detection** you can edit.

- Config-driven (JSON/YAML)
- Gmail receipts: Amazon, Flipkart, SBI alerts/statements
- SMS via Android companion/bridge (HTTP JSON)
- PDF/CSV statement parsing
- SQLite database
- NLP categorizer (rules + ML from your past labels)
- Dashboard (Flask + Chart.js) with editable categories
- Auto-refresh background fetcher

## 1) Install

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

## 2) Configure
Edit `config.json` (or `config.yaml`). Example is provided in the repo:
- Put your Gmail **`credentials.json`** next to `config.json`.
- Set `refresh_interval` (seconds), select which fetchers to enable.

## 3) Run
```bash
python main.py --config config.json --open
```
- First run opens a Google OAuth window to grant **read-only Gmail** access.
- The app immediately runs a fetch cycle so the dashboard shows **real data**.
- It keeps fetching every `refresh_interval` seconds in the background.

Dashboard: http://127.0.0.1:5000/

## 4) Editing Categories
- Use the **Category** dropdown in the table to correct AI predictions.
- Your edits are stored as `user_category` and used to retrain the model on next cycles.

## 5) SMS Bridge (optional)
- Set `sms.enabled=true` and provide `sms.android_api_url`.
- The endpoint should return JSON array like:
```json
[
  {"body": "SBI: Rs 4500 debited at AMAZON", "date": "2025-08-10"},
  {"body": "ICICI: Rs 899 spent at FLIPKART", "date": "2025-08-11"}
]
```

## 6) Statements
- Drop PDFs/CSVs into the `statements/` folder (configure path in `config`).
- Parser is generic; tweak your CSV column names if needed.

## 7) Build (Optional)
To package as a single executable with PyInstaller:
```bash
pip install pyinstaller
pyinstaller --name TheCoderFinanceApp --onefile app.py
```
> Tip: For the best experience, ship the whole folder (so templates/static load).

## Notes
- Data stays on your machine unless your SMS bridge is remote.
- Improve parsing by expanding `categories_rules`.
- For advanced bank APIs (Salt/Yodlee), add another fetcher module.

import re, requests, json, yaml
from datetime import datetime
from database import init_db, upsert_transaction

def load_config(path: str) -> dict:
    if path.lower().endswith(".json"):
        return json.load(open(path, "r", encoding="utf-8"))
    else:
        return yaml.safe_load(open(path, "r", encoding="utf-8"))

def parse_sms_text(text: str):
    # Example matches: Rs 4500 debited at AMAZON
    pat = r'(?:₹|INR|Rs\.?)\s*([0-9]+(?:\.[0-9]{1,2})?).{0,40}?(?:at|in)\s+([A-Za-z0-9 &\-\._]{2,64})'
    m = re.search(pat, text, re.IGNORECASE)
    if not m:
        return None
    amount = float(m.group(1))
    merch = m.group(2).strip(' .,-')
    return amount, merch

class SMSFetcher:
    def __init__(self, config_path: str):
        self.cfg = load_config(config_path)
        self.conn = init_db(self.cfg["database"]["path"])

    def run(self) -> int:
        if not self.cfg.get("sms", {}).get("enabled", False):
            return 0
        url = self.cfg["sms"]["android_api_url"]
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            messages = resp.json()  # Expect list of {body:..., date:...}
        except Exception as e:
            print("[SMS] fetch error:", e)
            return 0
        inserted = 0
        for sms in messages:
            body = sms.get("body", "")
            parsed = parse_sms_text(body)
            if not parsed: 
                continue
            amount, merchant = parsed
            date = sms.get("date") or datetime.now().strftime("%Y-%m-%d")
            tx = {
                "date": date[:10],
                "merchant": merchant,
                "category": None,
                "ai_category": None,
                "user_category": None,
                "amount": float(amount),
                "currency": "INR",
                "source": "sms",
                "message_id": None,
                "subject": None,
                "from_email": None,
                "raw_snippet": body[:1000]
            }
            if upsert_transaction(self.conn, tx):
                inserted += 1
        return inserted

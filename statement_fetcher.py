import os, csv, json, yaml
import pdfplumber
from datetime import datetime
from database import init_db, upsert_transaction

def load_config(path: str) -> dict:
    if path.lower().endswith(".json"):
        return json.load(open(path, "r", encoding="utf-8"))
    else:
        return yaml.safe_load(open(path, "r", encoding="utf-8"))

def parse_pdf_lines(file_path: str, password=None):
    txns = []
    try:
        with pdfplumber.open(file_path, password=password) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                for line in text.split("\n"):
                    parts = line.split()
                    if len(parts) >= 3:
                        # naive: first token date-like, last token amount-like
                        date_tok = parts[0]
                        amt_tok = parts[-1].replace(',', '')
                        if len(date_tok) >= 8 and amt_tok.replace('.', '', 1).isdigit():
                            try:
                                amt = float(amt_tok)
                            except:
                                continue
                            merchant = " ".join(parts[1:-1]).strip()
                            # normalize date
                            date = date_tok
                            for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d"):
                                try:
                                    date = datetime.strptime(date_tok, fmt).strftime("%Y-%m-%d")
                                    break
                                except: pass
                            txns.append({
                                "date": date,
                                "merchant": merchant,
                                "amount": amt,
                                "raw": line
                            })
    except Exception as e:
        print("[STATEMENT] PDF parse error:", e)
    return txns

def parse_csv(file_path: str):
    txns = []
    try:
        with open(file_path, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                date = (row.get("Date") or row.get("Txn Date") or row.get("date") or "")[:10]
                merchant = row.get("Description") or row.get("Narration") or row.get("Merchant") or ""
                amt_str = (row.get("Amount") or row.get("Debit") or row.get("Credit") or "0").replace(',', '')
                try:
                    amt = float(amt_str)
                except:
                    continue
                txns.append({"date": date, "merchant": merchant, "amount": amt, "raw": str(row)})
    except Exception as e:
        print("[STATEMENT] CSV parse error:", e)
    return txns

class StatementFetcher:
    def __init__(self, config_path: str):
        self.cfg = load_config(config_path)
        self.conn = init_db(self.cfg["database"]["path"])

    def run(self) -> int:
        if not self.cfg.get("statements", {}).get("enabled", False):
            return 0
        folder = self.cfg["statements"]["folder"]
        password = self.cfg["statements"].get("password")
        inserted = 0
        if not os.path.isdir(folder):
            return 0
        for name in os.listdir(folder):
            path = os.path.join(folder, name)
            txns = []
            if name.lower().endswith(".pdf"):
                txns = parse_pdf_lines(path, password)
            elif name.lower().endswith(".csv"):
                txns = parse_csv(path)
            for t in txns:
                tx = {
                    "date": (t["date"] or datetime.now().strftime("%Y-%m-%d"))[:10],
                    "merchant": t["merchant"] or "Statement Item",
                    "category": None,
                    "ai_category": None,
                    "user_category": None,
                    "amount": float(t["amount"]),
                    "currency": "INR",
                    "source": "statement",
                    "message_id": None,
                    "subject": None,
                    "from_email": None,
                    "raw_snippet": (t.get("raw") or "")[:1000]
                }
                from database import upsert_transaction
                if upsert_transaction(self.conn, tx):
                    inserted += 1
        return inserted

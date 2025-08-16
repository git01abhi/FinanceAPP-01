\
import base64, os, pickle, re
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Dict, Optional
import pytz, yaml, json

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

from database import init_db, upsert_transaction

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

def load_config(path: str) -> dict:
    if path.lower().endswith(".json"):
        return json.load(open(path, "r", encoding="utf-8"))
    else:
        return yaml.safe_load(open(path, "r", encoding="utf-8"))

def decode_payload(payload: dict) -> str:
    def walk(p):
        if "parts" in p:
            return " ".join(walk(pp) for pp in p["parts"])
        data = p.get("body", {}).get("data")
        if not data: return ""
        return base64.urlsafe_b64decode(data.encode("utf-8")).decode("utf-8", errors="ignore")
    return walk(payload)

def to_iso_date(date_header: str) -> str:
    try:
        dt = parsedate_to_datetime(date_header)
        return dt.astimezone(pytz.timezone("Asia/Kolkata")).strftime("%Y-%m-%d")
    except Exception:
        return datetime.now().strftime("%Y-%m-%d")

def extract_amount(text: str) -> Optional[float]:
    txt = text.replace(",", "")
    pats = [
        r"(?:₹|INR|Rs\.?)\s*([0-9]+(?:\.[0-9]{1,2})?)",
        r"([0-9]+(?:\.[0-9]{1,2})?)\s*(?:INR|₹|Rs\.?)"
    ]
    for p in pats:
        m = re.search(p, txt, re.IGNORECASE)
        if m:
            try:
                return float(m.group(1))
            except: pass
    return None

def extract_merchant(text: str, fallback: str) -> str:
    hints = [
        r"at\s+([A-Za-z0-9 &\-\._]+)",
        r"merchant\s*:\s*([A-Za-z0-9 &\-\._]+)",
        r"spent at\s+([A-Za-z0-9 &\-\._]+)"
    ]
    for h in hints:
        m = re.search(h, text, re.IGNORECASE)
        if m:
            name = m.group(1).strip(" .,-")
            if 2 <= len(name) <= 64:
                return name
    mapping = {"amazon": "Amazon.in", "flipkart": "Flipkart", "sbi_txn": "SBI", "sbi_stmt": "SBI Card"}
    return mapping.get(fallback, fallback.title())

class GmailFetcher:
    def __init__(self, config_path: str):
        self.cfg = load_config(config_path)
        self.conn = init_db(self.cfg["database"]["path"])
        self.service = self._auth()

    def _auth(self):
        creds = None
        token_file = self.cfg["gmail"]["token_file"]
        cred_file = self.cfg["gmail"]["credentials_file"]
        if os.path.exists(token_file):
            with open(token_file, "rb") as token:
                creds = pickle.load(token)
        if not creds or not getattr(creds, "valid", False):
            if creds and getattr(creds, "expired", False) and getattr(creds, "refresh_token", None):
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(cred_file, SCOPES)
                creds = flow.run_local_server(port=0)
            with open(token_file, "wb") as token:
                pickle.dump(creds, token)
        return build("gmail", "v1", credentials=creds)

    def run(self) -> int:
        if not self.cfg.get("gmail", {}).get("enabled", False):
            return 0
        total = 0
        user_id = self.cfg["gmail"]["user_id"]
        max_results = self.cfg["gmail"].get("max_results_per_query", 100)
        for source, query in self.cfg["gmail"]["search_queries"].items():
            try:
                results = self.service.users().messages().list(userId=user_id, q=query, maxResults=max_results).execute()
            except HttpError as e:
                print(f"[Gmail] list error {source}: {e}")
                continue
            for m in results.get("messages", []) or []:
                try:
                    msg = self.service.users().messages().get(userId=user_id, id=m["id"], format="full").execute()
                except HttpError as e:
                    print(f"[Gmail] get error {m['id']}: {e}")
                    continue
                headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
                subject = headers.get("subject", "")
                from_email = headers.get("from", "")
                date_iso = to_iso_date(headers.get("date", ""))
                snippet = msg.get("snippet", "") or ""
                body = decode_payload(msg.get("payload", {}))
                full = f"{subject}\n{snippet}\n{body}"
                amount = extract_amount(full) or 0.0
                merchant = extract_merchant(full, source)
                tx = {
                    "date": date_iso,
                    "merchant": merchant,
                    "category": None,
                    "ai_category": None,
                    "user_category": None,
                    "amount": float(amount),
                    "currency": "INR",
                    "source": source,
                    "message_id": msg.get("id"),
                    "subject": subject,
                    "from_email": from_email,
                    "raw_snippet": snippet[:1000]
                }
                if upsert_transaction(self.conn, tx):
                    total += 1
        return total

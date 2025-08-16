import sqlite3, datetime

SCHEMA = '''
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT,                -- ISO YYYY-MM-DD
    merchant TEXT,
    category TEXT,            -- legacy/rule category
    ai_category TEXT,         -- predicted by NLP
    user_category TEXT,       -- user override
    amount REAL,
    currency TEXT DEFAULT 'INR',
    source TEXT,              -- amazon, flipkart, sbi_txn, sms, statement...
    message_id TEXT,          -- unique per Gmail; for others can be NULL
    subject TEXT,
    from_email TEXT,
    raw_snippet TEXT,
    updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_txn_date ON transactions(date);
CREATE INDEX IF NOT EXISTS idx_txn_cat ON transactions(category);
CREATE INDEX IF NOT EXISTS idx_txn_ai_cat ON transactions(ai_category);
CREATE UNIQUE INDEX IF NOT EXISTS ux_transactions_message_id ON transactions(message_id);
'''

def init_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute('PRAGMA journal_mode=WAL;')
    conn.executescript(SCHEMA)
    return conn

def upsert_transaction(conn: sqlite3.Connection, tx: dict) -> bool:
    # If message_id provided, try upsert by message_id; else insert
    now = datetime.datetime.utcnow().isoformat()
    tx.setdefault("updated_at", now)
    cur = conn.cursor()
    if tx.get("message_id"):
        # Try insert ignore
        cur.execute('''
            INSERT OR IGNORE INTO transactions
            (date, merchant, category, ai_category, user_category, amount, currency, source, message_id, subject, from_email, raw_snippet, updated_at)
            VALUES (:date, :merchant, :category, :ai_category, :user_category, :amount, :currency, :source, :message_id, :subject, :from_email, :raw_snippet, :updated_at)
        ''', tx)
        inserted = cur.rowcount == 1
        if not inserted:
            # Update existing minimal fields
            cur.execute('''
                UPDATE transactions
                SET date=:date, merchant=:merchant, category=COALESCE(:category, category),
                    amount=COALESCE(:amount, amount), source=COALESCE(:source, source),
                    subject=COALESCE(:subject, subject), from_email=COALESCE(:from_email, from_email),
                    raw_snippet=COALESCE(:raw_snippet, raw_snippet), updated_at=:updated_at
                WHERE message_id=:message_id
            ''', tx)
        conn.commit()
        return inserted
    else:
        cur.execute('''
            INSERT INTO transactions
            (date, merchant, category, ai_category, user_category, amount, currency, source, message_id, subject, from_email, raw_snippet, updated_at)
            VALUES (:date, :merchant, :category, :ai_category, :user_category, :amount, :currency, :source, :message_id, :subject, :from_email, :raw_snippet, :updated_at)
        ''', tx)
        conn.commit()
        return True

def update_user_category(conn: sqlite3.Connection, tx_id: int, new_cat: str):
    now = datetime.datetime.utcnow().isoformat()
    cur = conn.cursor()
    cur.execute('UPDATE transactions SET user_category=?, updated_at=? WHERE id=?', (new_cat, now, tx_id))
    conn.commit()

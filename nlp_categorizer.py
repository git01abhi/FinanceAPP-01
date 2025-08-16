import json, yaml, sqlite3
from typing import List, Tuple
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import Pipeline

def load_config(path: str) -> dict:
    if path.lower().endswith('.json'):
        return json.load(open(path, 'r', encoding='utf-8'))
    else:
        return yaml.safe_load(open(path, 'r', encoding='utf-8'))

def rule_category(merchant: str, cfg: dict) -> str:
    low = (merchant or '').lower()
    for cat, keys in cfg.get('categories_rules', {}).items():
        for k in keys:
            if k.lower() in low:
                return cat
    return ''

def train_and_predict(conn: sqlite3.Connection, cfg: dict) -> int:
    cur = conn.cursor()
    # Training data: rows where user_category or category is present
    cur.execute("""        SELECT id, COALESCE(user_category, category), merchant||' '||IFNULL(subject,'')||' '||IFNULL(raw_snippet,'') 
        FROM transactions 
        WHERE COALESCE(user_category, category) IS NOT NULL
              AND TRIM(COALESCE(user_category, category)) <> ''
    """)
    rows = cur.fetchall()
    if not rows:
        return 0
    y = [r[1] for r in rows]
    X = [r[2] for r in rows]
    model: Pipeline = Pipeline([('tfidf', TfidfVectorizer(max_features=5000)), ('nb', MultinomialNB())])
    try:
        model.fit(X, y)
    except Exception:
        return 0

    # Predict for items missing ai_category and user_category
    cur.execute("""        SELECT id, merchant||' '||IFNULL(subject,'')||' '||IFNULL(raw_snippet,'') FROM transactions
        WHERE (ai_category IS NULL OR ai_category='') 
          AND (user_category IS NULL OR user_category='')
    """)
    targets = cur.fetchall()
    updated = 0
    for tid, text in targets:
        pred = model.predict([text])[0]
        cur.execute('UPDATE transactions SET ai_category=? WHERE id=?', (pred, tid))
        updated += 1
    conn.commit()
    return updated

def apply_rules(conn: sqlite3.Connection, cfg: dict) -> int:
    cur = conn.cursor()
    # Only set category if empty and rules match
    cur.execute("SELECT id, merchant FROM transactions WHERE category IS NULL OR TRIM(category)='' ")
    updated = 0
    for tid, merchant in cur.fetchall():
        cat = rule_category(merchant or '', cfg)
        if cat:
            cur.execute('UPDATE transactions SET category=? WHERE id=?', (cat, tid))
            updated += 1
    conn.commit()
    return updated

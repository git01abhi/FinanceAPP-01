import os, threading, time, json, yaml, sqlite3
from flask import Flask, render_template, jsonify, request
from database import init_db, update_user_category
from fetchers.gmail_fetcher import GmailFetcher
from fetchers.sms_fetcher import SMSFetcher
from fetchers.statement_fetcher import StatementFetcher
from nlp_categorizer import train_and_predict, apply_rules

def load_config(path: str) -> dict:
    if path.lower().endswith('.json'):
        return json.load(open(path, 'r', encoding='utf-8'))
    else:
        return yaml.safe_load(open(path, 'r', encoding='utf-8'))

CONFIG_PATH = os.environ.get('TC_CONFIG', 'config.json')
cfg = load_config(CONFIG_PATH)
DB_PATH = cfg['database']['path']
conn = init_db(DB_PATH)

app = Flask(__name__)

def run_fetch_cycle():
    if cfg.get('gmail', {}).get('enabled', False):
        try:
            inserted = GmailFetcher(CONFIG_PATH).run()
            print(f'[Fetch] Gmail inserted: {inserted}')
        except Exception as e:
            print('[Fetch] Gmail error:', e)
    if cfg.get('sms', {}).get('enabled', False):
        try:
            inserted = SMSFetcher(CONFIG_PATH).run()
            print(f'[Fetch] SMS inserted: {inserted}')
        except Exception as e:
            print('[Fetch] SMS error:', e)
    if cfg.get('statements', {}).get('enabled', False):
        try:
            inserted = StatementFetcher(CONFIG_PATH).run()
            print(f'[Fetch] Statements inserted: {inserted}')
        except Exception as e:
            print('[Fetch] Statements error:', e)
    # Rules first, then ML
    try:
        r = apply_rules(conn, cfg)
        m = train_and_predict(conn, cfg)
        print(f'[Categorizer] Rules set: {r}, ML predicted: {m}')
    except Exception as e:
        print('[Categorizer] error:', e)

def scheduler_loop(interval: int):
    while True:
        run_fetch_cycle()
        time.sleep(max(60, interval))

@app.route('/')
def index():
    return render_template('index.html', app_name=cfg.get('app_name', 'TheCoder Finance'))

@app.route('/api/summary')
def api_summary():
    cur = conn.cursor()
    cur.execute("""        SELECT COALESCE(user_category, ai_category, category, 'Uncategorized') as cat, SUM(amount) 
        FROM transactions
        WHERE amount < 0 OR amount > 0
        GROUP BY cat
        ORDER BY SUM(amount) DESC
    """ )
    cat_rows = cur.fetchall()

    cur.execute("""        SELECT date, SUM(amount) FROM transactions
        GROUP BY date ORDER BY date
    """ )
    trend = cur.fetchall()

    cur.execute("SELECT COUNT(*) FROM transactions" )
    total = cur.fetchone()[0]

    return jsonify({
        "categories": [{"category": c or "Uncategorized", "amount": a} for c,a in cat_rows],
        "trend": [{"date": d, "amount": a} for d,a in trend],
        "total": total
    })

@app.route('/api/transactions')
def api_transactions():
    cur = conn.cursor()
    cur.execute("""        SELECT id, date, merchant, amount,
               COALESCE(user_category, ai_category, category, 'Uncategorized') as category,
               source
        FROM transactions
        ORDER BY date DESC, id DESC LIMIT 500
    """ )
    rows = cur.fetchall()
    tx = [{
        "id": r[0], "date": r[1], "merchant": r[2], "amount": r[3],
        "category": r[4], "source": r[5]
    } for r in rows]
    return jsonify(tx)

@app.route('/api/update_category', methods=['POST'])
def api_update_category():
    data = request.json or {}
    tx_id = data.get('id')
    cat = data.get('category', '').strip()
    if not tx_id or not cat:
        return jsonify({"ok": False, "error": "Missing id/category"}), 400
    update_user_category(conn, int(tx_id), cat)
    return jsonify({"ok": True})

def start_scheduler():
    interval = int(cfg.get('refresh_interval', 300))
    t = threading.Thread(target=scheduler_loop, args=(interval,), daemon=True)
    t.start()

if __name__ == '__main__':
    start_scheduler()
    # Run one immediate cycle so the dashboard shows real data instantly
    run_fetch_cycle()
    app.run(host='127.0.0.1', port=5000, debug=False)

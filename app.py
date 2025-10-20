# app.py
import json
import random
import sqlite3
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify, request, send_file, g
from dateutil.parser import parse as parse_date

DB = "vocab.db"
VOCAB_JSON = "vocab.json"

app = Flask(__name__, static_folder="static", template_folder="templates")

# --- DB helpers ---
def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DB, check_same_thread=False)
        db.row_factory = sqlite3.Row
    return db

def init_db():
    db = get_db()
    db.executescript("""
    CREATE TABLE IF NOT EXISTS word (
        id INTEGER PRIMARY KEY,
        fr TEXT NOT NULL,
        nl TEXT NOT NULL,
        bucket TEXT DEFAULT 'Unknown', -- Known, Fuzzy, Unknown
        last_tested TEXT,
        correct_count INTEGER DEFAULT 0,
        total_tests INTEGER DEFAULT 0,
        next_review TEXT
    );
    """)
    db.commit()

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()

def load_vocab_to_db():
    db = get_db()
    with open(VOCAB_JSON, encoding="utf-8") as f:
        pairs = json.load(f)
    cur = db.cursor()
    # insert only if not exists
    for p in pairs:
        cur.execute("SELECT id FROM word WHERE fr = ? AND nl = ?", (p["fr"], p["nl"]))
        if cur.fetchone():
            continue
        cur.execute("""
            INSERT INTO word(fr, nl, bucket, last_tested, correct_count, total_tests, next_review)
            VALUES (?, ?, 'Unknown', NULL, 0, 0, NULL)
        """, (p["fr"], p["nl"]))
    db.commit()

# --- scheduling and buckets ---
def schedule_next(bucket):
    today = datetime.utcnow()
    if bucket == "Unknown":
        return (today + timedelta(days=1)).isoformat()
    elif bucket == "Fuzzy":
        return (today + timedelta(days=3)).isoformat()
    elif bucket == "Known":
        return (today + timedelta(days=7)).isoformat()
    else:
        return None

# --- selection logic ---
def sample_diagnostic(n=10):
    db = get_db()
    rows = db.execute("SELECT * FROM word").fetchall()
    rows = list(rows)
    if not rows:
        return []
    # choose diverse sample: random but try to cover different buckets
    random.shuffle(rows)
    return [dict(r) for r in rows[:min(len(rows), n)]]

def choose_adaptive(n=10):
    db = get_db()
    # prefer Unknown and Fuzzy
    unknowns = [dict(r) for r in db.execute("SELECT * FROM word WHERE bucket='Unknown'").fetchall()]
    fuzzies = [dict(r) for r in db.execute("SELECT * FROM word WHERE bucket='Fuzzy'").fetchall()]
    knowns = [dict(r) for r in db.execute("SELECT * FROM word WHERE bucket='Known'").fetchall()]
    selected = []
    # allocation: 40% Unknown, 40% Fuzzy, 20% Known
    u_n = int(n * 0.4)
    f_n = int(n * 0.4)
    k_n = n - u_n - f_n
    selected.extend(random.sample(unknowns, min(len(unknowns), u_n)))
    selected.extend(random.sample(fuzzies, min(len(fuzzies), f_n)))
    if knowns and k_n>0:
        selected.extend(random.sample(knowns, min(len(knowns), k_n)))
    # fill if shortage
    all_rows = unknowns + fuzzies + knowns
    while len(selected) < min(n, len(all_rows)):
        candidate = random.choice(all_rows)
        if candidate not in selected:
            selected.append(candidate)
    random.shuffle(selected)
    return selected[:n]

# --- routes ---
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/init", methods=["POST"])
def api_init():
    init_db()
    load_vocab_to_db()
    return jsonify({"status":"ok"})

@app.route("/api/diagnostic", methods=["GET"])
def api_diagnostic():
    items = sample_diagnostic(10)
    return jsonify({"items": items})

@app.route("/api/adaptive", methods=["GET"])
def api_adaptive():
    items = choose_adaptive(int(request.args.get("n", 10)))
    return jsonify({"items": items})

@app.route("/api/answer", methods=["POST"])
def api_answer():
    payload = request.json
    wid = payload.get("id")
    given = (payload.get("answer") or "").strip().lower()
    confidence = int(payload.get("confidence", 3))
    direction = payload.get("direction", "fr2nl")  # 'fr2nl' or 'nl2fr'

    db = get_db()
    row = db.execute("SELECT * FROM word WHERE id = ?", (wid,)).fetchone()
    if not row:
        return jsonify({"error":"unknown id"}), 400

    correct_text = row["nl"] if direction == "fr2nl" else row["fr"]
    # simple normalization
    def norm(s):
        return (s or "").strip().lower()

    correct = (norm(given) == norm(correct_text))
    # small tolerance: accept if edit distance small? we'll keep exact for simplicity
    new_total = row["total_tests"] + 1
    new_correct = row["correct_count"] + (1 if correct else 0)

    # update bucket logic:
    bucket = row["bucket"]
    # initial logic: if correct+high confidence => Known, if incorrect => Unknown, else Fuzzy
    if correct and confidence >= 4 and new_correct >= 1:
        new_bucket = "Known"
    elif not correct:
        new_bucket = "Unknown"
    else:
        new_bucket = "Fuzzy"

    next_review = schedule_next(new_bucket)
    now = datetime.utcnow().isoformat()
    db.execute("""
        UPDATE word
        SET bucket = ?, last_tested = ?, correct_count = ?, total_tests = ?, next_review = ?
        WHERE id = ?
    """, (new_bucket, now, new_correct, new_total, next_review, wid))
    db.commit()

    return jsonify({
        "correct": correct,
        "correct_text": correct_text,
        "new_bucket": new_bucket,
        "next_review": next_review
    })

@app.route("/api/progress", methods=["GET"])
def api_progress():
    db = get_db()
    rows = db.execute("SELECT * FROM word ORDER BY bucket DESC").fetchall()
    data = [dict(r) for r in rows]
    totals = {"Known":0,"Fuzzy":0,"Unknown":0}
    for r in data:
        b = r["bucket"]
        totals[b] = totals.get(b,0) + 1
    return jsonify({"rows": data, "totals": totals})

@app.route("/api/export", methods=["GET"])
def api_export():
    db = get_db()
    rows = db.execute("SELECT * FROM word").fetchall()
    csv_lines = ["id,fr,nl,bucket,last_tested,correct_count,total_tests,next_review"]
    for r in rows:
        safe = lambda v: (v or "").replace(",", ";")
        csv_lines.append(",".join([
            str(r["id"]),
            safe(r["fr"]),
            safe(r["nl"]),
            safe(r["bucket"]),
            safe(r["last_tested"]),
            str(r["correct_count"]),
            str(r["total_tests"]),
            safe(r["next_review"])
        ]))
    csv_text = "\n".join(csv_lines)
    return (csv_text, 200, {
        "Content-Type": "text/csv",
        "Content-Disposition": "attachment; filename=vocab_progress.csv"
    })

if __name__ == "__main__":
    with app.app_context():
        init_db()
        try:
            load_vocab_to_db()
        except Exception as e:
            print("Could not load vocab.json — run parse_pdf.py to generate it:", e)
    app.run(debug=True, port=5000)

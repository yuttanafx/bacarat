#!/usr/bin/env python3
"""เซิร์ฟเวอร์ฐานข้อมูลบาคาร่า (API + Webhook) ใช้เฉพาะไลบรารีมาตรฐานของ Python

    python3 server.py                      # http://localhost:8787
    python3 server.py --port 9000 --host 0.0.0.0
    BACC_TOKEN=รหัสลับ python3 server.py   # บังคับใช้โทเคน (แนะนำถ้าเปิดให้คนอื่นเข้าถึง)

เส้นทาง
  GET  /                  หน้าเว็บ index.html (ถ้ามีในโฟลเดอร์แม่)
  GET  /api/health        ตรวจสถานะ (ไม่ต้องใช้โทเคน)
  GET  /api/stats         จำนวนกระดาน/ตา และสัดส่วน B/P/T แยกตามแท็ก
  GET  /api/boards        ดึงกระดาน  ?limit=300&tag=&min_hands=&max_hands=&order=random|latest|oldest&offset=
  GET  /api/boards/<id>   ดึงกระดานเดียว
  POST /hook              รับ webhook จากหน้าเว็บ (board_finished / export_boards / test)

รูปแบบกระดานที่ตอบกลับตรงกับที่ปุ่ม "กู้คืนจากไฟล์สำรอง" ของหน้าเว็บอ่านได้
"""
import argparse, json, os, re, secrets, sqlite3, sys, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("BACC_DB", os.path.join(HERE, "baccarat.db"))
TOKEN = os.environ.get("BACC_TOKEN", "")
MAX_BODY = 5 * 1024 * 1024
MAX_LIMIT = 2000
MAX_HANDS = 5000          # ยาวสุดต่อกระดานที่รับผ่าน webhook
CLEAN = re.compile(r"[^BPT]")
SELECT = "SELECT id, name, tag, at, results FROM shoes"


def db():
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    return con


def to_board(r):
    return {"id": r["id"], "name": r["name"], "tag": r["tag"], "at": r["at"], "results": r["results"]}


def clean_results(v):
    if isinstance(v, list):
        v = "".join(map(str, v))
    return CLEAN.sub("", str(v or "").upper())


def to_int(v, default, lo, hi):
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return default


class Handler(BaseHTTPRequestHandler):
    server_version = "BaccDB/1.0"

    # ---------- helpers ----------
    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (time.strftime("%H:%M:%S"), fmt % args))

    def cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-API-Key, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Max-Age", "600")

    def send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.cors()
        self.end_headers()
        self.wfile.write(body)

    def authorized(self, qs):
        if not TOKEN:
            return True
        got = self.headers.get("X-API-Key", "")
        auth = self.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            got = got or auth[7:].strip()
        got = got or (qs.get("key", [""])[0])
        return secrets.compare_digest(got.encode(), TOKEN.encode())

    # ---------- routes ----------
    def do_OPTIONS(self):
        self.send_response(204)
        self.cors()
        self.end_headers()

    def do_GET(self):
        u = urlparse(self.path)
        qs = parse_qs(u.query)
        path = u.path.rstrip("/") or "/"
        try:
            if path == "/":
                return self.serve_index()
            if path == "/api/health":
                return self.send_json({"ok": True, "auth_required": bool(TOKEN)})
            if not path.startswith("/api/"):
                return self.send_json({"ok": False, "error": "not_found"}, 404)
            if not self.authorized(qs):
                return self.send_json({"ok": False, "error": "unauthorized"}, 401)
            if path == "/api/stats":
                return self.stats()
            if path == "/api/boards":
                return self.boards(qs)
            if path.startswith("/api/boards/"):
                return self.board_one(unquote(path[len("/api/boards/"):]))
            return self.send_json({"ok": False, "error": "not_found"}, 404)
        except sqlite3.Error as e:
            return self.send_json({"ok": False, "error": "db_error", "detail": str(e)}, 500)

    def do_POST(self):
        u = urlparse(self.path)
        qs = parse_qs(u.query)
        if (u.path.rstrip("/") or "/") != "/hook":
            return self.send_json({"ok": False, "error": "not_found"}, 404)
        if not self.authorized(qs):
            return self.send_json({"ok": False, "error": "unauthorized"}, 401)
        try:
            n = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            n = 0
        if n <= 0 or n > MAX_BODY:
            return self.send_json({"ok": False, "error": "bad_body_size", "max_bytes": MAX_BODY}, 413 if n > MAX_BODY else 400)
        try:
            payload = json.loads(self.rfile.read(n).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError
        except (ValueError, UnicodeDecodeError):
            return self.send_json({"ok": False, "error": "invalid_json"}, 400)
        try:
            return self.hook(payload)
        except sqlite3.Error as e:
            return self.send_json({"ok": False, "error": "db_error", "detail": str(e)}, 500)

    def serve_index(self):
        p = os.path.join(HERE, "..", "index.html")
        if not os.path.isfile(p):
            return self.send_json({"ok": True, "service": "baccarat-db", "docs": "ดูเส้นทางใน server.py"})
        body = open(p, "rb").read()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def stats(self):
        with db() as con:
            rows = con.execute(
                "SELECT tag, source, COUNT(*) shoes, SUM(hands) hands, SUM(b) b, SUM(p) p, SUM(t) t "
                "FROM shoes GROUP BY tag, source ORDER BY shoes DESC").fetchall()
        tags = [{"tag": r["tag"], "source": r["source"], "shoes": r["shoes"], "hands": r["hands"],
                 "B": r["b"], "P": r["p"], "T": r["t"]} for r in rows]
        hands = sum(t["hands"] for t in tags)
        tot = {k: sum(t[k] for t in tags) for k in "BPT"}
        self.send_json({"ok": True, "shoes": sum(t["shoes"] for t in tags), "hands": hands, "counts": tot,
                        "freq": {k: (tot[k] / hands if hands else 0) for k in "BPT"}, "tags": tags})

    def boards(self, qs):
        q = lambda k, d="": qs.get(k, [d])[0]
        where, args = [], []
        if q("tag"):
            where.append("tag = ?"); args.append(q("tag"))
        if q("min_hands"):
            where.append("hands >= ?"); args.append(to_int(q("min_hands"), 1, 1, 10**6))
        if q("max_hands"):
            where.append("hands <= ?"); args.append(to_int(q("max_hands"), 10**6, 1, 10**6))
        w = (" WHERE " + " AND ".join(where)) if where else ""
        order = {"random": "RANDOM()", "latest": "seq DESC", "oldest": "seq ASC"}.get(q("order", "oldest"))
        if order is None:
            return self.send_json({"ok": False, "error": "bad_order", "allowed": ["random", "latest", "oldest"]}, 400)
        limit = to_int(q("limit"), 100, 1, MAX_LIMIT)
        offset = to_int(q("offset"), 0, 0, 10**9)
        with db() as con:
            total = con.execute("SELECT COUNT(*) FROM shoes" + w, args).fetchone()[0]
            rows = con.execute(f"{SELECT}{w} ORDER BY {order} LIMIT ? OFFSET ?", args + [limit, offset]).fetchall()
        self.send_json({"ok": True, "total": total, "count": len(rows), "offset": offset,
                        "boards": [to_board(r) for r in rows]})

    def board_one(self, bid):
        with db() as con:
            r = con.execute(SELECT + " WHERE id = ?", (bid,)).fetchone()
        if not r:
            return self.send_json({"ok": False, "error": "not_found"}, 404)
        self.send_json({"ok": True, "board": to_board(r)})

    def hook(self, p):
        ev = str(p.get("event") or "")
        if ev == "test":
            return self.send_json({"ok": True, "event": "test", "message": "เชื่อมต่อฐานข้อมูลสำเร็จ"})
        items = p.get("boards") if isinstance(p.get("boards"), list) else ([p["board"]] if isinstance(p.get("board"), dict) else [])
        if not items:
            return self.send_json({"ok": False, "error": "no_boards", "hint": "ส่ง event=board_finished พร้อม board หรือ event=export_boards พร้อม boards[]"}, 400)
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        added = skipped = 0
        with db() as con:
            for b in items:
                if not isinstance(b, dict):
                    skipped += 1; continue
                res = clean_results(b.get("results"))
                if not res or len(res) > MAX_HANDS:
                    skipped += 1; continue
                bid = str(b.get("id") or "")[:80] or "hook-" + secrets.token_hex(6)
                cur = con.execute(
                    "INSERT OR IGNORE INTO shoes (id,name,tag,at,results,hands,b,p,t,source) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (bid, str(b.get("name") or "นำเข้า")[:120], str(b.get("tag") or "ไม่ระบุ")[:60],
                     str(b.get("at") or b.get("finished_at") or now)[:40], res, len(res),
                     res.count("B"), res.count("P"), res.count("T"), "webhook"))
                if cur.rowcount: added += 1
                else: skipped += 1
            total = con.execute("SELECT COUNT(*) FROM shoes").fetchone()[0]
        self.send_json({"ok": True, "event": ev or "unknown", "added": added, "skipped": skipped, "total_shoes": total})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1", help="ใช้ 0.0.0.0 เพื่อให้เครื่องอื่นเข้าถึงได้")
    ap.add_argument("--port", type=int, default=8787)
    a = ap.parse_args()
    if not os.path.isfile(DB_PATH):
        sys.exit(f"ไม่พบฐานข้อมูล {DB_PATH} รัน import_csv.py ก่อน")
    if a.host != "127.0.0.1" and not TOKEN:
        print("คำเตือน: เปิดให้เครื่องอื่นเข้าถึงโดยไม่ตั้ง BACC_TOKEN ใครก็เขียนข้อมูลเข้ามาได้", file=sys.stderr)
    srv = ThreadingHTTPServer((a.host, a.port), Handler)
    print(f"ฐานข้อมูล: {DB_PATH}\nเปิดที่ http://{a.host}:{a.port}  (โทเคน: {'เปิด' if TOKEN else 'ปิด'})")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

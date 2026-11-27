#!/usr/bin/env python3
"""แปลง baccaratDataSet.csv (Kaggle) ให้เป็นฐานข้อมูล SQLite แบบ 1 แถว = 1 กระดาน (1 สำรับ)

ใช้เฉพาะไลบรารีมาตรฐานของ Python ไม่ต้องติดตั้งอะไรเพิ่ม

    python3 import_csv.py baccaratDataSet.csv            # สร้าง baccarat.db
    python3 import_csv.py baccaratDataSet.csv --db my.db

วิธีแปลง (ตรวจกับข้อมูลจริงแล้ว):
  - คอลัมน์ "winner" ของแต่ละแถว = ผลของตานั้น: 1 = Banker, -1 = Player, 0 = Tie
  - แถวที่ "last winner" เป็น -100 คือตาแรกของสำรับใหม่ จึงใช้เป็นเส้นแบ่งกระดาน
"""
import argparse, csv, os, sqlite3, sys, time

MAP = {"1": "B", "-1": "P", "0": "T"}
SCHEMA = """
CREATE TABLE IF NOT EXISTS shoes (
  seq     INTEGER PRIMARY KEY AUTOINCREMENT,
  id      TEXT NOT NULL UNIQUE,
  name    TEXT NOT NULL,
  tag     TEXT NOT NULL,
  at      TEXT NOT NULL,
  results TEXT NOT NULL,
  hands   INTEGER NOT NULL,
  b INTEGER NOT NULL, p INTEGER NOT NULL, t INTEGER NOT NULL,
  source  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_shoes_tag   ON shoes(tag);
CREATE INDEX IF NOT EXISTS idx_shoes_hands ON shoes(hands);
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv_path")
    ap.add_argument("--db", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "baccarat.db"))
    ap.add_argument("--tag", default="kaggle-2024-05-27", help="แท็กของกระดานที่นำเข้า")
    ap.add_argument("--at", default="2024-05-27T00:00:00Z", help="วันที่ของชุดข้อมูล")
    a = ap.parse_args()

    if os.path.exists(a.db):
        sys.exit(f"มีไฟล์ {a.db} อยู่แล้ว ลบหรือเปลี่ยนชื่อก่อน (กันนำเข้าซ้ำ)")

    con = sqlite3.connect(a.db)
    con.executescript(SCHEMA)
    t0 = time.time()
    shoes, bad_link, unknown, rows = [], 0, 0, 0
    cur, prev_w = [], None

    def flush():
        if not cur:
            return
        s = "".join(cur)
        n = len(shoes) + 1
        shoes.append((f"kaggle-{n:06d}", f"Kaggle #{n:06d}", a.tag, a.at, s, len(s),
                      s.count("B"), s.count("P"), s.count("T"), "kaggle"))

    with open(a.csv_path, newline="") as f:
        r = csv.reader(f)
        head = next(r)
        iw, il = head.index("winner"), head.index("last winner")
        for row in r:
            if not row:
                continue
            rows += 1
            lw, w = row[il], row[iw]
            if lw == "-100":            # ตาแรกของสำรับใหม่
                flush(); cur = []
            elif lw != prev_w:          # ผลตาก่อนหน้าต้องตรงกับ last winner
                bad_link += 1
            c = MAP.get(w)
            if c is None:
                unknown += 1
            else:
                cur.append(c)
            prev_w = w
            if rows % 2_000_000 == 0:
                print(f"  อ่านแล้ว {rows:,} แถว", file=sys.stderr)
        flush()

    con.executemany("INSERT INTO shoes (id,name,tag,at,results,hands,b,p,t,source) VALUES (?,?,?,?,?,?,?,?,?,?)", shoes)
    hands = sum(s[5] for s in shoes)
    con.executemany("INSERT OR REPLACE INTO meta VALUES (?,?)", [
        ("kaggle_source", "coulbynguyen/baccarat-data-set-5-27-24"),
        ("kaggle_rows", str(rows)), ("kaggle_shoes", str(len(shoes))),
    ])
    con.commit(); con.execute("VACUUM"); con.close()
    print(f"เสร็จ: {rows:,} แถว -> {len(shoes):,} กระดาน {hands:,} ตา  ({time.time()-t0:.0f} วินาที)")
    print(f"ตรวจความต่อเนื่อง: แถวที่ไม่ต่อกัน {bad_link}, ค่า winner แปลกปลอม {unknown}")
    print(f"ไฟล์: {a.db} ({os.path.getsize(a.db)/1e6:.1f} MB)")


if __name__ == "__main__":
    main()

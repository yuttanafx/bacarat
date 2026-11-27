#!/usr/bin/env python3
"""ส่งออกฐานข้อมูลเป็นไฟล์ข้อความเล็ก ๆ ใน data/ ให้หน้าเว็บดึงได้โดยไม่ต้องมีเซิร์ฟเวอร์ (เช่น GitHub Pages)

    python3 export_static.py            # อ่าน db/baccarat.db เขียนลง ../data/

1 ไฟล์ = 2,000 กระดาน (shard) 1 บรรทัด = ผลของ 1 กระดาน (B/P/T) และมี manifest.json บอกจำนวนไฟล์
รหัสกระดานตรงกับในฐานข้อมูล (kaggle-000001 …) จึงไม่ซ้ำกันเมื่อดึงจากสองทาง
"""
import json, os, shutil, sqlite3, sys
HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "baccarat.db"); OUT = os.path.join(HERE, "..", "data"); PER = 2000

con = sqlite3.connect(DB)
rows = con.execute("SELECT seq, id, tag, at, results FROM shoes WHERE source='kaggle' ORDER BY seq").fetchall()
if not rows: sys.exit("ไม่พบกระดานชุด kaggle ในฐานข้อมูล")
tag, at = rows[0][2], rows[0][3]
for i, (seq, bid, *_ ) in enumerate(rows, 1):
    assert bid == f"kaggle-{i:06d}" and seq == i, "รหัสกระดานไม่เรียงต่อเนื่อง"
shutil.rmtree(OUT, ignore_errors=True); os.makedirs(OUT)
files = []
for s in range(0, len(rows), PER):
    name = f"s{s // PER:03d}.txt"; files.append(name)
    with open(os.path.join(OUT, name), "w", newline="\n") as f:
        f.write("\n".join(r[4] for r in rows[s:s + PER]) + "\n")
man = {"version": 1, "source": "kaggle coulbynguyen/baccarat-data-set-5-27-24", "tag": tag, "at": at,
       "id_prefix": "kaggle-", "per_shard": PER, "boards": len(rows),
       "hands": sum(len(r[4]) for r in rows), "files": files}
json.dump(man, open(os.path.join(OUT, "manifest.json"), "w"), ensure_ascii=False, indent=1)
print(f"ส่งออก {len(rows):,} กระดาน เป็น {len(files)} ไฟล์ ใน {os.path.abspath(OUT)}")

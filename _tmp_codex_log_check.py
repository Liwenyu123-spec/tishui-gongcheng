import os
import sqlite3

p = os.path.expanduser(r"~\.codex\logs_2.sqlite")
con = sqlite3.connect(p)
cur = con.cursor()
print("TABLES")
for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'"):
    print(r[0])
    cols = list(cur.execute(f"PRAGMA table_info({r[0]})"))
    print(" ", [c[1] for c in cols])

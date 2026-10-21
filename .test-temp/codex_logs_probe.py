import os
import sqlite3
import datetime

p = os.path.expanduser("~/.codex/logs_2.sqlite")
c = sqlite3.connect("file:" + p + "?mode=ro", uri=True)
cur = c.cursor()
tables = [r[0] for r in cur.execute("select name from sqlite_master where type='table'")]
print("tables:", tables)
for t in tables:
    sql = cur.execute("select sql from sqlite_master where type='table' and name=?", (t,)).fetchone()[0]
    print("---", t, "---")
    print(sql)

import os
import sqlite3
import datetime
import collections

p = os.path.expanduser("~/.codex/logs_2.sqlite")
c = sqlite3.connect("file:" + p + "?mode=ro", uri=True)
cur = c.cursor()
now = datetime.datetime.now(datetime.timezone.utc)
since = int((now - datetime.timedelta(minutes=6)).timestamp())

rows = cur.execute(
    "select ts, level, target, feedback_log_body from logs where ts>=? order by ts asc", (since,)
).fetchall()
print("rows", len(rows))
cnt = collections.Counter(r[2] for r in rows)
for t, n in cnt.most_common(15):
    print(f"{n:5d}  {t}")

print("\n== sample of newest 25 ==")
for ts, level, target, body in rows[-25:]:
    tt = datetime.datetime.fromtimestamp(ts).strftime("%H:%M:%S")
    b = (body or "").replace("\n", " ")
    print(f"[{tt}] {level} {target}: {b[-200:]}")

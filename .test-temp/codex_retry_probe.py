import os
import sqlite3
import datetime

p = os.path.expanduser("~/.codex/logs_2.sqlite")
c = sqlite3.connect("file:" + p + "?mode=ro", uri=True)
cur = c.cursor()

now = datetime.datetime.now(datetime.timezone.utc)
since = int((now - datetime.timedelta(minutes=120)).timestamp())

rows = cur.execute(
    "select ts, level, target, feedback_log_body from logs where ts>=? and (target like '%responses_retry%' or target like '%router%' or target like '%stream%' or level='ERROR') order by ts asc",
    (since,),
).fetchall()
print("rows:", len(rows))
for ts, level, target, body in rows:
    t = datetime.datetime.fromtimestamp(ts).strftime("%H:%M:%S")
    body = (body or "").replace("\n", " ")
    # keep only the trailing part which usually holds the message
    tail = body[-700:]
    print(f"\n=== [{t}] {level} {target} ===")
    print(tail)

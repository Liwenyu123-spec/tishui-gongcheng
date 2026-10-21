import os
import sqlite3
import datetime

p = os.path.expanduser("~/.codex/logs_2.sqlite")
c = sqlite3.connect("file:" + p + "?mode=ro", uri=True)
cur = c.cursor()
now = datetime.datetime.now(datetime.timezone.utc)
for mins in (5, 15, 30):
    since = int((now - datetime.timedelta(minutes=mins)).timestamp())
    n = cur.execute("select count(*) from logs where ts>=?", (since,)).fetchone()[0]
    print(f"last {mins}min rows: {n}")

since = int((now - datetime.timedelta(minutes=12)).timestamp())
print("\n== last 12 min (level>=WARN or sampling) ==")
for ts, level, target, body in cur.execute(
    "select ts, level, target, feedback_log_body from logs where ts>=? and (level in ('WARN','ERROR') or target like '%responses%' or target like '%sampling%') order by ts asc",
    (since,),
):
    t = datetime.datetime.fromtimestamp(ts).strftime("%H:%M:%S")
    b = (body or "").replace("\n", " ")
    print(f"[{t}] {level} {target}: {b[-260:]}")

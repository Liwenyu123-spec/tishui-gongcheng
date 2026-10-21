import os
import sqlite3
import datetime

p = os.path.expanduser("~/.codex/logs_2.sqlite")
c = sqlite3.connect("file:" + p + "?mode=ro", uri=True)
cur = c.cursor()
now = datetime.datetime.now(datetime.timezone.utc)
since = int((now - datetime.timedelta(hours=3)).timestamp())
for ts, level, target, body in cur.execute(
    "select ts, level, target, feedback_log_body from logs where ts>=? and target='codex_core::shell_snapshot' order by ts asc",
    (since,),
):
    t = datetime.datetime.fromtimestamp(ts).strftime("%H:%M:%S")
    b = (body or "").replace("\n", " ")
    print(f"[{t}] {level}: ...{b[-500:]}")
    print()

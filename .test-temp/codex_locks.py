import os
import sqlite3
import datetime

p = os.path.expanduser("~/.codex/logs_2.sqlite")
c = sqlite3.connect("file:" + p + "?mode=ro", uri=True)
cur = c.cursor()
now = datetime.datetime.now(datetime.timezone.utc)
since = int((now - datetime.timedelta(hours=8)).timestamp())
pats = ["index.lock", "Another git process", "Unable to create", "timed out", "timeout", "Unknown process id", "SandboxDenied", "denied", "Operation not permitted"]
for pat in pats:
    rows = cur.execute(
        "select ts, level, target, substr(feedback_log_body,-300) from logs where ts>=? and feedback_log_body like ? order by ts asc limit 6",
        (since, f"%{pat}%"),
    ).fetchall()
    if rows:
        print(f"--- {pat} ({len(rows)}) ---")
        for ts, level, target, body in rows:
            t = datetime.datetime.fromtimestamp(ts).strftime("%H:%M:%S")
            print(f"  [{t}] {level} {target}: {(body or '').replace(chr(10),' ')}")

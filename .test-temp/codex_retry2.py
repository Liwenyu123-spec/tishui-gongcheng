import os
import sqlite3
import datetime
import re

p = os.path.expanduser("~/.codex/logs_2.sqlite")
c = sqlite3.connect("file:" + p + "?mode=ro", uri=True)
cur = c.cursor()

now = datetime.datetime.now(datetime.timezone.utc)
since = int((now - datetime.timedelta(minutes=120)).timestamp())

print("=== responses_retry ===")
for ts, level, body in cur.execute(
    "select ts, level, feedback_log_body from logs where ts>=? and target='codex_core::responses_retry' order by ts asc",
    (since,),
):
    t = datetime.datetime.fromtimestamp(ts).strftime("%H:%M:%S")
    b = (body or "")
    b = b.replace("\n", " ")
    b = re.sub(r"[^ ]*\{[^}]*\}", "", b)
    print(f"[{t}] {level} {b[-400:]}")

print()
print("=== ERROR rows (any target) since 14:30 ===")
since2 = int((now - datetime.timedelta(minutes=40)).timestamp())
for ts, level, target, body in cur.execute(
    "select ts, level, target, feedback_log_body from logs where ts>=? and level='ERROR' order by ts asc",
    (since2,),
):
    t = datetime.datetime.fromtimestamp(ts).strftime("%H:%M:%S")
    b = (body or "").replace("\n", " ")
    m = re.search(r"(error|failed|Error)[:=].{0,300}", b)
    print(f"[{t}] {target}: {m.group(0) if m else b[-300:]}")

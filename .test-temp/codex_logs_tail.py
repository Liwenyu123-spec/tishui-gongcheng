import os
import sqlite3
import datetime

p = os.path.expanduser("~/.codex/logs_2.sqlite")
c = sqlite3.connect("file:" + p + "?mode=ro", uri=True)
cur = c.cursor()

now = datetime.datetime.now(datetime.timezone.utc)
since = int((now - datetime.timedelta(minutes=90)).timestamp())

print("== errors in last 90min ==")
rows = cur.execute(
    "select ts, level, target, substr(feedback_log_body,1,400) from logs where ts>=? and level in ('ERROR','WARN') order by ts desc limit 60",
    (since,),
).fetchall()
for ts, level, target, body in rows:
    t = datetime.datetime.fromtimestamp(ts).strftime("%H:%M:%S")
    print(f"[{t}] {level} {target}: {body}")

print()
print("== capacity / overload mentions last 90min ==")
rows = cur.execute(
    "select ts, level, target, substr(feedback_log_body,1,300) from logs where ts>=? and (feedback_log_body like '%overload%' or feedback_log_body like '%capacity%' or feedback_log_body like '%stream%error%' or feedback_log_body like '%retry%') order by ts desc limit 40",
    (since,),
).fetchall()
for ts, level, target, body in rows:
    t = datetime.datetime.fromtimestamp(ts).strftime("%H:%M:%S")
    print(f"[{t}] {level} {target}: {body}")

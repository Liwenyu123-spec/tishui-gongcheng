import os
import sqlite3
import datetime
import collections

p = os.path.expanduser("~/.codex/logs_2.sqlite")
c = sqlite3.connect("file:" + p + "?mode=ro", uri=True)
cur = c.cursor()
now = datetime.datetime.now(datetime.timezone.utc)
since = int((now - datetime.timedelta(hours=10)).timestamp())

rows = cur.execute(
    "select ts, feedback_log_body from logs where ts>=? and (feedback_log_body like '%is_connect=true%' or feedback_log_body like '%stream disconnected%' or feedback_log_body like '%error decoding response body%') order by ts asc",
    (since,),
).fetchall()
print("connect/stream failures:", len(rows))
per_hour = collections.Counter(datetime.datetime.fromtimestamp(r[0]).strftime("%H") for r in rows)
for h in sorted(per_hour):
    print(f"  {h}点: {per_hour[h]}")

print("\nendpoints seen:")
eps = collections.Counter()
for ts, body in rows:
    for m in ("chatgpt.com/backend-api/codex/responses", "chatgpt.com/backend-api/ps/plugins", "chatgpt.com/backend-api/models", "codex-cloud"):
        if m in (body or ""):
            eps[m] += 1
            break
    else:
        eps["other"] += 1
for k, v in eps.most_common():
    print(f"  {v:4d}  {k}")

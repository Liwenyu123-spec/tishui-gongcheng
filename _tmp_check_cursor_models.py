import sqlite3
import re

db = r"C:\Users\lenovo\AppData\Roaming\Cursor\User\globalStorage\state.vscdb"
con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
cur = con.cursor()
keys = [k[0] for k in cur.execute("SELECT key FROM ItemTable").fetchall()]
pat = re.compile(r"deepseek|openai|baseUrl|apiKey|model|aiconfig|cursor\.|anysphere", re.I)
interesting = sorted(k for k in keys if pat.search(k))
print("KEY_COUNT", len(interesting))
for k in interesting:
    print("KEY:", k)

secret_markers = ("apikey", "api_key", "secret", "token", "password", "authorization")
for k in interesting:
    row = cur.execute("SELECT value FROM ItemTable WHERE key=?", (k,)).fetchone()
    if not row:
        continue
    raw = row[0]
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    s = str(raw)
    low = (k + s).lower()
    if any(m in low for m in secret_markers):
        print(
            "VALUE_META:",
            k,
            "len=",
            len(s),
            "has_sk_prefix=",
            "sk-" in s,
            "has_true=",
            "true" in s.lower(),
            "emptyish=",
            s.strip() in ("", '""', "null", "{}", "[]"),
        )
        continue
    if len(s) > 800:
        s = s[:800] + "..."
    print("VALUE:", k, "=", s)

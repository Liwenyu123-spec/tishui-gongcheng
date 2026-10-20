import sqlite3
import json
import re

db = r"C:\Users\lenovo\AppData\Roaming\Cursor\User\globalStorage\state.vscdb"
con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
cur = con.cursor()
rows = cur.execute("SELECT key, value FROM ItemTable").fetchall()

targets = []
for k, v in rows:
    if isinstance(v, bytes):
        try:
            v = v.decode("utf-8", errors="replace")
        except Exception:
            v = str(v)
    s = str(v)
    kl = k.lower()
    if any(
        x in kl
        for x in [
            "openai",
            "baseurl",
            "base_url",
            "deepseek",
            "ownkey",
            "custommodel",
            "modelcatalog",
            "availablemodels",
            "usermodel",
            "aiSettings",
            "aisettings",
            "cursorauth",
            "openAI",
        ]
    ) or any(
        x in s.lower()
        for x in [
            "deepseek",
            "api.deepseek.com",
            "overrideopenai",
            "useOpenAIApiKey",
            "openaiApiKey",
            "openAIBaseUrl",
        ]
    ):
        targets.append((k, s))

print("MATCHES", len(targets))
for k, s in sorted(targets, key=lambda x: x[0]):
    # redact secrets
    display = s
    if "secret://" in k.lower() or "apikey" in k.lower() or "api_key" in k.lower():
        print("META", k, "len=", len(s), "encrypted_blob=yes")
        continue
    # redact long sk- strings if any
    display = re.sub(r"sk-[A-Za-z0-9_\-]{8,}", "sk-***REDACTED***", display)
    if len(display) > 1200:
        display = display[:1200] + "..."
    print("---")
    print("KEY:", k)
    print(display)

# also scan ALL values for deepseek / base url strings
print("\n=== GLOBAL STRING SCAN ===")
for k, v in rows:
    if isinstance(v, bytes):
        try:
            v = v.decode("utf-8", errors="replace")
        except Exception:
            continue
    s = str(v)
    if "deepseek" in s.lower() or "api.deepseek.com" in s.lower():
        cleaned = re.sub(r"sk-[A-Za-z0-9_\-]{8,}", "sk-***REDACTED***", s)
        if len(cleaned) > 600:
            cleaned = cleaned[:600] + "..."
        print("HIT_KEY:", k)
        print(cleaned)
        print("---")

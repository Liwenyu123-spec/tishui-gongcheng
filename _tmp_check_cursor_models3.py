import sqlite3
import json
import re

db = r"C:\Users\lenovo\AppData\Roaming\Cursor\User\globalStorage\state.vscdb"
con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
cur = con.cursor()
key = "src.vs.platform.reactivestorage.browser.reactiveStorageServiceImpl.persistentStorage.applicationUser"
raw = cur.execute("SELECT value FROM ItemTable WHERE key=?", (key,)).fetchone()[0]
data = json.loads(raw)

# print top-level keys
print("TOP_KEYS:")
for k in sorted(data.keys()):
    print(" ", k)

# walk for interesting fields
interesting_re = re.compile(
    r"openai|baseUrl|base_url|deepseek|apiKey|useOpenAI|ownKey|customModel|modelOverride|openAI",
    re.I,
)


def walk(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}" if path else k
            if interesting_re.search(str(k)):
                dump(p, v)
            walk(v, p)
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:50]):
            walk(v, f"{path}[{i}]")


def dump(path, v):
    s = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
    s = re.sub(r"sk-[A-Za-z0-9_\-]{8,}", "sk-***REDACTED***", s)
    # if looks like api key alone, redact
    if "key" in path.lower() and isinstance(v, str) and len(v) > 20:
        print(f"{path} = <redacted len={len(v)}>")
        return
    if len(s) > 500:
        s = s[:500] + "..."
    print(f"{path} = {s}")


print("\nINTERESTING FIELDS:")
walk(data)

# specifically look for model-related arrays
for cand in [
    "availableDefaultModels2",
    "availableModels",
    "modelSettings",
    "aiSettings",
    "featureModelConfigs",
    "openaiApiKey",
    "openAIBaseUrl",
    "useOpenAIKey",
    "useOpenAIApiKey",
    "overrideOpenAIBaseUrl",
    "customModels",
    "userAddedModels",
    "models",
]:
    if cand in data:
        dump(cand, data[cand])

# membership related
for k in data:
    if "member" in k.lower() or "plan" in k.lower() or "subscription" in k.lower():
        dump(k, data[k])

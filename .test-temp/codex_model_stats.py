import json
import os
import glob
import collections

base = os.path.expanduser("~/.codex/sessions/2026/10/21")
model_by_turn = {}
err_by_turn = {}
stats = collections.Counter()
errs = collections.Counter()

for path in sorted(glob.glob(os.path.join(base, "*.jsonl"))):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                j = json.loads(line)
            except Exception:
                continue
            p = j.get("payload") or {}
            if j.get("type") == "turn_context":
                model_by_turn[p.get("turn_id")] = p.get("model")
            elif j.get("type") == "event_msg":
                if p.get("type") == "task_complete":
                    tid = p.get("turn_id")
                    m = model_by_turn.get(tid, "?")
                    stats[m] += 1
                    e = p.get("error")
                    if e:
                        errs[(m, e.get("codex_error_info") or e.get("message"))] += 1

print("turns per model:", dict(stats))
print("errors per (model, type):")
for k, v in errs.most_common():
    print("  ", k, v)

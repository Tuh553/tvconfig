import json, os, re
from collections import Counter

d = json.load(open("江湖.json", encoding="utf-8"))

print("=== remote 0/1 ===")
for s in d["sites"]:
    if s.get("type") in (0, 1):
        print(json.dumps({k: s.get(k) for k in ("key", "name", "type", "api")}, ensure_ascii=False))

print("=== type4 ===")
for s in d["sites"]:
    if s.get("type") == 4:
        print(json.dumps({k: s.get(k) for k in ("key", "name", "type", "api", "ext")}, ensure_ascii=False)[:350])

print("=== csp ext shapes ===")
c = Counter()
missing = []
bad = []
for s in d["sites"]:
    if not str(s.get("api", "")).startswith("csp_"):
        continue
    ext = s.get("ext")
    if not ext or not isinstance(ext, str) or not str(ext).strip():
        c["no_ext"] += 1
        continue
    path = ext[2:] if ext.startswith("./") else ext
    if not os.path.isfile(path):
        missing.append((s["key"], ext))
        c["missing"] += 1
        continue
    try:
        j = json.load(open(path, encoding="utf-8"))
    except Exception:
        bad.append(s["key"])
        c["bad"] += 1
        continue
    if not isinstance(j, dict):
        c["not_dict"] += 1
        continue
    flags = []
    for k in ["主页url", "分类url", "host", "url", "homeUrl", "home", "site", "baseUrl", "站名"]:
        if k in j and j[k]:
            flags.append(k)
    c[",".join(flags) or "empty_dict"] += 1

print(dict(c))
print("missing", missing[:20], "count", len(missing))
print("bad", bad)

print("=== py urls ===")
for s in d["sites"]:
    if ".py" not in str(s.get("api", "")):
        continue
    path = str(s["api"])[2:] if str(s["api"]).startswith("./") else s["api"]
    exists = os.path.isfile(path)
    urls = []
    if exists:
        text = open(path, encoding="utf-8", errors="ignore").read()
        urls = re.findall(r"https?://[^\s\"']+", text)[:5]
    print(s["key"], "exists", exists, "urls", urls[:3])

print("=== parses sample ===")
for p in d.get("parses", [])[:5]:
    print(json.dumps(p, ensure_ascii=False)[:300])
print("parses count", len(d.get("parses", [])))

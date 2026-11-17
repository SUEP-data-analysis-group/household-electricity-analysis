# -*- coding: utf-8 -*-
"""交付包自校验：逐个比对 inputs / outputs 的 SHA-256 与 derivation_manifest.json 记录是否一致"""
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
MANIFEST = BASE / "out" / "derivation_manifest.json"


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


m = json.loads(MANIFEST.read_text(encoding="utf-8"))
bad = []
for group in ("inputs", "outputs", "code"):
    for item in m.get(group, []):
        p = BASE / item["file"]
        if not p.exists():
            bad.append((item["file"], "MISSING"))
            continue
        if sha256_of(p) != item["sha256"]:
            bad.append((item["file"], "HASH_MISMATCH"))

print("核验条目：输入 %d、代码 %d、输出 %d" % (
    len(m["inputs"]), len(m["code"]), len(m["outputs"])))
print("不一致：", bad if bad else "无")
print("核验结果：", "全部一致" if not bad else "存在差异")

"""
normalize.py —— 抽取后清洗（解决示例文件里的数据质量问题）。

针对的问题（你库里真实存在）：
  - TF/靶基因写成多实体串： "Sp1, Sp3, Sp4" / "Sp1/Sp3/Sp4"
  - 大小写、命名不统一： VEGF vs VEGFA, SP1 vs Sp1
  - 同一篇里重复关系
  - 自环： transcription_factor == target_gene（如 SP1→SP1）

做法:
  读 extraction_results.json -> 每条关系按多实体拆成多条 -> 统一大写+同义词映射
  -> 丢弃自环(TF==target_gene) -> 同一文档内 (TF,靶基因,方向) 去重(保留最高置信度) -> 写 extraction_results_clean.json

用法:
    python normalize.py
    python normalize.py --in extraction_results.json --out extraction_results_clean.json
"""
import argparse
import json
import re
from pathlib import Path

SYNONYMS = {
    "survivin": "birc5", "birc5": "birc5",
    "cyclin d1": "ccnd1", "cyclind1": "ccnd1", "ccnd1": "ccnd1",
    "c-met": "met", "c met": "met", "cmet": "met", "met": "met",
    "cox-2": "ptgs2", "cox2": "ptgs2", "ptgs2": "ptgs2",
    "vegf": "vegfa", "vegfa": "vegfa",
    "vegfr1": "flt1", "flt1": "flt1",
    "vegfr2": "kdr", "kdr": "kdr",
    "gastrin": "gast", "gast": "gast",
}
SPLIT_RE = re.compile(r"\s*(?:,|/|、|\band\b)\s*", re.IGNORECASE)
CONF_RANK = {"high": 3, "medium": 2, "low": 1, "unknown": 0}

_self_loop_count = 0
_unknown_dir_count = 0


def norm_symbol(s: str) -> str:
    s = (s or "").strip().lower()
    return SYNONYMS.get(s, s)


def split_entities(s: str) -> list[str]:
    if not s:
        return ["UNKNOWN"]
    parts = [norm_symbol(p) for p in SPLIT_RE.split(s) if p.strip()]
    return parts or [norm_symbol(s)]


def clean_doc(doc: dict) -> dict:
    global _self_loop_count, _unknown_dir_count
    best = {}
    for rel in doc.get("relations", []):
        if not isinstance(rel, dict):
            continue
        for tf in split_entities(rel.get("transcription_factor")):
            for tg in split_entities(rel.get("target_gene")):
                if tf == "UNKNOWN" or tg == "UNKNOWN":
                    continue
                if tf == tg:
                    _self_loop_count += 1
                    continue
                reg = (rel.get("regulation_type") or "unknown").strip().lower()
                if reg == "unknown":
                    _unknown_dir_count += 1
                    continue
                key = (tf, tg, reg)
                new = dict(rel)
                new["transcription_factor"] = tf
                new["target_gene"] = tg
                new["regulation_type"] = reg
                old = best.get(key)
                if old is None or CONF_RANK.get(new.get("confidence", "unknown"), 0) > \
                        CONF_RANK.get(old.get("confidence", "unknown"), 0):
                    best[key] = new
    cleaned = list(best.values())
    out = dict(doc)
    out["relations"] = cleaned
    out["relation_count"] = len(cleaned)
    return out


def get_self_loop_count() -> int:
    return _self_loop_count


def get_unknown_dir_count() -> int:
    return _unknown_dir_count


def main():
    global _self_loop_count, _unknown_dir_count
    _self_loop_count = 0
    _unknown_dir_count = 0
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="extraction_results.json")
    ap.add_argument("--out", default="extraction_results_clean.json")
    args = ap.parse_args()

    data = json.loads(Path(args.inp).read_text(encoding="utf-8"))
    cleaned = [clean_doc(d) for d in data if isinstance(d, dict)]
    Path(args.out).write_text(
        json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8")

    before = sum(len(d.get("relations", [])) for d in data)
    after = sum(d["relation_count"] for d in cleaned)
    print(f"清洗完成: {args.inp} ({before} 条) -> {args.out} ({after} 条, 已拆分+去重)")
    if _self_loop_count > 0:
        print(f"丢弃自环（TF==target_gene）: {_self_loop_count} 条")
    if _unknown_dir_count > 0:
        print(f"丢弃方向未知（regulation_type=unknown）: {_unknown_dir_count} 条")


if __name__ == "__main__":
    main()
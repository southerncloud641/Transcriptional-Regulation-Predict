"""
evaluate.py —— 补上 slides 第 13 页缺失的【评估】环节。

适配示例文件的数据结构：extraction_results.json 是
  [ {pdf_file, relations:[{transcription_factor, target_gene, regulation_type, ...}]}, ... ]

功能:
  1. 展开成 (TF, 靶基因, 调控方向) 三元组；自动拆分多实体("Sp1, Sp3, Sp4"等)；归一化大小写/同义词
  2. 跟金标准 gold_standard.csv 比，算 Precision / Recall / F1
  3. 打印 FP(疑似幻觉) / FN(漏抽) 清单 + 每篇 PDF 命中情况
  4. 用 --tag 记录本轮指标到 runs_log.csv，方便做"迭代前后对比"

用法:
    python evaluate.py
    python evaluate.py --pred extraction_results.json --gold gold_standard.csv --tag v1
"""
import argparse
import csv
import json
import re
from collections import defaultdict
from datetime import datetime
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


def norm(s: str) -> str:
    s = (s or "").strip().lower()
    return SYNONYMS.get(s, s)


def split_entities(s: str) -> list[str]:
    if not s:
        return []
    parts = [norm(p) for p in SPLIT_RE.split(s) if p.strip()]
    return parts or [norm(s)]


def expand_triples(tf_field, target_field, reg) -> set:
    out = set()
    for tf in split_entities(tf_field):
        for tg in split_entities(target_field):
            if tf and tg and tf != "UNKNOWN" and tg != "UNKNOWN":
                out.add((tf, tg, (reg or "").strip().lower()))
    return out


def load_predicted(pred_path: Path):
    data = json.loads(pred_path.read_text(encoding="utf-8"))
    pred, by_pdf = set(), defaultdict(set)
    for doc in data:
        pdf = doc.get("pdf_file", "?")
        for rel in doc.get("relations", []):
            t = expand_triples(rel.get("transcription_factor"),
                               rel.get("target_gene"), rel.get("regulation_type"))
            pred |= t
            by_pdf[pdf] |= t
    return pred, by_pdf


def load_gold(gold_path: Path) -> set:
    if not gold_path.exists():
        raise FileNotFoundError(f"找不到金标准 {gold_path}")
    gold = set()
    with open(gold_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            gold |= expand_triples(row["transcription_factor"],
                                   row["target_gene"], row["regulation_type"])
    return gold


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pred", default="extraction_results.json")
    ap.add_argument("--gold", default="gold_standard.csv")
    ap.add_argument("--tag", default="", help="本轮标签，如 v1 / v2；给了就写入 runs_log.csv")
    args = ap.parse_args()

    pred, by_pdf = load_predicted(Path(args.pred))
    gold = load_gold(Path(args.gold))
    tp, fp, fn = pred & gold, pred - gold, gold - pred
    P = len(tp) / len(pred) if pred else 0.0
    R = len(tp) / len(gold) if gold else 0.0
    F1 = 2 * P * R / (P + R) if P + R else 0.0

    print("===== 整体指标 =====")
    print(f"预测三元组 {len(pred)} | 金标准 {len(gold)} | 命中 TP {len(tp)}")
    print(f"Precision(提的准) = {P:.3f}")
    print(f"Recall   (提的全) = {R:.3f}")
    print(f"F1               = {F1:.3f}")

    print("\n===== FP 假阳性 / 疑似幻觉（precision 低就查这里）=====")
    for t in sorted(fp):
        print("  +", t)
    print("\n===== FN 漏抽（recall 低就查这里）=====")
    for t in sorted(fn):
        print("  -", t)

    print("\n===== 每篇 PDF 命中情况 =====")
    for pdf in sorted(by_pdf):
        print(f"  {pdf}: 抽到 {len(by_pdf[pdf])} 条, 命中金标准 {len(by_pdf[pdf] & gold)} 条")

    if args.tag:        # 记录到 runs_log.csv，做迭代对比
        log = Path("runs_log.csv")
        new = not log.exists()
        with open(log, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["time", "tag", "pred", "gold", "TP", "FP", "FN",
                            "precision", "recall", "f1"])
            w.writerow([datetime.now().strftime("%Y-%m-%d %H:%M"), args.tag,
                        len(pred), len(gold), len(tp), len(fp), len(fn),
                        f"{P:.3f}", f"{R:.3f}", f"{F1:.3f}"])
        print(f"\n已记录到 runs_log.csv（tag={args.tag}）")


if __name__ == "__main__":
    main()

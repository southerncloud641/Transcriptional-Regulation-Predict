import argparse
import json
import os
import re
import shutil
import time
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PDF_DIR = BASE_DIR / "实例文献"
GOLD_CSV = BASE_DIR / "gold_standard_v2.csv"
DB_PATH = BASE_DIR / "extraction.sqlite3"
RUNS_LOG = BASE_DIR / "runs_log.csv"

def get_json_path(prompt_version):
    return PDF_DIR / f"extraction_results_{prompt_version}.json"

API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
MODEL_NAME = "qwen-plus"

SYS_V1 = "你是一个专业的分子生物学与生物信息学专家。请严格基于用户提供的文献内容，提取其中所有明确提及或实验验证的“转录因子调控靶基因”关系。"
USER_V1 = """
【提取要求】
1. 仅提取文献中明确陈述或提供实验证据的调控关系，禁止推测、补充外部数据库知识或合并未直接关联的实体。
2. 对每条关系提取字段（缺失填 "unknown"）：transcription_factor, target_gene, regulation_type(activation/repression/dual/unknown), evidence_type, biological_context, auxiliary_proteins, confidence(high/medium/low), location。
3. 若同一对关系多次出现，合并为一条。
4. 输出必须为纯 JSON 数组，不含任何解释或 Markdown 标记。
5. 置信度低的关系也要输出，但 confidence 注明 "low"。
【文献内容】
{pdf_text}
"""

SYS_V2 = "你是一个严谨的分子生物学与生物信息学专家。只依据用户提供的这一篇文献的正文内容，提取“转录因子调控靶基因”关系。不得引入文献之外的数据库知识，不得臆测。"
USER_V2 = """
【提取要求】
1. 仅提取本文明确陈述或提供实验证据的调控关系；不要推测、不要补充外部知识。
2. 【每条关系只能有一个转录因子和一个靶基因】。若一句涉及多个（如 Sp1/Sp3/Sp4 调控 VEGF），必须拆成多条独立关系，禁止写成 "Sp1, Sp3, Sp4" 这种合并形式。
3. 【排除非转录因子作主语的关系】：microRNA、药物、化合物、SNP、lncRNA、circRNA、蛋白质（非TF）等均不得作为 transcription_factor，仅提取真正的转录因子（如 SP1、TP53、ZBTB10 等）。
4. 【忽略文末参考文献部分】：只抽取正文、图表标题和图注中的调控关系，跳过 References/Bibliography/文献列表等引用部分的内容。
5. 基因名一律用 HGNC 官方 symbol（如 VEGF 写作 VEGFA），统一大小写。
6. 字段（缺失填 "unknown"）：transcription_factor(单个,必须是转录因子), target_gene(单个), regulation_type(activation/repression/dual/unknown), evidence_type(若转引自他文写 "Literature citation" 并判 low), biological_context, auxiliary_proteins(数组，未提及填 "unknown"), confidence(high=本文直接实验; medium=本文间接证据; low=仅文献引用/泛泛陈述), location。
7. 同一对关系合并为一条，保留最完整信息与最高置信度。
8. 输出必须为纯 JSON 数组，不含任何解释或 Markdown 标记。

格式示例：
[
  {{
    "transcription_factor": "TP53",
    "target_gene": "CDKN1A",
    "regulation_type": "activation",
    "evidence_type": "ChIP-seq, Luciferase reporter",
    "biological_context": "Human HCT116, DNA damage",
    "auxiliary_proteins": ["EP300", "CREBBP"],
    "confidence": "high",
    "location": "p.4, Fig.1C-D"
  }}
]
【文献内容】
{pdf_text}
"""

SYS_V3 = "你是一个严谨的分子生物学与生物信息学专家。只依据用户提供的这一篇文献的正文内容，提取“转录因子调控靶基因”关系。不得引入文献之外的数据库知识，不得臆测。"
USER_V3 = """
【提取要求】
1. 仅提取本文明确陈述或提供实验证据的调控关系；不要推测、不要补充外部知识。
2. 【每条关系只能有一个转录因子和一个靶基因】。若一句涉及多个（如 Sp1/Sp3/Sp4 调控 VEGF），必须拆成多条独立关系，禁止写成 "Sp1, Sp3, Sp4" 这种合并形式。
3. 【排除非转录因子作主语的关系】：microRNA、药物、化合物、SNP、lncRNA、circRNA、蛋白质（非TF）等均不得作为 transcription_factor，仅提取真正的转录因子（如 SP1、TP53、ZBTB10 等）。
4. 【忽略文末参考文献部分】：只抽取正文、图表标题和图注中的调控关系，跳过 References/Bibliography/文献列表等引用部分的内容。
5. 基因名一律用 HGNC 官方 symbol（如 VEGF 写作 VEGFA），统一大小写。
6. 【只抽直接调控】：只抽转录因子直接结合靶基因启动子/直接转录调控的关系；不得把经由中间因子的间接、下游效应当作直接关系。反例：ZBTB10 抑制 Sp1、Sp1 激活 VEGF——不可写成 "ZBTB10 抑制 VEGF"。
7. 【排除预测/in-silico 关系】：排除来自数据库预测、in-silico 分析（如 HaploReg 预测的 TF 结合位点、"该区域与 N 个转录因子互作"）的关系；只保留有实验证据或文献明确陈述的因果调控。
8. 【方向与主客体】：ZBTB10 是 Sp1/Sp3/Sp4 的上游抑制因子（ZBTB10→Sp，repression），不要写反；方向无法判定时不要输出该条。基因用具体官方 symbol（VEGFR1=FLT1，VEGFR2=KDR），不要用笼统的 "VEGFR"。
9. 字段（缺失填 "unknown"）：transcription_factor(单个,必须是转录因子), target_gene(单个), regulation_type(activation/repression/dual/unknown), evidence_type(若转引自他文写 "Literature citation" 并判 low), biological_context, auxiliary_proteins(数组，未提及填 "unknown"), confidence(high=本文直接实验; medium=本文间接证据; low=仅文献引用/泛泛陈述), location。
10. 同一对关系合并为一条，保留最完整信息与最高置信度。
11. 输出必须为纯 JSON 数组，不含任何解释或 Markdown 标记。

格式示例：
[
  {{
    "transcription_factor": "TP53",
    "target_gene": "CDKN1A",
    "regulation_type": "activation",
    "evidence_type": "ChIP-seq, Luciferase reporter",
    "biological_context": "Human HCT116, DNA damage",
    "auxiliary_proteins": ["EP300", "CREBBP"],
    "confidence": "high",
    "location": "p.4, Fig.1C-D"
  }}
]
【文献内容】
{pdf_text}
"""

SYS_V4 = '你是一个严谨的分子生物学与生物信息学专家。只依据用户提供的这一篇文献的正文内容，提取"转录因子调控靶基因"关系。不得引入文献之外的数据库知识，不得臆测。'
USER_V4 = """
【提取要求】
1. 仅提取本文明确陈述或提供实验证据的调控关系；不要推测、不要补充外部知识。
2. 【每条关系只能有一个转录因子和一个靶基因】。若一句涉及多个（如 Sp1/Sp3/Sp4 调控 VEGF），必须拆成多条独立关系，禁止写成 "Sp1, Sp3, Sp4" 这种合并形式。
3. 【排除非转录因子作主语的关系】：microRNA、药物、化合物、SNP、lncRNA、circRNA、蛋白质（非TF）等均不得作为 transcription_factor，仅提取真正的转录因子（如 SP1、TP53、ZBTB10 等）。
4. 【忽略文末参考文献部分】：只抽取正文、图表标题和图注中的调控关系，跳过 References/Bibliography/文献列表等引用部分的内容。
5. 基因名一律用 HGNC 官方 symbol（如 VEGF 写作 VEGFA），统一大小写。
6. 【只抽直接调控】：只抽转录因子直接结合靶基因启动子/直接转录调控的关系；不得把经由中间因子的间接、下游效应当作直接关系。反例：ZBTB10 抑制 Sp1、Sp1 激活 VEGF——不可写成 "ZBTB10 抑制 VEGF"。
7. 【排除预测/in-silico 关系】：排除来自数据库预测、in-silico 分析（如 HaploReg 预测的 TF 结合位点、"该区域与 N 个转录因子互作"）的关系；只保留有实验证据或文献明确陈述的因果调控。
8. 【方向与主客体】：ZBTB10 是 Sp1/Sp3/Sp4 的上游抑制因子（ZBTB10→Sp，repression），不要写反；方向无法判定时不要输出该条。基因用具体官方 symbol（VEGFR1=FLT1，VEGFR2=KDR），不要用笼统的 "VEGFR"。
9. 【文档类型判断】：如果整篇文章本质是 GWAS / SNP 关联研究，或纯生物信息学/in-silico 预测（没有任何调控功能实验，只有"某基因区域与若干转录因子结合/互作"这类预测性、列举式陈述），则**不要从中抽取任何 TF→靶基因关系**，对该文返回空数组 []。
10. 字段（缺失填 "unknown"）：transcription_factor(单个,必须是转录因子), target_gene(单个), regulation_type(activation/repression/dual), evidence_type(若转引自他文写 "Literature citation" 并判 low), biological_context, auxiliary_proteins(数组，未提及填 "unknown"), confidence(high=本文直接实验; medium=本文间接证据; low=仅文献引用/泛泛陈述), location。
11. 同一对关系合并为一条，保留最完整信息与最高置信度。
12. 输出必须为纯 JSON 数组，不含任何解释或 Markdown 标记。

格式示例：
[
  {{
    "transcription_factor": "TP53",
    "target_gene": "CDKN1A",
    "regulation_type": "activation",
    "evidence_type": "ChIP-seq, Luciferase reporter",
    "biological_context": "Human HCT116, DNA damage",
    "auxiliary_proteins": ["EP300", "CREBBP"],
    "confidence": "high",
    "location": "p.4, Fig.1C-D"
  }}
]
【文献内容】
{pdf_text}
"""

PROMPTS = {"v1": (SYS_V1, USER_V1), "v2": (SYS_V2, USER_V2), "v3": (SYS_V3, USER_V3), "v4": (SYS_V4, USER_V4)}


def stage_extract(prompt_version, limit=None):
    if not API_KEY:
        raise ValueError("DASHSCOPE_API_KEY 环境变量未设置，无法执行抽取")

    pdfs = sorted(PDF_DIR.glob("*.pdf"))
    if not pdfs:
        raise ValueError("实例文献/ 下无 PDF 文件，无法执行抽取")

    try:
        from openai import OpenAI
        import fitz
    except ImportError as e:
        raise ImportError(f"缺少依赖：{e}，无法执行抽取")

    json_path = get_json_path(prompt_version)
    if json_path.exists() and not (PDF_DIR / f"extraction_results_{prompt_version}.baseline.json").exists():
        baseline_path = PDF_DIR / f"extraction_results_{prompt_version}.baseline.json"
        shutil.copy(str(json_path), str(baseline_path))
        print(f"已备份基线文件: {json_path} -> {baseline_path}")

    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

    def extract_text_from_pdf(pdf_path):
        doc = fitz.open(str(pdf_path))
        text = "".join(p.get_text() for p in doc)
        doc.close()
        return text.strip()

    def parse_json_array(raw):
        raw = re.sub(r"```(?:json)?|```", "", raw).strip()
        try:
            d = json.loads(raw)
        except json.JSONDecodeError:
            m = re.search(r"\[.*\]", raw, re.DOTALL)
            d = json.loads(m.group(0)) if m else []
        if isinstance(d, dict):
            d = d.get("relations", [d])
        return d if isinstance(d, list) else [d]

    def call_model(pdf_text):
        sys_p, user_t = PROMPTS[prompt_version]
        full_text = user_t.format(pdf_text=pdf_text[:50000])
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "system", "content": sys_p},
                      {"role": "user", "content": full_text}],
            temperature=0.1, max_tokens=8192,
            response_format={"type": "json_object"},
            stream=True,
        )
        content = ""
        for chunk in response:
            if chunk.choices[0].delta.content:
                content += chunk.choices[0].delta.content
        return parse_json_array(content)

    def process_one_pdf(pdf_path):
        print(f"  正在处理 {pdf_path.name}...")
        start_time = time.time()
        
        read_start = time.time()
        txt = extract_text_from_pdf(pdf_path)
        read_time = time.time() - read_start
        
        if not txt:
            elapsed = time.time() - start_time
            print(f"  {pdf_path.name}: 空文本 | 耗时 {elapsed:.1f}s")
            return {"pdf_file": pdf_path.name, "pdf_path": str(pdf_path), "status": "empty_text", "relation_count": 0, "relations": []}
        
        call_start = time.time()
        rels = call_model(txt)
        call_time = time.time() - call_start
        
        elapsed = time.time() - start_time
        print(f"  {pdf_path.name}: 抽到 {len(rels)} 条 / 总耗时 {elapsed:.1f}s (读PDF {read_time:.1f}s, 调用 {call_time:.1f}s)")
        return {"pdf_file": pdf_path.name, "pdf_path": str(pdf_path), "status": "ok", "relation_count": len(rels), "relations": rels}

    print(f"找到 {len(pdfs)} 个 PDF，用模型 {MODEL_NAME} + prompt {prompt_version} 抽取…")
    if limit:
        pdfs = pdfs[:limit]
        print(f"限制只处理前 {limit} 篇")
    results = []
    success_count = 0
    fail_count = 0
    total_relations = 0
    for p in pdfs:
        try:
            res = process_one_pdf(p)
            if res['status'] == 'ok':
                success_count += 1
            elif res['status'] == 'failed':
                fail_count += 1
            total_relations += res['relation_count']
        except Exception as e:
            fail_count += 1
            res = {"pdf_file": p.name, "pdf_path": str(p), "status": "failed", "relation_count": 0, "relations": [], "error": str(e)}
            print(f"  {p.name}: 失败 {e}")
        results.append(res)

    json_path.write_text(json.dumps(sorted(results, key=lambda x: x["pdf_file"]), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已保存: {json_path}")
    print(f"抽取统计: 成功 {success_count} 篇 / 失败 {fail_count} 篇 / 共 {total_relations} 条关系")


def stage_clean(prompt_version):
    json_path = get_json_path(prompt_version)
    import normalize
    data = json.loads(json_path.read_text(encoding="utf-8"))
    clean = [normalize.clean_doc(d) for d in data if isinstance(d, dict)]
    json_path.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
    before = sum(len(d.get("relations", [])) for d in data)
    after = sum(d["relation_count"] for d in clean)
    self_loop_count = normalize.get_self_loop_count()
    unknown_dir_count = normalize.get_unknown_dir_count()
    print(f"清洗完成: {before} -> {after} 条（多实体已拆开、已去重）")
    if self_loop_count > 0:
        print(f"丢弃自环（TF==target_gene）: {self_loop_count} 条")
    if unknown_dir_count > 0:
        print(f"丢弃方向未知（regulation_type=unknown）: {unknown_dir_count} 条")


def stage_build(prompt_version):
    json_path = get_json_path(prompt_version)
    import json_sqlite_store as store
    counts = store.rebuild_database(json_path=json_path, db_path=DB_PATH)
    print(f"已建库: {counts}")


def stage_evaluate(prompt_version):
    json_path = get_json_path(prompt_version)
    import evaluate
    pred, by_pdf = evaluate.load_predicted(json_path)
    gold = evaluate.load_gold(GOLD_CSV)
    tp, fp, fn = pred & gold, pred - gold, gold - pred
    P = len(tp) / len(pred) if pred else 0.0
    R = len(tp) / len(gold) if gold else 0.0
    F1 = 2 * P * R / (P + R) if P + R else 0.0

    print(f"\n===== [{prompt_version}] 整体指标 =====")
    print(f"预测三元组 {len(pred)} | 金标准 {len(gold)} | 命中 TP {len(tp)}")
    print(f"Precision(提的准) = {P:.3f}")
    print(f"Recall   (提的全) = {R:.3f}")
    print(f"F1               = {F1:.3f}")

    print(f"\n===== [{prompt_version}] FP 假阳性 / 疑似幻觉（precision 低就查这里）=====")
    for i, t in enumerate(sorted(fp)[:30], 1):
        print(f"  {i}. {t}")
    if len(fp) > 30:
        print(f"  ... 还有 {len(fp) - 30} 条")

    print(f"\n===== [{prompt_version}] FN 漏抽（recall 低就查这里）=====")
    for i, t in enumerate(sorted(fn)[:20], 1):
        print(f"  {i}. {t}")
    if len(fn) > 20:
        print(f"  ... 还有 {len(fn) - 20} 条")

    print(f"\n===== [{prompt_version}] 每篇 PDF 命中情况 =====")
    for pdf in sorted(by_pdf):
        print(f"  {pdf}: 抽到 {len(by_pdf[pdf])} 条, 命中金标准 {len(by_pdf[pdf] & gold)} 条")

    import csv
    new = not RUNS_LOG.exists()
    with open(RUNS_LOG, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["time", "tag", "pred", "gold", "TP", "FP", "FN",
                        "precision", "recall", "f1"])
        w.writerow([datetime.now().strftime("%Y-%m-%d %H:%M"), prompt_version,
                    len(pred), len(gold), len(tp), len(fp), len(fn),
                    f"{P:.3f}", f"{R:.3f}", f"{F1:.3f}"])
    print(f"\n已记录到 runs_log.csv（tag={prompt_version}）")


def main():
    ap = argparse.ArgumentParser(description="转录因子调控关系抽取流水线")
    ap.add_argument("--prompt-version", default="v1", choices=["v1", "v2", "v3", "v4"],
                    help="Prompt 版本：v1(原版) / v2(改进版) / v3(加强版) / v4(文档类型判断版)")
    ap.add_argument("--stage", default="all",
                    choices=["extract", "clean", "build", "evaluate", "all"],
                    help="运行阶段")
    ap.add_argument("--limit", type=int, default=None,
                    help="限制处理的PDF数量（用于测试）")
    args = ap.parse_args()

    stages = []
    if args.stage == "all":
        stages = ["extract", "clean", "build", "evaluate"]
    else:
        stages = [args.stage]

    print(f"Pipeline 启动: prompt_version={args.prompt_version}, stages={stages}, model={MODEL_NAME}")

    for stage in stages:
        print(f"\n--- [{stage}] ---")
        if stage == "extract":
            stage_extract(args.prompt_version, limit=args.limit)
        elif stage == "clean":
            stage_clean(args.prompt_version)
        elif stage == "build":
            stage_build(args.prompt_version)
        elif stage == "evaluate":
            stage_evaluate(args.prompt_version)

    print("\nPipeline 完成")


if __name__ == "__main__":
    main()
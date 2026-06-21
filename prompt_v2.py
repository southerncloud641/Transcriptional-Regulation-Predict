# prompt_v2.py
# 用法：把下面两段字符串复制进 1.ipynb 的 Cell 5，替换原来的
#       SYSTEM_PROMPT 和 USER_PROMPT_TEMPLATE，然后重跑 Cell 5 产出新一版结果。
#
# v2 相对示例(v1)改了什么、为什么改（这些理由要写进报告的“迭代”部分）：
#   1) 强制【单实体】：v1 抽出了 "Sp1, Sp3, Sp4"、"Sp1/Sp3/Sp4" 这种多实体串，
#      导致统计/检索失真。v2 要求每条只写一个 TF + 一个靶基因，多个就拆成多条。
#   2) 强制【官方基因符号】：v1 里 VEGF/VEGFA、SP1/Sp1 混用。v2 要求用 HGNC 标准符号。
#   3) 收紧【置信度判定】：v1 把“别处文献引用”的关系也大量输出。v2 明确区分
#      “本文实验验证”(high) 与 “转引自他文”(low)，并要求 evidence_type 注明来源，
#      减少把综述性引用当成本文发现的假阳性。

SYSTEM_PROMPT = """你是一个严谨的分子生物学与生物信息学专家。\
只依据用户提供的这一篇文献的正文内容，提取“转录因子调控靶基因”关系。\
不得引入文献之外的数据库知识，不得臆测。"""

USER_PROMPT_TEMPLATE = """
【提取要求】
1. 仅提取本文明确陈述或提供实验证据的调控关系；不要推测、不要补充外部知识。
2. 【每条关系只能有一个转录因子和一个靶基因】。若原文一句话涉及多个（如 Sp1/Sp3/Sp4
   调控 VEGF），必须拆成多条独立关系，禁止写成 "Sp1, Sp3, Sp4" 这种合并形式。
3. 基因名一律使用 HGNC 官方 symbol（例如 VEGF 写作 VEGFA，统一大小写），不要用别名混写。
4. 每条关系输出以下字段（缺失填 "unknown"）：
   - transcription_factor: 单个转录因子（官方 symbol）
   - target_gene: 单个靶基因（官方 symbol）
   - regulation_type: activation / repression / dual / unknown
   - evidence_type: 实验证据类型（如 ChIP-seq, EMSA, Luciferase, RNA-seq after KO/OE）；
     若该关系是【转引自其他文献】而非本文实验，请写 "Literature citation" 并据此判 low
   - biological_context: 物种、细胞系/组织、处理条件
   - auxiliary_proteins: 明确提及的共激活子/共抑制子/协同因子等（数组；未提及填 "unknown"，不要推测）
   - confidence: high=本文有直接实验（如 ChIP+报告基因+敲低/过表达）；medium=本文有间接证据；
     low=仅文献引用/泛泛陈述、本文无直接实验
   - location: 页码/图表编号
5. 同一对关系多次出现，合并为一条，保留最完整信息与最高置信度。
6. 输出必须为纯 JSON 数组，不含任何解释、前言或 Markdown 标记。

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

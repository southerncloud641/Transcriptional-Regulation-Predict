# 转录因子调控关系知识库（改进版项目）

老师示例只抽取了一次、没评估、没优化。本项目在其上补全了
「评估 → 改 prompt → 重测 → 记录指标」闭环。

详细操作（含 Windows + VS Code 设置）见 **HOWTO_windows.md**。

文件作用速查：
- 1_improved.ipynb   改进版主流水线（内置 v1/v2 prompt 切换 + 评估）
- json_sqlite_store.py / extraction.sqlite3   灌库 / 数据库
- app.py / templates/index.html               Flask 网站（app.py 已修好 rebuild 导入 bug）
- evaluate.py        评估：P/R/F1 + FP/FN + 记录 runs_log.csv
- normalize.py       清洗：拆多实体 / 统一符号 / 去重
- gold_standard.csv  金标准（需你人工补全）
- 实例文献/          放 8 篇 PDF 和 extraction_results.json

最短跑通（已有 extraction_results.json，无需联网）：
    pip install -r requirements.txt
    # 打开 1_improved.ipynb，依次跑 ④清洗 ⑤建库 ⑥评估
    python app.py        # 看网站

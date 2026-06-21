# 在 Windows + VS Code 上跑通并改进（操作指南）

老师给的示例只做到“抽取一次”，没评估、没优化。你的任务是**在它基础上跑完
“评估 → 改 prompt → 重抽 → 记录指标”这个闭环**。下面全部按 Windows + VS Code 写。

---

## 一、能不能只用 VS Code？—— 能。

VS Code 同时能跑 `.py` 脚本和 `.ipynb` notebook，一个软件搞定。装这些：

1. **Python**：去 python.org 下 3.11，安装时**勾选 “Add python.exe to PATH”**。
2. **VS Code** + 两个扩展：在扩展市场搜 **Python**（Microsoft）和 **Jupyter**，都装上。
3. 用 VS Code **打开项目文件夹**（File → Open Folder，选下面那个目录结构的根目录）。

### 建虚拟环境 + 装依赖（在 VS Code 底部的终端里）
终端默认是 PowerShell。依次输入：
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```
> 如果第二行报“无法加载…执行策略”，先跑一次：
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`，再激活；
> 或者改用 cmd 终端，命令是 `.\.venv\Scripts\activate.bat`。

激活后行首会出现 `(.venv)`。然后装库：
```powershell
pip install biopython openai pdfplumber flask requests mygene
```

### 怎么运行
- **`.py` 脚本**（evaluate.py / normalize.py / app.py）：在终端 `python evaluate.py`，
  或点右上角的 ▶ Run。
- **`1.ipynb`**：在 VS Code 里打开它 → 右上角 **选择内核(Select Kernel)** → 选 `.venv` →
  逐个 cell 点左边的 ▶ 运行。
- **网站**：`python app.py`，终端会显示 `http://127.0.0.1:5000`，按住 Ctrl 点它打开。

---

## 二、各文件的作用（先认门）

| 文件 | 作用 | 你要不要动 |
|---|---|---|
| `1.ipynb` | 主流水线：取文献→调 API→抽取成 JSON | **要改**（Cell 5 的路径/key/prompt） |
| `extraction_results.json` | 抽取结果（8 篇 / 33 条），网站的数据源 | 重抽后会被覆盖 |
| `json_sqlite_store.py` | 把 JSON 灌进 SQLite（两表+索引+raw_json） | 一般不动 |
| `extraction.sqlite3` | 数据库文件，网站从这里读 | 自动生成 |
| `app.py` | Flask 后端：检索/分页/统计/重建 | 一般不动 |
| `index.html` | 网站页面（**必须放在 `templates/` 子文件夹**） | 一般不动 |
| `evaluate.py` 🆕 | 评估：算 Precision/Recall/F1，列 FP/FN，记录指标 | 用它，不用改 |
| `normalize.py` 🆕 | 清洗：拆多实体、统一基因符号、去重 | 用它 |
| `prompt_v2.py` 🆕 | 改进版 prompt，粘贴进 Cell 5 做第 2 轮 | 用它 |
| `gold_standard.csv` 🆕 | 金标准（评估的“标准答案”） | **要自己补全** |

### 目录结构（按 `json_sqlite_store.py` 的约定摆好）
```
项目根目录/
├── app.py
├── json_sqlite_store.py
├── evaluate.py  normalize.py  prompt_v2.py  gold_standard.csv   ← 新增的放这层
├── 1.ipynb
├── extraction.sqlite3            ← 自动生成
├── templates/
│   └── index.html               ← index.html 必须在这里，否则 Flask 找不到
└── 实例文献/
    ├── 1.pdf … 8.pdf            ← 8 篇 PDF 放这
    └── extraction_results.json  ← 抽取结果放这
```
> ⚠️ 两个易错点：
> ① `index.html` 必须在 `templates/` 里（Flask 规矩）。
> ② notebook Cell 5 默认把结果存成 `ZBTB10_extraction_results.json`，而
> `json_sqlite_store.py` 读的是 `extraction_results.json`——重抽后记得**改文件名对上**，
> 或把 Cell 5 的 `OUTPUT_JSON` 改成 `extraction_results.json`。

---

## 三、优化闭环：每一步改哪个文件、跑什么

### 第 0 步 · 先让示例能在你机器上跑起来
打开 `1.ipynb` 的 **Cell 5**，改 3 处：
- `API_KEY = "你的百炼key"`（建议用环境变量，别提交真 key）
- `PDF_DIR = Path(r"你电脑上放 8 篇 PDF 的真实路径")`
- `OUTPUT_JSON = PDF_DIR / "extraction_results.json"`（统一成这个名字）

> `Cell 1`（PubMed 检索）是坏的（`my_tfs` 空、`alias_dict` 未定义、残留了
> `Cell="GM12878"`），而且 8 篇 PDF 本来就是手动下的——**把 Cell 1 注释掉**，
> 报告里写明“文献人工检索下载”即可。

跑 Cell 4（测 API 通不通）→ 跑 Cell 5（产出 `extraction_results.json`）。

### 第 1 步 · 做金标准（评估的前提，最花时间但最重要）
把 8 篇 PDF **完整读一遍**，逐条把真实的 (TF, 靶基因, 方向) 填进 `gold_standard.csv`。
列固定为 `transcription_factor,target_gene,regulation_type`。
> 关键：金标准要**尽量覆盖这 8 篇里的所有真实关系**，否则 precision 会被假性压低。
> 我给的 `gold_standard.csv` 只是 8 条种子示例，**必须你自己扩充**。
> 另：TRRUST 数据库里没有 ZBTB10，所以这一步只能靠人工——这点写进报告（正是课题立意）。

### 第 2 步 · 评估基线（v1）
```powershell
python normalize.py --in 实例文献\extraction_results.json --out 实例文献\extraction_results.json
python evaluate.py --pred 实例文献\extraction_results.json --gold gold_standard.csv --tag v1
```
看 Precision / Recall / F1，以及 **FP 清单**（疑似幻觉）和 **FN 清单**（漏抽）。
`--tag v1` 会把这一行指标写进 `runs_log.csv`。

### 第 3 步 · 据 FP/FN 改 prompt（v2）→ 重抽
打开 `prompt_v2.py`，把里面的 `SYSTEM_PROMPT` 和 `USER_PROMPT_TEMPLATE` 复制进
`1.ipynb` Cell 5，**替换**原来那两段。v2 主要改了三点（理由写进报告）：
- 强制每条只一个 TF + 一个靶基因（解决 "Sp1, Sp3, Sp4" 合并问题）；
- 强制 HGNC 官方符号（解决 VEGF/VEGFA、SP1/Sp1 混用）；
- 收紧置信度：把“转引自他文”的关系明确判 low，减少把综述引用当本文发现的假阳性。

重跑 Cell 5 → 重新 normalize → 再评估并打 v2 标签：
```powershell
python evaluate.py --pred 实例文献\extraction_results.json --gold gold_standard.csv --tag v2
```

### 第 4 步 · 看指标变化
```powershell
type runs_log.csv
```
你会得到类似这样的对比表，**这就是“记录指标变化”要交的东西**：
```
tag  pred gold TP FP FN precision recall f1
v1   38   25   22 16  3  0.579   0.880  0.698
v2   31   25   23  8  2  0.742   0.920  0.823
```
（数字仅示意；真实值取决于你的金标准和 prompt）报告里就讨论：v2 为什么 precision 升了、
还有哪些 FP/FN 没解决。

### 第 5 步 · 重建库 + 起网站 + 截图
```powershell
python app.py
```
浏览器打开 `http://127.0.0.1:5000`，点“重建数据库”，截图放报告。

---

## 四、报告要点（评分锚点）
1. 方法：取文献(人工) → prompt → 抽取 → 清洗 → 落库 → 网站。
2. 评估：v1 的 Precision/Recall/F1 + FP/FN 错误分析。
3. **迭代**：v1→v2 改了哪几句 prompt、为什么改、指标怎么变（贴 `runs_log.csv`）。
4. 局限：金标准不全 / TRRUST 无 ZBTB10 / 数据归一化 / 长文本分块未做。

## 交付清单
- [ ] `1.ipynb`（Cell 1 注释、key 用环境变量、Cell 5 用 v2 prompt）
- [ ] `extraction_results.json`（v2 抽取 + 清洗后）
- [ ] `gold_standard.csv`（自己补全的）
- [ ] `runs_log.csv`（v1 vs v2 指标对比）
- [ ] 网站截图
- [ ] 报告（含上面四点）

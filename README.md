# LitRecombine

基于文献结构化提取与跨论文重组的研究方向生成工具。

---

## 项目简介

传统做法通常是先凭直觉提出研究方向，再去文献中寻找支持依据。这种方式容易出现两个问题：

- 方向缺乏明确文献证据支撑
- 提出的方向与已有工作重复，但自己没有及时发现

`LitRecombine` 的思路是把顺序倒过来：

1. 先从已有论文中提取结构化模块
2. 再基于这些模块做跨论文重组
3. 最终生成可追溯到原始文献的候选研究方向

这样生成的每个候选方向，都可以追踪到具体来源论文，而不是"无依据地产生一个想法"。

---

## 功能概览

项目当前实现的是一个本地 `Streamlit` 工作流，包含四个阶段：

1. 文献收集
2. 结构化提取
3. 重组生成
4. 候选评估

其中：

- PDF 文本提取由本地脚本完成
- 六模块提取通过 DeepSeek API 完成
- 重组步骤仍然是人工把整理后的输入提交给 Claude
- 候选解析与评估记录回到本地应用中完成

---

## 环境要求

- Python 3.10 及以上
- DeepSeek API Key

---

## 安装

```bash
pip install -r requirements.txt
```

测试套件需要额外安装 pytest：

```bash
pip install pytest
```

---

## 配置

复制配置模板并填写 DeepSeek API Key：

```bash
cp config.yaml.example config.yaml
```

然后编辑 `config.yaml`：

```yaml
deepseek:
  api_key: "YOUR_DEEPSEEK_API_KEY"
```

所有配置均集中在 `config.yaml`，包括：

| 配置块 | 内容 |
|--------|------|
| `deepseek` | API Key、模型选择、max_tokens、temperature |
| `extraction.modules` | 六个提取模块定义 |
| `filters` | Stage 3 硬性筛选条件 |
| `chunking` | 长文分块参数（见下） |
| `paths` | projects 与 module_pool 目录 |

### 分块参数（`chunking`）

```yaml
chunking:
  max_tokens: 12000         # 每个 chunk 的 token 上限（估算值）
  overlap_tokens: 500       # 相邻 chunk 的重叠 token 数
  chars_per_token: 2.5      # 英文主导论文用 2.5；中英混合用 2.0
  min_paragraph_tokens: 50  # 短于此值的段落会与下一段合并
```

模型建议：

- `deepseek-chat`：默认，速度快、成本低，适合稳定结构化抽取
- `deepseek-reasoner`：推理更强，适合边界模糊、需要深度理解的论文；可在 `chunking.max_tokens` 调至 `20000`

---

## 启动方式

```bash
streamlit run app.py
```

应用启动后会打开本地网页界面。如果 `config.yaml` 缺少必填字段，界面会显示红色错误提示。

---

## 运行测试

```bash
python -m pytest tests/ -v
```

---

## 目录结构

```text
LitRecombine/
├── app.py                        # Streamlit 主入口
├── config.yaml.example           # 配置模板（复制为 config.yaml 后使用）
├── requirements.txt
├── README.md
├── README_en.md
├── research_direction_workflow.md
├── scripts/
│   ├── extract_text.py           # Stage 2a：PDF → JSON 全文提取
│   ├── extract_modules.py        # Stage 2b：六模块提取（支持长文分块）
│   ├── format_consolidated.py    # Stage 2c：合并 per-paper 提取结果
│   └── parse_candidates.py       # Stage 4a：解析 Claude 输出为候选文件
├── tests/
│   ├── test_chunking.py          # 分块函数单元测试
│   └── test_parse_candidates.py  # 候选解析正则单元测试
├── module_pool/
│   ├── core_method/
│   ├── experimental_scenario/
│   ├── unresolved_questions/
│   ├── acknowledged_limitations/
│   ├── evaluation_metrics/
│   └── measurement_instruments/
└── projects/                     # 每次 run 的输出（不纳入版本控制）
    └── YYYY-MM-DD_HHMMSS[_label]/
        ├── papers/
        ├── extracted_text/
        ├── module_extractions/
        └── candidates/
```

---

## 工作流说明

### Stage 1：文献收集

在首页创建一个新的 run，可以输入自定义标签，也可以只使用自动生成的时间戳。

应用会创建当前 run 的目录结构，并提供打开 `papers/` 文件夹的按钮。把待分析的 PDF 放入 `papers/` 目录即可。

建议每次收集约 10 篇论文，便于控制提取成本与后续重组复杂度。

---

### Stage 2：结构化提取

#### 2a：PDF 全文提取

将每篇 PDF 提取为 JSON 文件，保存到 `extracted_text/`。JSON 中包含完整文本与逐页备份。

若 PDF 为扫描版（无可提取文字），提取后会打印 `[warn]` 提示，JSON 中会写入 `"error": "empty_text"` 字段，后续步骤会自动跳过该文件。

#### 2b：六模块提取

对每篇论文提取以下六个模块：

1. Core Innovation
2. Application Scenario
3. Future Research Directions
4. Acknowledged Limitations
5. Evaluation Metrics
6. Experimental Measurement Methods

每篇论文输出一个 Markdown 文件，保存在 `module_extractions/`。

**长文处理**：论文超过 token 预算时，会自动按四级边界切分（空行 → 句末换行 → 强制截断），对每个 chunk 单独提取，最后做一次合并。所有分块参数均可在 `config.yaml` 的 `chunking:` 块中调整。

**API 容错**：每次 API 调用最多自动重试 3 次（间隔 2/4/8 秒）。若仍失败，会写入 `{paper_id}_extraction_FAILED.md` 作为失败标记，并继续处理其余论文。

#### 2c：合并提取结果

将所有 per-paper 提取结果合并为 `module_extractions/consolidated_extractions.md`，按"模块"而非"论文"组织，便于 Stage 3 的横向比较。

若存在 `_FAILED.md` 标记文件，合并时会打印警告并自动跳过对应论文。

若 `module_pool/` 下有历史高质量模块文本，界面会允许按模块逐项选择纳入。

---

### Stage 3：研究方向重组

在 Stage 3 中：

1. 下载 `consolidated_extractions.md`
2. 复制界面中给出的重组提示词
3. 将两者一起提交给 Claude

#### 当前硬性筛选条件

重组提示词中包含以下硬性过滤（可在 `config.yaml` 的 `filters:` 中修改）：

- Measurement Instruments 至少包含以下之一：
  - eye tracking
  - heart rate measurement
  - head movement tracking
  - hand movement tracking
  - validated self-report questionnaires
- Measurement Instruments 不能包含 CAVE
- 参与者不能涉及临床人群或已确诊疾病个体

---

### Stage 4：候选解析与评估

#### 4a：候选解析

将 Claude 输出全文粘贴回界面，应用会：

- 保存原始文本到 `candidates/candidates_raw.md`
- 拆分为多个候选文件：`candidate_001.md`、`candidate_002.md`……

解析器支持以下标题格式：

| 格式 | 示例 |
|------|------|
| 加粗带括号 | `**Candidate [1]**` |
| 加粗不带括号 | `**Candidate 1**` |
| Markdown 标题 | `## Candidate 1`、`### Candidate 1` |
| 冒号结尾 | `Candidate 1:` |

#### 4b：评估记录

候选生成后，界面为每个候选提供 Decision 与 Rationale 字段，保存到 `candidates/evaluation_record.md`。

#### 4c：将评估记录作为后续输入

多次运行后，可以把历史 `evaluation_record.md` 再提交给 Claude，作为优化六模块设计、重组提示词或候选筛选策略的参考。

---

## Module Pool 用法

`module_pool/` 是跨 run 的模块复用池。把历史运行中质量较高的模块文本手动放入对应子目录，在 Stage 2c 中即可按模块逐项选择纳入当前合并文件。被纳入的内容会以 `[pool]` 标记显示。

---

## 注意事项

- PDF 提取质量依赖 PDF 是否含可选文本；扫描版需先 OCR
- Stage 2a 与 Stage 2b 默认跳过已存在的输出文件，避免重复处理
- Stage 4a 重新解析时，会删除旧的 `candidate_*.md` 并写入新的结果
- DeepSeek 调用会产生 token 成本，建议在控制台设置额度上限
- Stage 3 目前仍需手动提交给 Claude，尚未自动化

---

## 相关文档

- [research_direction_workflow.md](research_direction_workflow.md)：设计说明与工作流定义

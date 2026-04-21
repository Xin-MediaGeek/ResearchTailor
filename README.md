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

这样生成的每个候选方向，都可以追踪到具体来源论文，而不是“无依据地产生一个想法”。

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

在项目根目录执行：

```bash
pip install -r requirements.txt
```

---

## 配置

打开 [config.yaml](E:\Xin_Tool\ResearchTailor\config.yaml)，填写 DeepSeek API Key：

```yaml
deepseek:
  api_key: "YOUR_DEEPSEEK_API_KEY"
```

其余配置也都集中在 `config.yaml` 中，包括：

- DeepSeek 模型与参数
- 六个提取模块定义
- Stage 3 中使用的硬性筛选条件
- 项目目录与模块池目录

当前默认配置中：

- `model: deepseek-chat`
- `max_tokens: 4096`

一般建议：

- `deepseek-chat` 作为默认提取模型，更快、更便宜，也更适合稳定结构化抽取
- `deepseek-reasoner` 适合模块边界更模糊、需要更强推理时使用

---

## 启动方式

在项目根目录执行：

```bash
streamlit run app.py
```

应用启动后会打开本地网页界面。

---

## 目录结构

```text
LitRecombine/
├── app.py
├── config.yaml
├── requirements.txt
├── README.md
├── research_direction_workflow.md
├── scripts/
│   ├── extract_text.py
│   ├── extract_modules.py
│   ├── format_consolidated.py
│   └── parse_candidates.py
├── module_pool/
│   ├── core_method/
│   ├── experimental_scenario/
│   ├── unresolved_questions/
│   ├── acknowledged_limitations/
│   ├── evaluation_metrics/
│   └── measurement_instruments/
└── projects/
    └── YYYY-MM-DD_HHMMSS_label/
        ├── papers/
        ├── extracted_text/
        ├── module_extractions/
        └── candidates/
```

说明：

- `projects/` 用于存放每一次运行的完整结果
- 每次新建 run 时，目录名格式为 `YYYY-MM-DD_HHMMSS[_label]`
- `module_pool/` 用于跨 run 复用高质量模块文本

---

## 工作流说明

### Stage 1：文献收集

在首页创建一个新的 run，可以输入自定义标签，也可以只使用自动生成的时间戳。

应用会：

- 创建当前 run 的目录结构
- 提供打开 `papers/` 文件夹的按钮

你需要把待分析的 PDF 放入当前 run 的 `papers/` 目录中。

建议每次收集约 10 篇论文，便于控制提取成本与后续重组复杂度。

---

### Stage 2：结构化提取

Stage 2 分为三个步骤。

#### 2a：PDF 全文提取

运行 [scripts\extract_text.py](E:\Xin_Tool\ResearchTailor\scripts\extract_text.py) 后，会把每篇 PDF 提取为一个 JSON 文件，保存到：

- `extracted_text/`

输出示例：

- `paper01_fulltext.json`

这些 JSON 用作后续处理备份，不是面向人工阅读的主文件。

#### 2b：六模块提取

运行 [scripts\extract_modules.py](E:\Xin_Tool\ResearchTailor\scripts\extract_modules.py) 后，会把每篇论文提取成六个模块：

1. Core Innovation
2. Application Scenario
3. Future Research Directions
4. Acknowledged Limitations
5. Evaluation Metrics
6. Experimental Measurement Methods

每篇论文会输出一个 Markdown 文件，保存在：

- `module_extractions/`

当前 Stage 2b 界面中可以直接选择提取模型：

- `deepseek-chat`
- `deepseek-reasoner`

无需再手动修改 `config.yaml` 才能切换模型。

如果论文较长，当前实现不会再“直接截断前 60000 字符”。而是：

1. 将全文按长度切成多个重叠 chunk
2. 对每个 chunk 单独提取模块
3. 再将 chunk 级结果做一次合并

这样可以降低遗漏论文后半部分信息的风险，尤其是：

- limitations
- unresolved questions
- evaluation metrics

#### 2c：合并提取结果

运行 [scripts\format_consolidated.py](E:\Xin_Tool\ResearchTailor\scripts\format_consolidated.py) 后，会把所有 per-paper 提取结果合并成：

- `module_extractions/consolidated_extractions.md`

这个文件按“模块”组织，而不是按“论文”组织，便于后续在同一模块下横向比较不同论文内容。

当前输出格式示例：

```md
# Consolidated Extractions

Papers included: paper01, paper02

---
## Module: Core Innovation

**[paper01]**
...

**[paper02]**
...
```

如果 `module_pool/` 下已有历史高质量模块文本，界面会允许你：

- 按模块查看可用文件
- 逐项选择要纳入本次 run 的 pool 条目

不会再像之前那样只能“全选全部 pool 文件”。

---

### Stage 3：研究方向重组

在 Stage 3 中，你需要：

1. 下载 `consolidated_extractions.md`
2. 复制界面中给出的重组提示词
3. 将两者一起提交给 Claude

当前界面中的提示词使用原生文本框显示，推荐直接：

- 选中文本
- 使用 `Ctrl+C` / `Cmd+C` 手动复制

不再依赖不稳定的浏览器脚本复制方案。

#### 当前硬性筛选条件

重组提示词中包含以下硬性过滤：

- Measurement Instruments 至少包含以下之一：
  - eye tracking
  - heart rate measurement
  - head movement tracking
  - hand movement tracking
  - validated self-report questionnaires
- Measurement Instruments 不能包含 EEG
- 参与者不能涉及临床人群或已确诊疾病个体

---

### Stage 4：候选解析与评估

#### 4a：候选解析

将 Claude 输出全文粘贴回界面后，应用会：

- 保存原始文本到 `candidates/candidates_raw.md`
- 自动拆分为多个候选文件：
  - `candidate_001.md`
  - `candidate_002.md`
  - ...

当前解析器支持两种标题格式：

- `**Candidate [1]**`
- `**Candidate 1**`

#### 4b：评估记录

候选生成后，界面会为每个候选提供：

- Decision
- Rationale

并保存到：

- `candidates/evaluation_record.md`

结构示例：

```md
## Candidate 001
- Decision: Keep
- Rationale: ...
```

#### 4c：将评估记录作为后续输入

多次运行之后，可以把历史 `evaluation_record.md` 再提交给 Claude，作为后续优化以下内容的参考：

- 六模块设计
- 重组提示词
- 候选筛选策略

---

## Module Pool 用法

`module_pool/` 是一个跨 run 的模块复用池。

你可以把历史运行中质量较高的模块文本，手动放入对应子目录，例如：

- `module_pool/core_method/`
- `module_pool/experimental_scenario/`
- `module_pool/unresolved_questions/`

在 Stage 2c 中，界面会显示这些 pool 文件，并允许你逐项选择纳入当前合并文件。

被纳入的 pool 内容会在合并文件中以 `[pool]` 标记显示。

---

## 关键脚本说明

- [app.py](E:\Xin_Tool\ResearchTailor\app.py)
  - Streamlit 主入口
  - 串联四个阶段的界面流程

- [scripts\extract_text.py](E:\Xin_Tool\ResearchTailor\scripts\extract_text.py)
  - PDF 转 JSON 全文备份

- [scripts\extract_modules.py](E:\Xin_Tool\ResearchTailor\scripts\extract_modules.py)
  - 调用 DeepSeek 做六模块提取
  - 长文按 chunk 提取并合并
  - 支持通过界面切换 `deepseek-chat` / `deepseek-reasoner`

- [scripts\format_consolidated.py](E:\Xin_Tool\ResearchTailor\scripts\format_consolidated.py)
  - 合并 per-paper 模块结果
  - 支持按模块逐项选择 `module_pool` 文件

- [scripts\parse_candidates.py](E:\Xin_Tool\ResearchTailor\scripts\parse_candidates.py)
  - 将 Claude 输出拆分为单独候选文件
  - 支持 `Candidate [N]` 与 `Candidate N`

---

## 注意事项

- PDF 提取质量依赖 PDF 是否为可复制文本的版本；扫描版通常需要先 OCR
- Stage 2a 与 Stage 2b 默认会跳过已经存在的输出文件，避免重复处理
- Stage 4a 重新解析时，会删除旧的 `candidate_*.md` 并写入新的解析结果
- DeepSeek 调用会产生 token 成本，建议在控制台设置额度上限
- 当前项目仍然要求 Stage 3 手动提交给 Claude，这一步没有自动化

---

## 相关文档

- [research_direction_workflow.md](E:\Xin_Tool\ResearchTailor\research_direction_workflow.md)
  - 更偏设计说明与工作流定义

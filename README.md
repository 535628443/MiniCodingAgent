# MiniCodingAgent 🤖

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Powered by LiteLLM](https://img.shields.io/badge/LLM-Gemini%202.5%20Flash%20Lite%20%7C%20Claude-green.svg)](https://github.com/BerriAI/litellm)

**MiniCodingAgent** 是一个遵循单一职责原则（Single Responsibility Principle, SRP）的轻量级、模块化自主代码代理（Coding Agent）参考架构。

本项目脱胎于对 **Anthropic Claude Code** 核心运作机制的极简复刻与工程化重构，提供了在生产环境中构建 Agent 所需的完整系统切面：**两级技能按需注入**、**多阶段上下文压缩管线**、**分层子代理派发**、**生命周期钩子**、**安全沙箱拦截** 以及 **动态任务状态看板**。

---

## 🌟 核心特性

- **多阶段上下文压缩管线 (Multi-Stage Compaction Pipeline)**:
  - **容量预算控制 (Tool Result Budget)**: 单次大输出自动持久化至本地 `.transcripts/` 磁盘，替换为结构化预览摘要，避免上下文爆炸。
  - **历史裁剪与微压缩 (Snip & Micro-Compact)**: 自动保留头部系统上下文与最近关键步骤，将较早的历史 tool_result 占位压缩。
  - **自动上下文总结 (Auto-Compaction)**: 监测会话总字符量，超限自动调用 LLM 归档会话历史为结构化 Markdown 摘要。
  - **反应式溢出恢复 (Reactive Compaction)**: 智能捕获 `BadRequestError (Prompt Too Long)` 并自动触发压缩重试。
- **两级按需技能注入 (Two-Level On-Demand Skill Injection)**:
  - **Layer 1（目录索引）**: 启动时扫描 `skills/` 目录，仅将技能名称与一句话概要注入 `System Prompt`，大幅节省 Context Window。
  - **Layer 2（知识检索）**: 当模型判断任务需要特定知识时，动态调用 `load_skill` 从内存注册表中拉取完整的标准作业程序（SOP）和知识正文。
- **子代理隔离派发机制 (Subagent Delegation)**:
  - 主代理可调用 `task` 工具派发全新、独立上下文的子代理（Subagent）。
  - 子代理具备独立循环上限与专用工具集（严禁递归生成子代理），在执行完复杂的子任务后仅返回精简摘要，保持主上下文紧凑。
- **全生命周期钩子体系 (Lifecycle Hooks)**:
  - 支持 `UserPromptSubmit`、`PreToolUse`、`PostToolUse`、`Stop` 事件。
  - 内置高危 Shell 命令拦截（如 `rm -rf /`, `sudo` 等防误操作沙箱）。
  - 自动记录工具执行审计日志与会话总耗费工具数统计。
- **动态 Todo 任务看板 (Stateful Task Tracker)**:
  - 具备 `pending` / `in_progress` / `completed` 状态看板与终端彩色格式化输出。
  - 超过指定轮次未更新任务时自动向模型注入催促提醒（Reminder）。
- **统一多模型协议网关 (Multi-Provider LiteLLM Proxy)**:
  - 默认集成 LiteLLM，完美兼容 Google **Gemini 2.5 Flash Lite**、Claude 3.7 Sonnet 等多种大模型。

---

## 📁 目录结构

```text
MiniCodingAgent/
├── MiniCodingAgent/           # Agent 核心包
│   ├── __init__.py           # 包导出声明
│   ├── __main__.py           # 支持 python -m MiniCodingAgent 运行
│   ├── main.py               # CLI 终端交互入口
│   ├── agent.py              # 核心调度驱动循环 (agent_loop)
│   ├── compact.py            # 上下文压缩管线 (Budget, Snip, Micro, Auto, Reactive)
│   ├── config.py             # 环境变量与 LLM Client 初始化
│   ├── state.py              # 全局状态管理 (todos, 催促计数器, 技能缓存)
│   ├── prompts.py            # 系统提示词构建与 Subagent Prompt
│   ├── hooks.py              # 生命周期钩子注册与安全拦截器
│   └── tools/                # 独立工具模块
│       ├── __init__.py       # Tools Schema 与 Handler 查表映射
│       ├── system.py         # 系统操作 (safe_path 越界防护, run_bash)
│       ├── files.py          # 文件读写 (read_file, write_file, edit_file, glob)
│       ├── todo.py           # 任务列表管理 (todo_write)
│       ├── skill.py          # 技能扫描与加载 (scan_skills, load_skill)
│       └── subagent.py       # 子代理驱动器 (spawn_subagent)
├── skills/                   # 外部按需技能库 (SKILL.md)
│   ├── agent-builder/        # Agent 构建与架构指导
│   ├── code-review/          # 代码审查标准与安全性最佳实践
│   ├── mcp-builder/          # MCP 服务器构建指南
│   └── pdf/                  # PDF 提取与分析规范
├── tests/                    # 自动化测试套件
│   ├── test_agent.py         # 核心功能单元测试
│   └── test_full_agent_compaction.py # 全功能与上下文压缩多轮测试
├── .env.example              # 环境变量配置模板
├── litellm_config.yaml       # LiteLLM 模型代理映射配置
├── pyproject.toml            # 项目元数据与依赖定义
└── README.md
```

---

## 🚀 快速上手

### 1. 环境准备

克隆项目并进入目录：
```bash
git clone https://github.com/535628443/MiniCodingAgent.git
cd MiniCodingAgent
```

推荐使用 `uv` 管理虚拟环境与依赖（或使用传统 `venv`）：
```bash
# 使用 uv 一键安装并同步环境 (推荐)
uv sync

# 或使用传统 venv
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env` 并填写 API Key：
```bash
cp .env.example .env
```
编辑 `.env`：
```env
GEMINI_API_KEY=your_actual_gemini_api_key
MODEL_ID=gemini-2.5-flash-lite
ANTHROPIC_BASE_URL=http://localhost:4000
ANTHROPIC_API_KEY=sk-litellm-proxy-key
```

### 3. 启动模型代理服务

在后台或独立终端窗口启动 LiteLLM 代理：
```bash
# 使用 uvx 免手动安装直接运行代理 (推荐)
uvx --from "litellm[proxy]" litellm --config litellm_config.yaml --port 4000

# 或在激活环境后运行
litellm --config litellm_config.yaml --port 4000
```

### 4. 运行 Agent

在项目根目录下，使用 `uv run` 启动交互式命令行客户端：

```bash
# 方式 1: 使用 uv 命令直接运行 CLI (推荐)
uv run mini-coding-agent

# 方式 2: 使用 uv run 执行模块
uv run python -m MiniCodingAgent
```

终端将呈现交互界面：
```text
MiniCodingAgent: Skill Loading — catalog in SYSTEM, content on demand (Modular Edition)
Type a question, press Enter. Type q to quit.

MiniCodingAgent >> 
```

---

## 🧪 运行测试

执行基础功能单元测试：
```bash
uv run python -m unittest tests/test_agent.py
```

执行全功能与压缩机制完整验证（支持三轮连续测试）：
```bash
uv run python tests/test_full_agent_compaction.py
```

---

## 🛠 内置工具一览

| 工具名 | 输入参数 | 职责描述 |
| :--- | :--- | :--- |
| `bash` | `command` | 执行 Shell 脚本（带 120s 超时与危险命令白名单防护） |
| `read_file` | `path`, `limit` | 安全读取文件内容，支持按行截断保护上下文 |
| `write_file` | `path`, `content` | 写入目标文件，自动递归创建父目录 |
| `edit_file` | `path`, `old_text`, `new_text` | 精确单次文本替换 |
| `glob` | `pattern` | 基于工作区根目录检索匹配的文件路径 |
| `todo_write` | `todos` | 维护会话任务清单与看板状态（pending, in_progress, completed） |
| `load_skill` | `name` | **Layer 2 技能加载器**：从内存缓存按需拉取完整 SKILL 指导文本 |
| `task` | `description` | **子代理生成器**：派发具备全新独立上下文的 Subagent 并获取总结报告 |
| `compact` | `{}` | **手动压缩工具**：显式触发当前历史归档与摘要生成，释放上下文空间 |

---

## 📄 License

本项目采用 [MIT License](LICENSE) 开源协议。

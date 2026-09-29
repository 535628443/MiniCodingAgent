# MiniCodingAgent: Skill Loading (模块化重构版)

本项目是 `s07_skill.py` 的工程化模块化拆分版本，遵循单一职责原则（Single Responsibility Principle, SRP），将单文件中的各个系统切面解耦。

## 目录结构

```text
MiniCodingAgent/
├── __init__.py           # 包导出声明
├── __main__.py           # 支持 python -m MiniCodingAgent 运行
├── main.py               # CLI 终端交互入口 (支持 python MiniCodingAgent/main.py)
├── config.py             # 环境变量、工作区路径与 Anthropic Client 初始化
├── state.py              # 会话状态管理 (todos, 催促计数器, 内存技能注册表)
├── prompts.py            # 系统提示词构建 (build_system) 与 Subagent 提示词
├── hooks.py              # 生命周期钩子 (Hooks 注册/分发/安全拦截/审计)
├── agent.py              # 核心调度循环 (agent_loop)
└── tools/                # 独立工具模块集
    ├── __init__.py       # TOOLS Schema 与 TOOL_HANDLERS 集中映射
    ├── system.py         # 系统操作 (safe_path, run_bash)
    ├── files.py          # 文件操作 (read_file, write_file, edit_file, glob)
    ├── todo.py           # 任务列表管理 (todo_write)
    ├── skill.py          # 技能扫描与两级注入 (scan_skills, load_skill)
    └── subagent.py       # 子代理派发机制 (spawn_subagent, SUB_TOOLS)
```

## 运行方式

在项目根目录下：

```bash
# 步骤 1: 启动后台 LiteLLM 代理服务 (若未启动)
.venv/bin/litellm --config litellm_config.yaml --port 4000

# 步骤 2: 运行 Agent
# 方式 1: 作为模块运行 (推荐)
python -m MiniCodingAgent

# 方式 2: 直接执行 main.py
python MiniCodingAgent/main.py
```

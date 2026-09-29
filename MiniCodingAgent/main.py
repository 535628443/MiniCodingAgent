"""
s07 CLI 交互入口
初始化技能扫描与生命周期钩子，提供 Readline 交互循环。
"""
import sys
from pathlib import Path

# 确保直接通过 python MiniCodingAgent/main.py 运行时也能正确定位并导入包
if __package__ is None or __package__ == "":
    parent_dir = Path(__file__).resolve().parent.parent
    if str(parent_dir) not in sys.path:
        sys.path.insert(0, str(parent_dir))
    from MiniCodingAgent.state import state
    from MiniCodingAgent.hooks import trigger_hooks, setup_default_hooks
    from MiniCodingAgent.tools.skill import scan_skills
    from MiniCodingAgent.agent import agent_loop
else:
    from .state import state
    from .hooks import trigger_hooks, setup_default_hooks
    from .tools.skill import scan_skills
    from .agent import agent_loop

try:
    import readline
    # macOS libedit 中文输入与终端补丁
    readline.parse_and_bind('set bind-tty-special-chars off')
    readline.parse_and_bind('set input-meta on')
    readline.parse_and_bind('set output-meta on')
    readline.parse_and_bind('set convert-meta off')
except ImportError:
    pass


def main():
    # 1. 扫描 skills/ 目录构建技能内存注册表 (Layer 1 初始化)
    scan_skills()

    # 2. 注册默认生命周期钩子 (安全拦截、日志、结束统计等)
    setup_default_hooks()

    print("MiniCodingAgent: Skill Loading — catalog in SYSTEM, content on demand (Modular Edition)")
    print("Type a question, press Enter. Type q to quit.\n")

    history = []
    while True:
        try:
            query = input("\033[36mMiniCodingAgent >> \033[0m")
        except (EOFError, KeyboardInterrupt):
            break

        if query.strip().lower() in ("q", "exit", ""):
            break

        trigger_hooks("UserPromptSubmit", query)

        state.reset_rounds()

        history.append({"role": "user", "content": query})
        agent_loop(history)

        for block in history[-1]["content"]:
            if getattr(block, "type", None) == "text":
                print(block.text)
        print()


if __name__ == "__main__":
    main()

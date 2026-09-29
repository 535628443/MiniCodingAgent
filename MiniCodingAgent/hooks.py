"""
s07 生命周期钩子体系 (Hooks)
支持 UserPromptSubmit、PreToolUse、PostToolUse、Stop 等事件拦截与扩展。
"""
from typing import Callable, Any
from .config import WORKDIR

# 全局钩子字典
HOOKS: dict[str, list[Callable]] = {
    "UserPromptSubmit": [],
    "PreToolUse": [],
    "PostToolUse": [],
    "Stop": [],
}


def register_hook(event: str, callback: Callable):
    """注册指定生命周期事件的回调函数。"""
    if event not in HOOKS:
        HOOKS[event] = []
    HOOKS[event].append(callback)


def trigger_hooks(event: str, *args) -> Any:
    """触发指定事件的所有钩子，遇拦截返回值立即返回。"""
    for callback in HOOKS.get(event, []):
        result = callback(*args)
        if result is not None:
            return result
    return None


DENY_LIST = ["rm -rf /", "sudo", "shutdown", "reboot", "mkfs", "dd if="]


def permission_hook(block):
    """PreToolUse: 拦截高危 Shell 命令。"""
    if block.name == "bash":
        cmd = block.input.get("command", "")
        for p in DENY_LIST:
            if p in cmd:
                print(f"\n\033[31m⛔ Blocked: '{p}'\033[0m")
                return "Permission denied"
    return None


def log_hook(block):
    """PreToolUse: 打印工具调用日志。"""
    print(f"\033[90m[HOOK] {block.name}\033[0m")
    return None


def context_inject_hook(query: str):
    """UserPromptSubmit: 注入当前工作目录上下文提示。"""
    print(f"\033[90m[HOOK] UserPromptSubmit: working in {WORKDIR}\033[0m")
    return None


def summary_hook(messages: list):
    """Stop: 统计并打印本次会话的工具调用总次数。"""
    tool_count = 0
    for m in messages:
        content = m.get("content")
        if isinstance(content, list):
            for b in content:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    tool_count += 1

    print(f"\033[90m[HOOK] Stop: session used {tool_count} tool calls\033[0m")
    return None


def setup_default_hooks():
    """注册通用默认生命周期钩子"""
    # 避免重复注册
    for hook_list in HOOKS.values():
        hook_list.clear()

    register_hook("UserPromptSubmit", context_inject_hook)
    register_hook("PreToolUse", permission_hook)
    register_hook("PreToolUse", log_hook)
    register_hook("Stop", summary_hook)

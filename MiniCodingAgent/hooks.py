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


def setup_default_hooks():
    """注册通用默认生命周期钩子"""
    # 避免重复注册
    for hook_list in HOOKS.values():
        hook_list.clear()

    register_hook("UserPromptSubmit", _context_inject_hook)
    register_hook("PreToolUse", _permission_hook)
    register_hook("PreToolUse", _log_hook)
    register_hook("Stop", _task_guard_hook)
    register_hook("Stop", _summary_hook)


# ====================== Helper Methods ============================

_DENY_LIST = ["rm -rf /", "sudo", "shutdown", "reboot", "mkfs", "dd if="]
_MAX_GUARD_RETRIES = 2
_guard_retries = 0


def _permission_hook(block):
    """PreToolUse: 拦截高危 Shell 命令。"""
    if block.name == "bash":
        cmd = block.input.get("command", "")
        for p in _DENY_LIST:
            if p in cmd:
                print(f"\n\033[31m⛔ Blocked: '{p}'\033[0m")
                return "Permission denied"
    return None


def _log_hook(block):
    """PreToolUse: 打印工具调用日志。"""
    print(f"\033[90m[HOOK] {block.name}\033[0m")
    return None


def _context_inject_hook(query: str):
    """UserPromptSubmit: 注入当前工作目录上下文提示并重置防护计数器。"""
    global _guard_retries
    _guard_retries = 0
    print(f"\033[90m[HOOK] UserPromptSubmit: working in {WORKDIR}\033[0m")
    return None


def _task_guard_hook(messages: list):
    """Stop: 若还有未完成的待办事项且重试次数未超限，阻止模型提前退出。"""
    global _guard_retries
    from .state import state
    unfinished = [t for t in state.current_todos if t.get("status") in ("pending", "in_progress")]
    if unfinished:
        if _guard_retries < _MAX_GUARD_RETRIES:
            _guard_retries += 1
            tasks_str = "\n".join(f"- [{t.get('status')}] {t.get('content')}" for t in unfinished)
            return (
                f"<task_guard>\n"
                f"You still have unfinished tasks:\n{tasks_str}\n"
                f"Please continue executing tools to complete the remaining tasks or update their status before stopping.\n"
                f"</task_guard>"
            )
    _guard_retries = 0
    return None


def _summary_hook(messages: list):
    """Stop: 统计并打印本次会话的工具调用总次数。"""
    tool_count = 0
    for m in messages:
        content = m.get("content") if isinstance(m, dict) else getattr(m, "content", None)
        if isinstance(content, list):
            for b in content:
                b_type = b.get("type") if isinstance(b, dict) else getattr(b, "type", None)
                if b_type == "tool_result":
                    tool_count += 1

    print(f"\033[90m[HOOK] Stop: session used {tool_count} tool calls\033[0m")
    return None


# 兼容旧命名别名（若有外部引用）
permission_hook = _permission_hook
log_hook = _log_hook
context_inject_hook = _context_inject_hook
task_guard_hook = _task_guard_hook
summary_hook = _summary_hook
DENY_LIST = _DENY_LIST



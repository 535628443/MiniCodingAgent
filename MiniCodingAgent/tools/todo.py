"""
任务管理工具：todo_write
"""
import ast
import json
from ..state import state


def _normalize_todos(todos):
    """参数归一化与校验（保证兼容模型输出的各种结构）。"""
    if isinstance(todos, str):
        try:
            todos = json.loads(todos)
        except json.JSONDecodeError:
            try:
                todos = ast.literal_eval(todos)
            except (SyntaxError, ValueError):
                return None, "Error: todos must be a list or JSON array string"

    if not isinstance(todos, list):
        return None, "Error: todos must be a list"

    for i, t in enumerate(todos):
        if not isinstance(t, dict):
            return None, f"Error: todos[{i}] must be an object"
        if "content" not in t or "status" not in t:
            return None, f"Error: todos[{i}] missing 'content' or 'status'"
        if t["status"] not in ("pending", "in_progress", "completed"):
            return None, f"Error: todos[{i}] has invalid status '{t['status']}'"

    return todos, None


def run_todo_write(todos: list) -> str:
    """保存并彩色打印任务状态看板。"""
    normalized, error = _normalize_todos(todos)
    if error:
        return error

    state.current_todos = normalized

    lines = ["\n\033[33m## Current Tasks\033[0m"]
    icon_map = {
        "pending": " ",
        "in_progress": "\033[36m▸\033[0m",
        "completed": "\033[32m✓\033[0m",
    }

    for t in state.current_todos:
        icon = icon_map.get(t["status"], " ")
        lines.append(f"  [{icon}] {t['content']}")

    print("\n".join(lines))
    return f"Updated {len(state.current_todos)} tasks"

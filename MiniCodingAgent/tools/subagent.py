"""
Subagent 子代理派发机制 (继承自 s06)
派发拥有独立全新上下文的子代理，运行多轮后返回总结文本。
"""
from ..config import client, MODEL
from ..hooks import trigger_hooks
from .system import run_bash
from .files import run_read, run_write, run_edit, run_glob

# Subagent 专有工具列表（严禁包含 task 工具，防止无限递归嵌套）
SUB_TOOLS = [
    {
        "name": "bash",
        "description": "Run non-interactive shell commands (e.g. grep, find, git, pytest, ls, python) in the workspace directory and capture the output.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command line string to execute in the workspace.",
                }
            },
            "required": ["command"],
        },
    },
    {
        "name": "read_file",
        "description": "Read file contents safely from the workspace. Supports optional line limit to avoid context overflow.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path to the file in the workspace.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Optional maximum number of lines to read from the file.",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write or overwrite content to a file. Automatically creates any missing parent directories.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path to the destination file.",
                },
                "content": {
                    "type": "string",
                    "description": "The full text content to write to the file.",
                },
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "edit_file",
        "description": "Replace an exact substring ('old_text') with 'new_text' in a file once. 'old_text' must match the file content exactly.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path to the file to edit.",
                },
                "old_text": {
                    "type": "string",
                    "description": "The exact substring to be replaced (must match uniquely in the file).",
                },
                "new_text": {
                    "type": "string",
                    "description": "The replacement substring.",
                },
            },
            "required": ["path", "old_text", "new_text"],
        },
    },
    {
        "name": "glob",
        "description": "Find file paths in the workspace matching a glob pattern (e.g., '**/*.py', 'MiniCodingAgent/*.py', 'tests/*').",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern relative to workspace root.",
                }
            },
            "required": ["pattern"],
        },
    },
]

SUB_HANDLERS = {
    "bash": run_bash,
    "read_file": run_read,
    "write_file": run_write,
    "edit_file": run_edit,
    "glob": run_glob,
}


def spawn_subagent(description: str) -> str:
    """
    派发一个拥有独立全新上下文的 Subagent。
    内部最多运行 30 轮交互，中间过程丢弃，仅返回最终文本总结。
    """
    from ..prompts import SUB_SYSTEM

    print(f"\n\033[35m[Subagent spawned]\033[0m")
    messages = [{"role": "user", "content": description}]

    for _ in range(30):
        response = client.messages.create(
            model=MODEL,
            system=SUB_SYSTEM,
            messages=messages,
            tools=SUB_TOOLS,
            max_tokens=8000,
        )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            break

        results = []
        for block in response.content:
            if block.type != "tool_use":
                continue

            blocked = trigger_hooks("PreToolUse", block)
            if blocked:
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": str(blocked),
                })
                continue

            handler = SUB_HANDLERS.get(block.name)
            output = handler(**block.input) if handler else f"Unknown: {block.name}"

            trigger_hooks("PostToolUse", block, output)
            print(f"  \033[90m[sub] {block.name}: {str(output)[:100]}\033[0m")

            results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": output,
            })

        messages.append({"role": "user", "content": results})

    result = _extract_text(messages[-1]["content"])
    if not result:
        for msg in reversed(messages):
            if msg["role"] == "assistant":
                result = _extract_text(msg["content"])
                if result:
                    break

        if not result:
            result = "Subagent stopped after 30 turns without final answer."

    print(f"\033[35m[Subagent done]\033[0m")
    return result


# ====================== Helper Methods ============================

def _extract_text(content) -> str:
    """从消息块列表中提取纯文本回复内容。"""
    if not isinstance(content, list):
        return str(content)
    return "\n".join(
        getattr(b, "text", "")
        for b in content
        if getattr(b, "type", None) == "text"
    )


# 兼容旧命名别名
extract_text = _extract_text


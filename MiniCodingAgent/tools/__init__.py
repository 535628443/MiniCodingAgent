"""
工具聚合导出模块：汇总 TOOLS 声明与 TOOL_HANDLERS 分发映射
"""
from .system import run_bash, safe_path
from .files import run_read, run_write, run_edit, run_glob
from .todo import run_todo_write
from .skill import load_skill, scan_skills, list_skills
from .subagent import spawn_subagent

# 主 Agent 完整工具 Schema 定义
TOOLS = [
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
    {
        "name": "todo_write",
        "description": "Create and manage the structured task checklist for your coding session. Keeps progress tracked across multiple steps.",
        "input_schema": {
            "type": "object",
            "properties": {
                "todos": {
                    "type": "array",
                    "description": "The complete list of todo items.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "content": {
                                "type": "string",
                                "description": "Clear description of the task item.",
                            },
                            "status": {
                                "type": "string",
                                "enum": ["pending", "in_progress", "completed"],
                                "description": "Current status of the task item.",
                            },
                        },
                        "required": ["content", "status"],
                    },
                }
            },
            "required": ["todos"],
        },
    },
    {
        "name": "task",
        "description": "Launch an autonomous subagent with a fresh, isolated context to perform a complex or exploratory subtask, returning only a concise summary.",
        "input_schema": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "Detailed instructions and context for the subagent to execute.",
                }
            },
            "required": ["description"],
        },
    },
    {
        "name": "load_skill",
        "description": "Load the full standard operating procedure (SOP) and detailed domain guidelines for a specific skill from the catalog.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "The name of the skill to load (e.g. 'agent-builder', 'code-review', 'mcp-builder', 'pdf').",
                }
            },
            "required": ["name"],
        },
    },
    {
        "name": "compact",
        "description": "Manually trigger conversation history compaction to free context space.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
]

# 工具函数映射表
TOOL_HANDLERS = {
    "bash": run_bash,
    "read_file": run_read,
    "write_file": run_write,
    "edit_file": run_edit,
    "glob": run_glob,
    "todo_write": run_todo_write,
    "task": spawn_subagent,
    "load_skill": load_skill,
}

__all__ = [
    "TOOLS",
    "TOOL_HANDLERS",
    "safe_path",
    "run_bash",
    "run_read",
    "run_write",
    "run_edit",
    "run_glob",
    "run_todo_write",
    "load_skill",
    "scan_skills",
    "list_skills",
    "spawn_subagent",
]

"""
基础系统工具：安全路径校验与 Bash 命令执行
"""
import subprocess
from pathlib import Path
from ..config import WORKDIR


def safe_path(p: str) -> Path:
    """确保路径在工作区内，防止目录遍历攻击。"""
    path = (WORKDIR / p).resolve()
    if not path.is_relative_to(WORKDIR):
        raise ValueError(f"Path escapes workspace: {p}")
    return path


def run_bash(command: str) -> str:
    """执行 Shell 命令并捕获输出。"""
    try:
        r = subprocess.run(
            command,
            shell=True,
            cwd=WORKDIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        out = (r.stdout + r.stderr).strip()
        return out[:50000] if out else "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Timeout (120s)"

"""
Prompt 提示词管理：系统提示词构建与子代理提示词定义
"""
from .config import WORKDIR
from .tools.skill import list_skills


def build_system() -> str:
    """
    构建主 Agent 的系统提示词：
    将 Layer 1 的技能索引清单 (仅名称与单行简述) 注入到 System Prompt 中。
    """
    catalog = list_skills()
    return (
        f"You are a coding agent at {WORKDIR}. "
        f"Skills available:\n{catalog}\n"
        "Use load_skill to get full details when needed."
    )


# Subagent 专属系统提示词（明确独立执行职责，禁止递归派发子代理）
SUB_SYSTEM = (
    f"You are a coding agent at {WORKDIR}. "
    "Complete the task you were given, then return a concise summary. "
    "Do not delegate further."
)

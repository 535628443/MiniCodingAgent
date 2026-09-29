"""
s07 全局会话状态管理
封装待办任务清单、催促计数器与已注册技能缓存，避免分散的全局变量。
"""
from dataclasses import dataclass, field


@dataclass
class AgentState:
    # 当前会话的待办任务清单 (继承自 s05)
    current_todos: list[dict] = field(default_factory=list)
    # 距上次更新待办任务的对话轮数
    rounds_since_todo: int = 0
    # 启动时构建的内存技能注册表 (Layer 1 & Layer 2 数据源)
    skill_registry: dict[str, dict] = field(default_factory=dict)

    def reset_rounds(self):
        """重置催促计数器"""
        self.rounds_since_todo = 0

    def increment_rounds(self):
        """递增轮数计数器"""
        self.rounds_since_todo += 1


# 全局默认会话状态实例
state = AgentState()

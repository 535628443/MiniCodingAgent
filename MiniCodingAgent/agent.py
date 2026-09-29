"""
Agent 核心执行引擎：agent_loop 调度循环
负责驱动 LLM 调用、催促机制 (Todo Reminder)、Hook 拦截与工具分发执行。
"""
from .config import client, MODEL
from .state import state
from .hooks import trigger_hooks
from .prompts import build_system
from .tools import TOOLS, TOOL_HANDLERS


def agent_loop(messages: list):
    """
    核心驱动循环 (Agent Loop — 保持通用查表分发)
    """
    # 动态构建已注入 Layer 1 技能目录的系统提示词
    system_prompt = build_system()

    while True:
        # 催促机制：连续 3 轮未更新 todo 时自动注入提醒
        if state.rounds_since_todo >= 3 and messages:
            messages.append({
                "role": "user",
                "content": "<reminder>Update your todos.</reminder>",
            })
            state.reset_rounds()

        response = client.messages.create(
            model=MODEL,
            system=system_prompt,
            messages=messages,
            tools=TOOLS,
            max_tokens=8000,
        )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            force = trigger_hooks("Stop", messages)
            if force:
                messages.append({"role": "user", "content": force})
                continue
            return

        state.increment_rounds()
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

            # 查表调用：load_skill、task 等所有工具均统一通过查表执行
            handler = TOOL_HANDLERS.get(block.name)
            output = handler(**block.input) if handler else f"Unknown: {block.name}"

            trigger_hooks("PostToolUse", block, output)

            if block.name == "todo_write":
                state.reset_rounds()

            results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": output,
            })

        messages.append({"role": "user", "content": results})

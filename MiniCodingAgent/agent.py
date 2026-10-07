from anthropic import BadRequestError
from .config import client, MODEL
from .state import state
from .hooks import trigger_hooks
from .prompts import build_system
from .tools import TOOLS, TOOL_HANDLERS
from .compact import (
    tool_result_budget,
    snip_compact,
    micro_compact,
    compact_history,
    reactive_compact,
    should_auto_compact,
    MAX_REACTIVE_RETRIES
)


def agent_loop(messages: list):
    """核心驱动循环 (Agent Loop — 保持通用查表分发)"""
   
    # =========================================================================
    # 步骤 0：初始化准备
    # =========================================================================
    # 动态构建已注入 Layer 1 技能目录、环境与通用规范的系统提示词
    system_prompt = build_system()
    # 记录 Token 超限时的反应式压缩（Reactive Compaction）重试次数
    reactive_retries = 0

    while True:
        # =====================================================================
        # 步骤 1：预处理上下文压缩 (Pre-Compaction)
        # =====================================================================

        # 1.1 容量预算控制：若最新一轮工具输出过大，将大输出持久化到磁盘并替换为预览摘要
        messages[:] = tool_result_budget(messages)
        # 1.2 历史裁剪：保留会话头部与尾部消息，裁剪中间过长历史
        messages[:] = snip_compact(messages)
        # 1.3 微压缩：将历史中较早的、体积过大的 tool_result 进行简化占位
        messages[:] = micro_compact(messages)

        # =====================================================================
        # 步骤 2：自动上下文压缩 (Auto-Compaction)
        # =====================================================================

        # 检查当前上下文是否超过预设字符上限；若超限，则调用大模型总结历史并重置上下文
        if should_auto_compact(messages):
            print("[auto-compact]")
            messages[:] = compact_history(messages)

        # =====================================================================
        # 步骤 3：催促机制 (Todo Reminder Injection)
        # =====================================================================

        # 如果连续 3 轮交互未调用 todo_write 更新任务进度，自动注入提醒消息并重置计数
        if state.rounds_since_todo >= 3 and messages:
            messages.append({
                "role": "user",
                "content": (
                    "<reminder>\n"
                    "Update your task checklist using todo_write if needed, and IMMEDIATELY CONTINUE working towards the user's objective. "
                    "Do NOT stop or ask for confirmation until the entire task is completely finished.\n"
                    "</reminder>"
                ),
            })
            state.reset_rounds()

        # =====================================================================
        # 步骤 4：调用大模型推理生成 (LLM API Request & Error Handling)
        # =====================================================================

        try:
            # 携带当前上下文、系统提示词和工具列表请求 LLM
            response = client.messages.create(
                model=MODEL,
                system=system_prompt,
                messages=messages,
                tools=TOOLS,
                max_tokens=8000,
            )
        
        # 异常处理：捕获 Token 超限错误并执行反应式压缩 (Reactive Compaction)
        except BadRequestError as e:
            e_str = str(e).lower()
            # 若错误原因为 Prompt 过长且未达到最大重试次数，则压缩历史并重试
            overflow_keywords = ("prompt_too_long", "too many tokens", "context_length_exceeded", "contextwindowexceedederror", "maximum context length", "token limit", "prompt is too long")
            if any(k in e_str for k in overflow_keywords) and reactive_retries < MAX_REACTIVE_RETRIES:
                print(f"[Reactive Compaction] Token overflow, retry #{reactive_retries}")
                messages[:] = reactive_compact(messages)
                reactive_retries += 1
                continue
            raise

        # =====================================================================
        # 步骤 5：记录模型回复 (Record Assistant Message)
        # =====================================================================

        # 将模型的思考、文本回复或工具调用块追加到消息历史
        messages.append({"role": "assistant", "content": response.content})

        # =====================================================================
        # 步骤 6：停止机制与 Stop Hook 检查 (Stop Condition)
        # =====================================================================

        # 若大模型未发出工具调用 (stop_reason != 'tool_use')，说明已生成最终回复
        if response.stop_reason != "tool_use":
            # 触发 Stop 钩子（例如检查任务是否真的完成，或是否需要补充验证）
            force = trigger_hooks("Stop", messages)
            if force:
                # 钩子要求继续执行，注入反馈内容并继续循环
                messages.append({"role": "user", "content": force})
                continue
            # 无强制继续要求，正常结束 Agent 循环
            return

        # =====================================================================
        # 步骤 7：准备执行工具调用 (Tool Execution Setup)
        # =====================================================================

        # 递增自上次更新 todo 以来的轮次计数
        state.increment_rounds()
        # 存放本次返回给大模型的所有工具执行结果
        results = []

        # =====================================================================
        # 步骤 8：遍历并分发执行工具调用 (Tool Calls Dispatching)
        # =====================================================================

        compacted = False
        for block in response.content:
            # 仅处理 tool_use 类型的 content block
            if block.type != "tool_use":
                continue

            # 8.1 特殊工具：若模型主动调用 compact 工具，则对历史进行归档摘要
            if block.name == "compact":
                print("[compact]")
                messages[:] = compact_history(messages)
                compacted = True
                break

            # 8.2 工具前置钩子拦截 (PreToolUse Hook, 如安全防护与权限检查)
            blocked = trigger_hooks("PreToolUse", block)
            if blocked:
                # 若被拦截，直接将拦截原因包装为 tool_result 返回，跳过工具实际执行
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": str(blocked),
                })
                continue

            # 8.3 通用查表分发：根据工具名获取对应的执行函数并传参调用
            handler = TOOL_HANDLERS.get(block.name)
            output = handler(**block.input) if handler else f"Unknown: {block.name}"

            # 8.4 工具后置钩子 (PostToolUse Hook)
            trigger_hooks("PostToolUse", block, output)

            # 8.5 状态重置：若执行了 todo_write 工具，重置 rounds_since_todo 计数
            if block.name == "todo_write":
                state.reset_rounds()

            # 8.6 收集当前工具的执行结果
            results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": output,
            })

        # 若触发了 compact，上下文已被重置为摘要单条消息，跳过追加 tool_result，直接进入下一轮 LLM 推理
        if compacted:
            continue

        # =====================================================================
        # 步骤 9：回传工具执行结果 (Feed Tool Results Back to LLM)
        # =====================================================================

        # 将所有工具执行结果以 user 角色追加回消息列表，供下一轮模型决策
        messages.append({"role": "user", "content": results})

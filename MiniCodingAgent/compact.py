import os
from pathlib import Path
import json
import time
from .config import client, MODEL

KEEP_RECENT_TOOL_RESULTS = 3
DEFAULT_MAX_MESSAGES = 50
DEFAULT_TOOL_RESULT_BUDGET_BYTES = 200_000
DEFAULT_PREVIEW_LINES = 20
DEFAULT_SUMMARY_MAX_TOKENS = 2000
DEFAULT_CONTEXT_CHAR_LIMIT = 50_000
MAX_REACTIVE_RETRIES = 1

STORAGE_DIR = Path("/tmp/mini_agent_tool_outputs")
TRANSCRIPT_DIR = Path(".transcripts")


def snip_compact(messages: list[dict], max_messages=DEFAULT_MAX_MESSAGES) -> list[dict]:
    """保留头部与尾部消息，裁剪中间部分，返回压缩后的 messages"""
    if len(messages) <= max_messages:
        return messages

    keep_head = 3  # 头部保留3条
    keep_tail = max_messages - 3  # 尾部保留max_messages - 3 条

    # 头部切片为 messages[:head_end]，包含索引 0 到 head_end - 1
    head_end = keep_head
    # 尾部切片为 messages[tail_start:]，从 tail_start 一直到末尾
    tail_start = len(messages) - keep_tail

    if _message_has_tool_use(messages[head_end - 1]):
        while head_end < len(messages) and _is_tool_result_message(messages[head_end]):
            head_end += 1

    if _is_tool_result_message(messages[tail_start]) and _message_has_tool_use(messages[tail_start - 1]):
        tail_start -= 1

    if tail_start <= head_end:
        return messages

    snipped = tail_start - head_end
    placeholder = {"role": "user", "content": f"[snipped {snipped} messages from conversation middle]"}

    return messages[:head_end] + [placeholder] + messages[tail_start:]


def micro_compact(messages):
    """将旧的 tool_result 内容过大的部分压缩，只保留最新的几个。"""
    tool_results = _collect_tool_result_blocks(messages)
    if len(tool_results) <= KEEP_RECENT_TOOL_RESULTS:
        return messages

    for block in tool_results[:-KEEP_RECENT_TOOL_RESULTS]:
        content = block.get("content", "") if isinstance(block, dict) else getattr(block, "content", "")
        if len(str(content)) > 120:
            if isinstance(block, dict):
                block["content"] = "[Earlier tool result compacted. Re-run if needed.]"
            else:
                setattr(block, "content", "[Earlier tool result compacted. Re-run if needed.]")
    return messages


def tool_result_budget(messages, max_bytes=DEFAULT_TOOL_RESULT_BUDGET_BYTES):
    """ 对最新一轮的 tool_result 进行容量预算控制, 超限时优先持久化最大的输出"""
    if not messages:
        return messages
    last = messages[-1]
    content = last.get("content") if isinstance(last, dict) else getattr(last, "content", None)
    if not isinstance(content, list):
        return messages

    blocks = [
        (i, b) for i, b in enumerate(content)
        if (isinstance(b, dict) and b.get("type") == "tool_result") or getattr(b, "type", None) == "tool_result"
    ]
    total = sum(len(str(b.get("content", "") if isinstance(b, dict) else getattr(b, "content", ""))) for _, b in blocks)
    
    if total <= max_bytes:
        return messages
    
    ranked = sorted(
        blocks,
        key=lambda p: len(str(p[1].get("content", "") if isinstance(p[1], dict) else getattr(p[1], "content", ""))),
        reverse=True
    )  # 按内容长度倒序排列
    
    for idx, block in ranked:
        if total <= max_bytes:
            break
        
        tool_use_id = block.get("tool_use_id", "unknown") if isinstance(block, dict) else getattr(block, "tool_use_id", "unknown")
        b_content = block.get("content", "") if isinstance(block, dict) else getattr(block, "content", "")
        persisted = _persist_large_output(tool_use_id, str(b_content))
        if isinstance(block, dict):
            block["content"] = persisted
        else:
            setattr(block, "content", persisted)
        total = _recalculate_total(blocks)

    return messages


def compact_history(messages):
    """ LLM 把完整对话压缩成一条, 简洁描述当前对话的背景和进度."""
    transcript_path = _write_transcript(messages)  # 将当前完整对话持久化, 需要是再从磁盘加载原始文件.
    summary = _summarize_history(messages)          # LLM 另开一个新线程自己生成摘要.
    return [
        {
            "role": "user",
            "content": f"[Compacted]\n\n{summary}"
        }
    ]


def reactive_compact(messages):
    """ Token 超限时的反应式压缩：总结旧历史并保留最近 5-6 条消息 """
    transcript = _write_transcript(messages) 
    summary = _summarize_history(messages) 
    tail_start = max(0, len(messages) - 5) # 保留最后 5 条消息
    
    # 如果最后一条消息是 tool_result 且倒数第二条是 tool_use，则保留倒数第二条(一共保留最后 6 条消息)
    if tail_start > 0 and _is_tool_result_message(messages[tail_start]) and _message_has_tool_use(messages[tail_start - 1]):
        tail_start -= 1
        
    return [{"role": "user", "content": f"[Reactive compact]\n\n{summary}"}, *messages[tail_start:]]


def should_auto_compact(messages: list, limit: int | None = None) -> bool:
    """判断当前上下文是否超限，需要触发自动压缩"""
    if limit is None:
        limit = DEFAULT_CONTEXT_CHAR_LIMIT
    return _estimate_chars(messages) > limit


# ====================== Helper Methods ============================

def _message_has_tool_use(message: dict | object) -> bool:
    """判断消息是否包含 tool_use 调用"""
    content = message.get("content") if isinstance(message, dict) else getattr(message, "content", None)
    if not isinstance(content, list):
        return False

    for block in content:
        b_type = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
        if b_type == "tool_use":
            return True
    return False


def _is_tool_result_message(message: dict | object) -> bool:
    """判断消息是否为 tool_result 结果"""
    content = message.get("content") if isinstance(message, dict) else getattr(message, "content", None)
    
    if not isinstance(content, list):
        return False
    
    for block in content:
        b_type = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
        if b_type == "tool_result":
            return True
    return False


def _collect_tool_result_blocks(messages: list[dict]) -> list[dict]:
    """收集所有类型为 'tool_result' 的 content block"""
    tool_results = []
    for message in messages:
        content = message.get("content") if isinstance(message, dict) else getattr(message, "content", None)
        
        if isinstance(content, list):
            for block in content:
                b_type = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
                if b_type == "tool_result":
                    tool_results.append(block)
    return tool_results


def _serialize_message(obj):
    """通用对象序列化器，支持 Pydantic 模型、字典与自定义对象"""
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    return str(obj)


def _format_messages_for_summary(messages: list) -> str:
    """将各种格式的消息历史格式化为结构化纯文本供摘要模型阅读"""
    lines = []
    for msg in messages:
        role = msg.get("role", "unknown") if isinstance(msg, dict) else getattr(msg, "role", "unknown")
        content = msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", "")
        
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, str):
                    parts.append(block)
                elif isinstance(block, dict):
                    b_type = block.get("type")
                    if b_type == "text":
                        parts.append(block.get("text", ""))
                    elif b_type == "tool_use":
                        parts.append(f"[Tool Call: {block.get('name')}({json.dumps(block.get('input', {}), default=_serialize_message, ensure_ascii=False)})]")
                    elif b_type == "tool_result":
                        c = block.get("content", "")
                        c_str = str(c)[:1000] + ("..." if len(str(c)) > 1000 else "")
                        parts.append(f"[Tool Result: {c_str}]")
                    else:
                        parts.append(str(block))
                else:
                    b_type = getattr(block, "type", None)
                    if b_type == "text":
                        parts.append(getattr(block, "text", ""))
                    elif b_type == "tool_use":
                        parts.append(f"[Tool Call: {getattr(block, 'name', '')}({json.dumps(getattr(block, 'input', {}), default=_serialize_message, ensure_ascii=False)})]")
                    elif b_type == "tool_result":
                        c = getattr(block, "content", "")
                        c_str = str(c)[:1000] + ("..." if len(str(c)) > 1000 else "")
                        parts.append(f"[Tool Result: {c_str}]")
                    else:
                        parts.append(str(block))
            text = "\n".join(parts)
        else:
            text = str(content)
        lines.append(f"{str(role).upper()}:\n{text}")
    return "\n\n".join(lines)


def _persist_large_output(tool_use_id: str, content: str, preview_lines: int = DEFAULT_PREVIEW_LINES) -> str:
    """将超大工具输出持久化到磁盘，并返回摘要和文件路径"""
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    file_path = STORAGE_DIR / f"{tool_use_id}.log"
    
    # 1. 写入本地文件
    file_path.write_text(content, encoding="utf-8")
    
    # 2. 截取前 preview_lines 行作为预览
    preview = "\n".join(content.splitlines()[:preview_lines])
    
    # 3. 返回给大模型的占位提示
    return (
        f"[Output too large ({len(content)} chars). Full output saved to {file_path}]\n"
        f"--- Preview (First {preview_lines} lines) ---\n"
        f"{preview}\n"
        f"--- End Preview ---"
    )


def _recalculate_total(blocks: list) -> int:
    """重新计算所有 tool_result block 的总字符长度"""
    return sum(len(str(b.get("content", "") if isinstance(b, dict) else getattr(b, "content", ""))) for _, b in blocks)


def _write_transcript(messages: list) -> Path:
    """将完整对话历史归档保存为 JSONL 文件"""
    TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"transcript_{int(time.time())}.jsonl"
    file_path = TRANSCRIPT_DIR / filename
    
    with file_path.open("w", encoding="utf-8") as f:
        for msg in messages:
            f.write(json.dumps(msg, default=_serialize_message, ensure_ascii=False) + "\n")
            
    return file_path


def _summarize_history(messages: list) -> str:
    """调用大模型为长对话生成结构化摘要"""
    formatted_history = _format_messages_for_summary(messages)
    prompt = (
        "请对以下完整的历史对话进行高度概括, 列出: 1. 用户的最初目标; 2. 已经完成的工作与修改的文件; 3. 关键信息; 4. 待办事项。\n\n"
        f"=== 历史对话 ===\n{formatted_history}"
    )
    
    response = client.messages.create(
        model=MODEL,
        max_tokens=DEFAULT_SUMMARY_MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    for block in response.content:
        if getattr(block, "type", None) == "text":
            return block.text
        if isinstance(block, dict) and block.get("type") == "text":
            return block.get("text", "")
    return str(response.content)


def _estimate_chars(messages: list) -> int:
    """估算当前消息列表的总字符数"""
    return len(json.dumps(messages, default=_serialize_message, ensure_ascii=False))


__all__ = [
    "tool_result_budget",
    "snip_compact",
    "micro_compact",
    "compact_history",
    "reactive_compact",
    "should_auto_compact",
    "MAX_REACTIVE_RETRIES",
]
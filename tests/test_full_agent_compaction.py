"""
MiniCodingAgent 全功能与全流程自动化测试套件
验证项目的每一个功能模块，并通过持续多轮 Agent 问答交互，
分别触发 [auto-compact] 和 [Reactive Compaction]，
支持连续执行三轮完整测试，确保 0 报错。
"""

import io
import os
import sys
import json
import time
import shutil
import unittest
import contextlib
from pathlib import Path
from unittest.mock import patch

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import httpx
from anthropic import BadRequestError
from anthropic.types import TextBlock, ToolUseBlock

from MiniCodingAgent.config import client, MODEL, WORKDIR, SKILLS_DIR
from MiniCodingAgent.state import state, AgentState
from MiniCodingAgent.prompts import build_system, SUB_SYSTEM
from MiniCodingAgent.hooks import (
    HOOKS,
    register_hook,
    trigger_hooks,
    setup_default_hooks,
    _permission_hook,
    _log_hook,
    _context_inject_hook,
    _task_guard_hook,
    _summary_hook,
)
from MiniCodingAgent.tools import TOOLS, TOOL_HANDLERS
from MiniCodingAgent.tools.system import run_bash, safe_path
from MiniCodingAgent.tools.files import run_read, run_write, run_edit, run_glob
from MiniCodingAgent.tools.todo import run_todo_write, _normalize_todos
from MiniCodingAgent.tools.skill import scan_skills, list_skills, load_skill, _parse_frontmatter
from MiniCodingAgent.tools.subagent import spawn_subagent, SUB_TOOLS, SUB_HANDLERS, extract_text
from MiniCodingAgent.compact import (
    tool_result_budget,
    snip_compact,
    micro_compact,
    compact_history,
    reactive_compact,
    should_auto_compact,
    _write_transcript,
    _summarize_history,
    _format_messages_for_summary,
    _estimate_chars,
    DEFAULT_CONTEXT_CHAR_LIMIT,
    STORAGE_DIR,
    TRANSCRIPT_DIR,
)
from MiniCodingAgent.agent import agent_loop


class TestMiniCodingAgentFeatures(unittest.TestCase):
    """
    模块功能单元测试：覆盖 MiniCodingAgent 每一个独立功能组件
    """

    def setUp(self):
        scan_skills()
        setup_default_hooks()
        state.reset_rounds()
        state.current_todos.clear()
        self.test_dir = Path("test_temp_workspace")
        self.test_dir.mkdir(exist_ok=True)

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    # -------------------------------------------------------------------------
    # 1. System & Path Tools 测试
    # -------------------------------------------------------------------------
    def test_safe_path(self):
        """测试路径安全性与工作区越界防护"""
        valid_p = safe_path("test_temp_workspace/test.txt")
        self.assertTrue(valid_p.is_relative_to(WORKDIR))

        with self.assertRaises(ValueError):
            safe_path("../../outside.txt")

    def test_run_bash(self):
        """测试 bash 命令执行、输出截断与错误捕获"""
        # 正常命令
        res = run_bash("echo 'MiniAgent Bash Test'")
        self.assertEqual(res, "MiniAgent Bash Test")

        # 空输出
        res_empty = run_bash("true")
        self.assertEqual(res_empty, "(no output)")

        # 错误输出
        res_err = run_bash("ls nonexistent_directory_12345")
        self.assertTrue("No such file" in res_err or "nonexistent_directory" in res_err)

    # -------------------------------------------------------------------------
    # 2. Files Tools 测试 (read, write, edit, glob)
    # -------------------------------------------------------------------------
    def test_file_operations_full(self):
        """测试文件的写入、按行读取、修改及 glob 匹配"""
        test_file = "test_temp_workspace/sample.txt"

        # 1. write_file (包括自动创建多层父目录)
        w_res = run_write(test_file, "Line 1\nLine 2\nLine 3\nLine 4\nLine 5\n")
        self.assertIn("Wrote", w_res)
        self.assertTrue(safe_path(test_file).exists())

        # 2. read_file 全文读取与 limit 读取
        r_all = run_read(test_file)
        self.assertIn("Line 3", r_all)
        r_limit = run_read(test_file, limit=2)
        self.assertIn("Line 1", r_limit)
        self.assertIn("... (3 more lines)", r_limit)

        # 3. edit_file 精确替换与未找到报错
        e_res = run_edit(test_file, "Line 3", "Modified Line Three")
        self.assertIn("Edited", e_res)
        self.assertIn("Modified Line Three", run_read(test_file))

        e_fail = run_edit(test_file, "Nonexistent Text", "Replacement")
        self.assertIn("Error: text not found", e_fail)

        # 4. glob 模式搜索
        g_res = run_glob("test_temp_workspace/*.txt")
        self.assertIn(test_file, g_res)

        g_none = run_glob("test_temp_workspace/*.nonexistent")
        self.assertEqual(g_none, "(no matches)")

        # 5. 安全越界防护
        r_escape = run_read("../../../etc/passwd")
        self.assertIn("Error", r_escape)

    # -------------------------------------------------------------------------
    # 3. Todo Write & State 测试
    # -------------------------------------------------------------------------
    def test_todo_management(self):
        """测试任务管理看板规范化、状态记录与校验"""
        todos = [
            {"content": "Design architecture", "status": "completed"},
            {"content": "Implement test suite", "status": "in_progress"},
            {"content": "Run 3 rounds verification", "status": "pending"},
        ]
        res = run_todo_write(todos)
        self.assertIn("Updated 3 tasks", res)
        self.assertEqual(len(state.current_todos), 3)
        self.assertEqual(state.current_todos[0]["status"], "completed")

        # 测试 JSON 字符串格式的 todo 输入
        json_todos = json.dumps([{"content": "Task A", "status": "pending"}])
        res_json = run_todo_write(json_todos)
        self.assertIn("Updated 1 tasks", res_json)

        # 测试异常参数校验
        err_list = run_todo_write("invalid_json_string")
        self.assertIn("Error", err_list)

        err_status = run_todo_write([{"content": "Task B", "status": "invalid_status"}])
        self.assertIn("Error", err_status)

        err_keys = run_todo_write([{"wrong_key": "val"}])
        self.assertIn("Error", err_keys)

    # -------------------------------------------------------------------------
    # 4. Skill System 测试
    # -------------------------------------------------------------------------
    def test_skills_catalog_and_loading(self):
        """测试 Layer 1 技能目录扫描与 Layer 2 按需正文加载"""
        scan_skills()
        self.assertGreater(len(state.skill_registry), 0)

        # list_skills
        catalog = list_skills()
        self.assertIn("agent-builder", catalog)
        self.assertIn("code-review", catalog)

        # load_skill
        content = load_skill("agent-builder")
        self.assertIn("agent-builder", content.lower())

        missing = load_skill("nonexistent_skill_xyz")
        self.assertIn("Skill not found", missing)

        # _parse_frontmatter
        meta, body = _parse_frontmatter("---\nname: my-skill\ndescription: demo\n---\n# Body Content")
        self.assertEqual(meta.get("name"), "my-skill")
        self.assertEqual(body, "# Body Content")

    # -------------------------------------------------------------------------
    # 5. Subagent 机制测试
    # -------------------------------------------------------------------------
    def test_subagent_toolset_and_extract_text(self):
        """测试 Subagent 的专属工具集（无递归 task）与文本提取"""
        sub_tool_names = [t["name"] for t in SUB_TOOLS]
        self.assertNotIn("task", sub_tool_names)
        self.assertIn("bash", sub_tool_names)
        self.assertIn("read_file", sub_tool_names)

        # 文本提取辅助函数
        blocks = [
            TextBlock(text="Subagent finished task.", type="text"),
            ToolUseBlock(id="1", input={}, name="bash", type="tool_use"),
        ]
        self.assertEqual(extract_text(blocks), "Subagent finished task.")
        self.assertEqual(extract_text("Plain text string"), "Plain text string")

    def test_subagent_live_execution(self):
        """测试 Subagent 独立上下文派发与结果返回"""
        res = spawn_subagent("Run bash echo 'subagent live test' and return the exact text.")
        self.assertIn("subagent live test", res)

    def test_manual_compact_tool(self):
        """测试模型显式调用 compact 工具手动压缩历史"""
        history = [
            {"role": "user", "content": "Please compress the conversation history using the compact tool."},
        ]
        # 模拟模型返回 compact 工具调用块、摘要生成、以及压缩后的最终回复
        mock_tool = type("MockToolResp", (), {
            "content": [ToolUseBlock(id="call_c1", input={}, name="compact", type="tool_use")],
            "stop_reason": "tool_use"
        })()
        mock_summary = type("MockSummaryResp", (), {
            "content": [TextBlock(text="Summary of earlier session.", type="text")],
            "stop_reason": "end_turn"
        })()
        mock_final = type("MockFinalResp", (), {
            "content": [TextBlock(text="History compacted successfully.", type="text")],
            "stop_reason": "end_turn"
        })()

        with patch.object(client.messages, "create", side_effect=[
            mock_tool,     # 1. 模型发出 compact 工具调用
            mock_summary,  # 2. compact_history 内部调用 LLM 生成摘要
            mock_final,    # 3. 压缩重置后模型生成下一轮最终文本回复
        ]):
            captured = io.StringIO()
            with contextlib.redirect_stdout(captured):
                agent_loop(history)

            output_str = captured.getvalue()
            self.assertIn("[compact]", output_str)
            self.assertEqual(len(history), 2)
            self.assertIn("[Compacted]", history[0]["content"])

    # -------------------------------------------------------------------------
    # 6. Hooks 拦截与生命周期测试
    # -------------------------------------------------------------------------
    def test_hooks_system(self):
        """测试 PreToolUse, PostToolUse, Stop, UserPromptSubmit 钩子体系"""
        # 1. PreToolUse 危险命令拦截
        class DangerousBlock:
            name = "bash"
            input = {"command": "rm -rf /"}

        blocked = trigger_hooks("PreToolUse", DangerousBlock())
        self.assertEqual(blocked, "Permission denied")

        class SafeBlock:
            name = "bash"
            input = {"command": "echo safe"}

        safe_res = trigger_hooks("PreToolUse", SafeBlock())
        self.assertIsNone(safe_res)

        # 2. Stop 钩子与 Task Guard 拦截
        state.current_todos = [{"content": "Unfinished step", "status": "in_progress"}]
        stop_blocked = trigger_hooks("Stop", [])
        self.assertIsNotNone(stop_blocked)
        self.assertIn("unfinished tasks", stop_blocked)

        state.current_todos = [{"content": "Finished step", "status": "completed"}]
        stop_allowed = trigger_hooks("Stop", [])
        self.assertIsNone(stop_allowed)

        # 3. UserPromptSubmit 钩子
        trigger_hooks("UserPromptSubmit", "new query")

    # -------------------------------------------------------------------------
    # 7. Prompts 体系测试
    # -------------------------------------------------------------------------
    def test_prompts_construction(self):
        """测试系统提示词构建与技能清单注入"""
        sys_prompt = build_system()
        self.assertIn("MiniCodingAgent", sys_prompt)
        self.assertIn(str(WORKDIR), sys_prompt)
        self.assertIn("Layer 1 Available Skills Catalog", sys_prompt)
        self.assertIn("agent-builder", sys_prompt)

        self.assertIn("subagent", SUB_SYSTEM.lower())
        self.assertIn("CANNOT delegate or spawn further subagents", SUB_SYSTEM)

    # -------------------------------------------------------------------------
    # 8. Compaction 上下文压缩管线单元测试
    # -------------------------------------------------------------------------
    def test_compaction_pipeline_units(self):
        """测试 tool_result_budget, snip_compact, micro_compact, should_auto_compact"""
        # 1. tool_result_budget
        huge_msgs = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": [{"type": "tool_use", "id": "t1", "name": "bash", "input": {}}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "Z" * 300_000}]},
        ]
        budgeted = tool_result_budget(huge_msgs, max_bytes=5_000)
        content_str = budgeted[-1]["content"][0]["content"]
        self.assertIn("[Output too large", content_str)
        self.assertIn(str(STORAGE_DIR), content_str)

        # 2. snip_compact
        messages_60 = [{"role": "user", "content": f"msg {i}"} for i in range(60)]
        snipped = snip_compact(messages_60, max_messages=10)
        self.assertIn("[snipped 50 messages", snipped[3]["content"])

        # 3. micro_compact
        old_tool_msgs = [
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": f"id_{i}", "content": "K" * 200}]}
            for i in range(5)
        ]
        compacted = micro_compact(old_tool_msgs)
        self.assertIn("[Earlier tool result compacted", compacted[0]["content"][0]["content"])
        self.assertEqual("K" * 200, compacted[-1]["content"][0]["content"])

        # 4. should_auto_compact 动态判定
        small_msgs = [{"role": "user", "content": "hi"}]
        self.assertFalse(should_auto_compact(small_msgs, limit=10000))
        self.assertTrue(should_auto_compact(small_msgs, limit=5))

        # 5. transcript 归档写入
        sample_msgs = [
            {"role": "user", "content": "test transcript"},
            {"role": "assistant", "content": [TextBlock(text="reply", type="text")]},
        ]
        t_file = _write_transcript(sample_msgs)
        self.assertTrue(t_file.exists())
        self.assertIn("test transcript", t_file.read_text(encoding="utf-8"))
        t_file.unlink(missing_ok=True)

        # 6. _format_messages_for_summary
        formatted = _format_messages_for_summary(sample_msgs)
        self.assertIn("USER:\ntest transcript", formatted)
        self.assertIn("ASSISTANT:\nreply", formatted)


class TestAgentLoopCompactionAndQA(unittest.TestCase):
    """
    与 Agent 持续问答并触发 [auto-compact] 和 [Reactive Compaction] 的完整端到端测试
    """

    def setUp(self):
        scan_skills()
        setup_default_hooks()
        state.reset_rounds()
        state.current_todos.clear()

    def tearDown(self):
        for pattern in ["code_review*.md", "scratch_*.txt", "temp_*.txt", "test_*.txt"]:
            for f in WORKDIR.glob(pattern):
                f.unlink(missing_ok=True)

    def test_01_agent_multi_turn_qa_and_tools(self):
        """
        测试 Agent 多轮真实问答：调用 glob, load_skill, todo_write 等工具完成任务
        """
        history = []

        # Turn 1: 提问文件定位 (glob 工具)
        history.append({"role": "user", "content": "Please use glob to find python files in the workspace."})
        agent_loop(history)
        self.assertGreaterEqual(len(history), 2)
        last_resp = history[-1]["content"]
        resp_text = "".join(getattr(b, "text", "") for b in last_resp if getattr(b, "type", None) == "text")
        self.assertTrue(len(resp_text) > 0 or len(last_resp) > 0)

        # Turn 2: 提问技能加载与查看 (load_skill 工具)
        history.append({"role": "user", "content": "Please load the 'code-review' skill using load_skill and state its main goal in 1-2 sentences."})
        agent_loop(history)
        self.assertGreaterEqual(len(history), 4)

        # Turn 3: 任务管理 (todo_write 工具)
        history.append({"role": "user", "content": "Create a todo checklist using todo_write with 2 items: 1) Run test (completed), 2) Finish verification (completed)."})
        agent_loop(history)
        self.assertGreaterEqual(len(state.current_todos), 1)

    def test_02_trigger_auto_compact_during_qa(self):
        """
        测试持续问答直到触发 [auto-compact] 自动上下文压缩机制
        """
        import MiniCodingAgent.compact as compact
        orig_limit = compact.DEFAULT_CONTEXT_CHAR_LIMIT

        try:
            # 设置较小的压缩阈值，确保在问答中能够稳定触发 [auto-compact]
            compact.DEFAULT_CONTEXT_CHAR_LIMIT = 1200

            history = []
            captured_stdout = io.StringIO()

            with contextlib.redirect_stdout(captured_stdout):
                # 第一轮问答
                history.append({"role": "user", "content": "List 5 essential coding principles for Python developers."})
                agent_loop(history)

                # 第二轮问答：上下文累积增加
                history.append({"role": "user", "content": "Now elaborate on principles 1 and 2 in detail with code examples."})
                agent_loop(history)

                # 第三轮问答：继续累积，确保超过 1200 字符限制触发 [auto-compact]
                history.append({"role": "user", "content": "Now explain principle 3 with code examples."})
                agent_loop(history)

            output_text = captured_stdout.getvalue()
            print(f"\n[Test Auto-Compact Output Summary]:\n{output_text[:300]}...\n")

            # 验证触发了 [auto-compact] 标记
            self.assertIn(
                "[auto-compact]",
                output_text,
                "Failed to trigger [auto-compact] during continuous Q&A!"
            )

            # 验证历史中包含压缩摘要标记或被成功压缩
            has_compacted = any("[Compacted]" in str(m.get("content", "")) for m in history)
            self.assertTrue(
                has_compacted or len(history) <= 4,
                "History was expected to be compacted after auto-compact trigger"
            )

        finally:
            compact.DEFAULT_CONTEXT_CHAR_LIMIT = orig_limit

    def test_03_trigger_reactive_compaction_during_qa(self):
        """
        测试在问答过程中捕获 BadRequestError (Prompt Too Long / Token Overflow)
        并触发 [Reactive Compaction] 反应式压缩重试
        """
        real_messages_create = client.messages.create
        simulated_overflow_triggered = False

        def mock_messages_create(*args, **kwargs):
            nonlocal simulated_overflow_triggered
            # 第一次调用模拟产生 prompt_too_long 异常
            if not simulated_overflow_triggered:
                simulated_overflow_triggered = True
                req = httpx.Request("POST", "http://localhost:4000/v1/messages")
                resp = httpx.Response(status_code=400, request=req)
                raise BadRequestError(
                    message="prompt_too_long: too many tokens in context window",
                    response=resp,
                    body={"error": {"message": "prompt_too_long"}}
                )
            # 重试时调用真实 API
            return real_messages_create(*args, **kwargs)

        history = [
            {"role": "user", "content": "Hello agent, what is 42 * 2?"},
            {"role": "assistant", "content": [TextBlock(text="42 * 2 is 84.", type="text")]},
            {"role": "user", "content": "Now multiply that result by 10 and output only the number."}
        ]

        captured_stdout = io.StringIO()
        with patch.object(client.messages, "create", side_effect=mock_messages_create):
            with contextlib.redirect_stdout(captured_stdout):
                agent_loop(history)

        output_text = captured_stdout.getvalue()
        print(f"\n[Test Reactive-Compaction Output Summary]:\n{output_text}\n")

        # 验证触发了 [Reactive Compaction]
        self.assertTrue(simulated_overflow_triggered, "Mock overflow was not called")
        self.assertIn(
            "[Reactive Compaction]",
            output_text,
            "Failed to trigger [Reactive Compaction] on prompt_too_long error!"
        )

        # 验证在反应式压缩后重试成功并获得了最终回复
        self.assertGreaterEqual(len(history), 2)
        last_msg = history[-1]
        self.assertEqual(last_msg["role"], "assistant")

    def test_04_todo_reminder_injection_after_3_rounds(self):
        """
        测试连续 3 轮未更新 todo_write 时的催促机制 (<reminder>)
        """
        history = [{"role": "user", "content": "Step 1"}]
        # 模拟 rounds_since_todo 计数达到 3
        state.rounds_since_todo = 3

        # 运行一轮测试催促注入
        with patch.object(client.messages, "create", return_value=type("MockResp", (), {
            "content": [TextBlock(text="OK", type="text")],
            "stop_reason": "end_turn"
        })()):
            agent_loop(history)

        # 验证消息历史中被注入了 <reminder>
        has_reminder = any("<reminder>" in str(m.get("content", "")) for m in history)
        self.assertTrue(has_reminder, "Expected <reminder> to be injected when rounds_since_todo >= 3")
        self.assertEqual(state.rounds_since_todo, 0)


def create_suite():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestMiniCodingAgentFeatures))
    suite.addTests(loader.loadTestsFromTestCase(TestAgentLoopCompactionAndQA))
    return suite


def run_three_rounds():
    """
    运行三轮完整测试，必须三轮全部 0 报错通过
    """
    print("\n" + "=" * 70)
    print("🚀 开始执行 MiniCodingAgent 全功能与压缩机制验证 (三轮测试)")
    print("=" * 70)

    total_rounds = 3
    passed_rounds = 0

    for round_num in range(1, total_rounds + 1):
        print(f"\n▶ 正在进行第 {round_num}/{total_rounds} 轮完整测试...")
        suite = create_suite()
        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)

        if not result.wasSuccessful():
            print(f"\n❌ 第 {round_num} 轮测试失败! 发现 {len(result.errors)} 个错误, {len(result.failures)} 个失败.")
            return False

        passed_rounds += 1
        print(f"✅ 第 {round_num}/{total_rounds} 轮测试全部通过! (0 错误, 0 失败)")

    print("\n" + "=" * 70)
    print(f"🎉 恭喜！连续 {passed_rounds}/{total_rounds} 轮完整测试全部通过，所有功能正常，压缩机制验证无误！")
    print("=" * 70 + "\n")
    return True


if __name__ == "__main__":
    success = run_three_rounds()
    sys.exit(0 if success else 1)

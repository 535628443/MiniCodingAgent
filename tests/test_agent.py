import sys
import unittest
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from MiniCodingAgent.state import state
from MiniCodingAgent.hooks import trigger_hooks, setup_default_hooks
from MiniCodingAgent.tools.system import safe_path
from MiniCodingAgent.tools.files import run_read, run_write, run_edit, run_glob
from MiniCodingAgent.tools.todo import run_todo_write
from MiniCodingAgent.tools.skill import scan_skills, load_skill, list_skills


class TestMiniCodingAgentCore(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scan_skills()
        setup_default_hooks()

    def setUp(self):
        state.reset_rounds()
        state.current_todos.clear()

    def test_skills_scanning_and_loading(self):
        self.assertGreater(len(state.skill_registry), 0)
        skills = list(state.skill_registry.keys())
        self.assertIn("agent-builder", skills)
        content = load_skill("agent-builder")
        self.assertIn("agent-builder", content.lower())

    def test_file_operations(self):
        test_file = "scratch_test_file.txt"
        w_res = run_write(test_file, "Line 1\nLine 2\nLine 3\n")
        self.assertIn("Wrote", w_res)

        r_res = run_read(test_file)
        self.assertIn("Line 2", r_res)

        e_res = run_edit(test_file, "Line 2", "Modified Line 2")
        self.assertIn("Edited", e_res)

        r_res_after = run_read(test_file)
        self.assertIn("Modified Line 2", r_res_after)

        g_res = run_glob("scratch_test_*.txt")
        self.assertIn(test_file, g_res)

        safe_path(test_file).unlink(missing_ok=True)

    def test_todo_write(self):
        todos = [
            {"content": "Step 1: Init", "status": "completed"},
            {"content": "Step 2: Execution", "status": "in_progress"},
            {"content": "Step 3: Verification", "status": "pending"}
        ]
        res = run_todo_write(todos)
        self.assertIn("Updated 3 tasks", res)
        self.assertEqual(len(state.current_todos), 3)
        self.assertEqual(state.current_todos[0]["status"], "completed")

    def test_permission_hook(self):
        class FakeBlock:
            name = "bash"
            input = {"command": "rm -rf /critical/data"}

        blocked = trigger_hooks("PreToolUse", FakeBlock())
        self.assertEqual(blocked, "Permission denied")

    def test_compaction_pipeline(self):
        from MiniCodingAgent.compact import snip_compact, micro_compact, tool_result_budget, should_auto_compact

        # 1. Test tool_result_budget with normal text and huge tool result
        messages = [
            {"role": "user", "content": "initial prompt"},
            {"role": "assistant", "content": [{"type": "tool_use", "id": "call_1", "name": "read_file", "input": {}}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "call_1", "content": "x" * 300_000}]}
        ]
        budgeted = tool_result_budget(messages, max_bytes=10_000)
        self.assertIn("[Output too large", budgeted[-1]["content"][0]["content"])

        # 2. Test snip_compact
        long_messages = [{"role": "user", "content": f"msg {i}"} for i in range(60)]
        snipped = snip_compact(long_messages, max_messages=10)
        self.assertEqual(len(snipped), 11)  # 3 head + 1 placeholder + 7 tail
        self.assertIn("[snipped", snipped[3]["content"])

        # 3. Test micro_compact
        tool_msgs = [
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": f"t_{i}", "content": "a" * 200}]}
            for i in range(6)
        ]
        micro_compacted = micro_compact(tool_msgs)
        # First 3 should be compacted
        self.assertIn("[Earlier tool result compacted", micro_compacted[0]["content"][0]["content"])
        # Last 3 should remain untouched
        self.assertEqual("a" * 200, micro_compacted[-1]["content"][0]["content"])

    def test_tool_use_block_compaction_and_transcript(self):
        from anthropic.types import ToolUseBlock, TextBlock
        from MiniCodingAgent.compact import _write_transcript, _format_messages_for_summary, _estimate_chars, tool_result_budget

        # Test message sequence containing SDK objects
        messages = [
            {"role": "user", "content": "Can you check files?"},
            {
                "role": "assistant",
                "content": [
                    TextBlock(text="Let me inspect the directory", type="text"),
                    ToolUseBlock(id="call_99", input={"command": "ls -la"}, name="bash", type="tool_use")
                ]
            },
            {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "call_99", "content": "file1.txt\nfile2.txt"}]
            }
        ]

        # 1. Test transcript writing with ToolUseBlock (should not raise TypeError)
        transcript_file = _write_transcript(messages)
        self.assertTrue(transcript_file.exists())
        transcript_text = transcript_file.read_text(encoding="utf-8")
        self.assertIn("call_99", transcript_text)
        self.assertIn("bash", transcript_text)
        transcript_file.unlink(missing_ok=True)

        # 2. Test format for summary
        summary_prompt = _format_messages_for_summary(messages)
        self.assertIn("USER:", summary_prompt)
        self.assertIn("ASSISTANT:", summary_prompt)
        self.assertIn("[Tool Call: bash", summary_prompt)

        # 3. Test estimate chars
        char_count = _estimate_chars(messages)
        self.assertGreater(char_count, 50)

    def test_task_guard_hook(self):
        # When todos have pending/in_progress tasks, trigger_hooks("Stop") should return warning
        state.current_todos = [
            {"content": "Read all files", "status": "in_progress"},
            {"content": "Generate summary", "status": "pending"}
        ]
        res = trigger_hooks("Stop", [])
        self.assertIsNotNone(res)
        self.assertIn("unfinished tasks", res)
        self.assertIn("Read all files", res)

        # When todos are all completed, Stop hook should return None (allowing stop)
        state.current_todos = [
            {"content": "Read all files", "status": "completed"},
            {"content": "Generate summary", "status": "completed"}
        ]
        res = trigger_hooks("Stop", [])
        self.assertIsNone(res)


if __name__ == "__main__":
    unittest.main()

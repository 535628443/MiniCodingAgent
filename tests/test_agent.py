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


if __name__ == "__main__":
    unittest.main()

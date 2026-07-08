import os
import tempfile
import unittest

import config
from agents.qa import QAIssue, QAResult
from main import Orchestrator


class FakePlanner:
    def get_model(self):
        return "fake-model"


class FakeDeveloper:
    def __init__(self, staging_dir, writes):
        self.staging_dir = staging_dir
        self.writes = list(writes)
        self.calls = []
        self.feedbacks = []

    def write_code(
        self,
        user_request,
        approved_plan,
        step_instruction,
        codebase_context,
        qa_feedback="",
        image_paths=None,
    ):
        self.calls.append(step_instruction)
        self.feedbacks.append(qa_feedback)
        attempt = len(self.calls) - 1
        write_set = self.writes[min(attempt, len(self.writes) - 1)]
        for rel_path, content in write_set.items():
            full = os.path.join(self.staging_dir, rel_path)
            os.makedirs(os.path.dirname(full) or self.staging_dir, exist_ok=True)
            with open(full, "w", encoding="utf-8") as f:
                f.write(content)
        return f"fake developer attempt {attempt + 1}"


class StepAwareDeveloper:
    def __init__(self, staging_dir):
        self.staging_dir = staging_dir
        self.calls = []

    def write_code(
        self,
        user_request,
        approved_plan,
        step_instruction,
        codebase_context,
        qa_feedback="",
        image_paths=None,
    ):
        self.calls.append(step_instruction)
        filename = step_instruction.replace(" ", "_") + ".py"
        full = os.path.join(self.staging_dir, filename)
        os.makedirs(os.path.dirname(full) or self.staging_dir, exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(f"STEP = {step_instruction!r}\n")
        return f"wrote {filename}"


class FakeQA:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def review_code(self, user_request, approved_plan, step_instruction, staged_files):
        self.calls.append({
            "step": step_instruction,
            "files": list(staged_files),
        })
        idx = len(self.calls) - 1
        return self.results[min(idx, len(self.results) - 1)]


class MalformedQA:
    def __init__(self):
        self.calls = []

    def review_code(self, user_request, approved_plan, step_instruction, staged_files):
        self.calls.append(list(staged_files))
        return {"decision": "APPROVED"}


class NoSpecOrchestrator(Orchestrator):
    def _update_project_spec(self, step_idx, step, staged_files):
        return None


class StagingWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.target = self.tmp.name
        self.old_max_code_iterations = config.MAX_CODE_ITERATIONS
        config.MAX_CODE_ITERATIONS = 3

    def tearDown(self):
        config.MAX_CODE_ITERATIONS = self.old_max_code_iterations
        self.tmp.cleanup()

    def make_orchestrator(self):
        return NoSpecOrchestrator(self.target)

    def test_approved_staged_file_is_promoted(self):
        orch = self.make_orchestrator()
        orch.developer = FakeDeveloper(orch.staging_dir, [
            {"app.py": "def answer():\n    return 42\n"}
        ])
        orch.qa = FakeQA([
            QAResult("APPROVED", "looks good", [])
        ])

        ok = orch._run_step("build app", "plan", "create app.py", 1, [])

        self.assertTrue(ok)
        self.assertTrue(os.path.isfile(os.path.join(self.target, "app.py")))
        self.assertEqual(orch._list_staged_files(), [])

    def test_rejection_feedback_retries_and_promotes_second_attempt(self):
        orch = self.make_orchestrator()
        orch.developer = FakeDeveloper(orch.staging_dir, [
            {"app.py": "def value():\n    return 1\n"},
            {"app.py": "def value():\n    return 2\n"},
        ])
        orch.qa = FakeQA([
            QAResult(
                "REJECTED",
                "wrong return value",
                [QAIssue("app.py", "value() must return 2", "return 1", "return 2")],
            ),
            QAResult("APPROVED", "fixed", []),
        ])

        ok = orch._run_step("build app", "plan", "create app.py", 1, [])

        self.assertTrue(ok)
        self.assertEqual(len(orch.qa.calls), 2)
        self.assertIn("QA REJECTION", orch.developer.feedbacks[1])
        with open(os.path.join(self.target, "app.py"), encoding="utf-8") as f:
            self.assertIn("return 2", f.read())

    def test_syntax_failure_blocks_qa_and_retries(self):
        orch = self.make_orchestrator()
        orch.developer = FakeDeveloper(orch.staging_dir, [
            {"app.py": "def broken(:\n    pass\n"},
            {"app.py": "def fixed():\n    return True\n"},
        ])
        orch.qa = FakeQA([
            QAResult("APPROVED", "syntax is fixed", [])
        ])

        ok = orch._run_step("build app", "plan", "create app.py", 1, [])

        self.assertTrue(ok)
        self.assertEqual(len(orch.qa.calls), 1)
        self.assertIn("Orchestrator-side staged file validation failed", orch.developer.feedbacks[1])
        with open(os.path.join(self.target, "app.py"), encoding="utf-8") as f:
            self.assertIn("def fixed", f.read())

    def test_step_scope_blocks_extra_staged_files_before_qa(self):
        orch = self.make_orchestrator()
        orch.developer = FakeDeveloper(orch.staging_dir, [
            {
                "index.html": "<!DOCTYPE html><html><body></body></html>\n",
                "static/js/main.js": "console.log('future step');\n",
            },
            {"index.html": "<!DOCTYPE html><html><body><main></main></body></html>\n"},
        ])
        orch.qa = FakeQA([
            QAResult("APPROVED", "scoped file ok", [])
        ])

        ok = orch._run_step("build app", "plan", "create index.html skeleton", 1, [])

        self.assertTrue(ok)
        self.assertEqual(len(orch.qa.calls), 1)
        self.assertIn("outside the current step scope", orch.developer.feedbacks[1])
        self.assertTrue(os.path.exists(os.path.join(self.target, "index.html")))
        self.assertFalse(os.path.exists(os.path.join(self.target, "static", "js", "main.js")))

    def test_invalid_plan_shape_is_rejected_locally(self):
        orch = self.make_orchestrator()

        issues = orch._validate_plan_shape("I will build the app from scratch.")

        self.assertTrue(any("Sub-tasks Checklist" in issue for issue in issues))
        self.assertTrue(any("Proposed Changes" in issue for issue in issues))

    def test_unapproved_step_fails_workflow_and_does_not_promote(self):
        config.MAX_CODE_ITERATIONS = 1
        orch = self.make_orchestrator()
        orch.developer = FakeDeveloper(orch.staging_dir, [
            {"app.py": "def value():\n    return 1\n"}
        ])
        orch.qa = FakeQA([
            QAResult(
                "REJECTED",
                "wrong behavior",
                [QAIssue("app.py", "not acceptable", None, "return the expected value")],
            )
        ])

        ok = orch._run_dev_loop("build app", "plan", ["create app.py"], 0, [])

        self.assertFalse(ok)
        self.assertFalse(os.path.exists(os.path.join(self.target, "app.py")))
        self.assertEqual(orch._list_staged_files(), [])

    def test_malformed_qa_result_is_rejected_and_not_promoted(self):
        config.MAX_CODE_ITERATIONS = 1
        orch = self.make_orchestrator()
        orch.developer = FakeDeveloper(orch.staging_dir, [
            {"app.py": "def value():\n    return 1\n"}
        ])
        orch.qa = MalformedQA()

        ok = orch._run_step("build app", "plan", "create app.py", 1, [])

        self.assertFalse(ok)
        self.assertFalse(os.path.exists(os.path.join(self.target, "app.py")))
        self.assertEqual(orch._list_staged_files(), [])

    def test_resume_starts_from_checkpoint_step(self):
        orch = self.make_orchestrator()
        orch.planner = FakePlanner()
        orch.developer = StepAwareDeveloper(orch.staging_dir)
        orch.qa = FakeQA([
            QAResult("APPROVED", "second step ok", [])
        ])
        sub_tasks = ["first step", "second step"]
        orch.ltm.save_checkpoint(1, sub_tasks, "plan")

        ok = orch.run("build app", resume=True)

        self.assertTrue(ok)
        self.assertEqual(orch.developer.calls, ["second step"])
        self.assertFalse(os.path.exists(os.path.join(self.target, "first_step.py")))
        self.assertTrue(os.path.exists(os.path.join(self.target, "second_step.py")))
        self.assertIsNone(orch.ltm.load_checkpoint())


if __name__ == "__main__":
    unittest.main()

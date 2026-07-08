import unittest

from agents.qa import QAAgent


class QAParserTests(unittest.TestCase):
    def test_bare_approved_is_accepted(self):
        result = QAAgent()._parse("APPROVED")

        self.assertTrue(result.approved)

    def test_bare_rejected_has_actionable_issue(self):
        result = QAAgent()._parse("REJECTED")

        self.assertFalse(result.approved)
        self.assertTrue(result.issues)
        self.assertIn("bare REJECTED", result.issues[0].issue)


if __name__ == "__main__":
    unittest.main()

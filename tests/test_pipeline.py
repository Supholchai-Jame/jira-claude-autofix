"""
Unit tests for the Claude AI Pipeline components.
External services (Jira, GitHub, Anthropic API) are mocked.
"""
from unittest.mock import MagicMock, patch

import pytest

from pipeline.claude_agent import ClaudeAgent
from pipeline.jira_client import JiraClient
from pipeline.validator import Validator


# ── ClaudeAgent ─────────────────────────────────────────────────────────────

class TestClaudeAgentParseResponse:
    def setup_method(self):
        with patch("anthropic.Anthropic"):
            self.agent = ClaudeAgent.__new__(ClaudeAgent)
            self.agent._system_prompt = "You are a developer."

    def test_parses_single_modified_file(self):
        response = (
            '<modified_file path="src/foo.py">\n'
            'def foo():\n    return 42\n'
            '</modified_file>'
        )
        result = self.agent._parse_response(response)
        assert "src/foo.py" in result
        assert "def foo():" in result["src/foo.py"]

    def test_parses_multiple_modified_files(self):
        response = (
            '<modified_file path="a.py">\nprint("a")\n</modified_file>\n'
            '<modified_file path="b.py">\nprint("b")\n</modified_file>'
        )
        result = self.agent._parse_response(response)
        assert len(result) == 2
        assert "a.py" in result
        assert "b.py" in result

    def test_returns_empty_on_no_changes_needed(self):
        result = self.agent._parse_response("NO_CHANGES_NEEDED")
        assert result == {}

    def test_returns_empty_when_no_tags_present(self):
        result = self.agent._parse_response("Here is some explanation with no file tags.")
        assert result == {}

    def test_format_files(self):
        files = {"src/main.py": "x = 1"}
        output = self.agent._format_files(files)
        assert "src/main.py" in output
        assert "x = 1" in output


# ── JiraClient ───────────────────────────────────────────────────────────────

class TestJiraClient:
    def _make_client(self, mock_jira):
        client = JiraClient.__new__(JiraClient)
        client._jira = mock_jira
        return client

    def test_get_ticket_returns_expected_fields(self):
        mock_issue = MagicMock()
        mock_issue.fields.summary = "Fix login bug"
        mock_issue.fields.description = "Users cannot log in with SSO."
        mock_issue.fields.status.name = "In Progress"
        mock_issue.fields.issuetype.name = "Bug"
        mock_issue.fields.customfield_10016 = None

        mock_jira = MagicMock()
        mock_jira.issue.return_value = mock_issue

        client = self._make_client(mock_jira)
        ticket = client.get_ticket("PROJ-1")

        assert ticket["summary"] == "Fix login bug"
        assert ticket["status"] == "In Progress"
        assert "SSO" in ticket["description"]

    def test_get_ticket_appends_acceptance_criteria(self):
        mock_issue = MagicMock()
        mock_issue.fields.summary = "Add feature"
        mock_issue.fields.description = "Base description."
        mock_issue.fields.status.name = "To Do"
        mock_issue.fields.issuetype.name = "Story"
        mock_issue.fields.customfield_10016 = "- Must work on mobile"

        mock_jira = MagicMock()
        mock_jira.issue.return_value = mock_issue

        client = self._make_client(mock_jira)
        ticket = client.get_ticket("PROJ-2")

        assert "Acceptance Criteria" in ticket["description"]
        assert "Must work on mobile" in ticket["description"]

    def test_transition_issue_raises_when_not_found(self):
        mock_jira = MagicMock()
        mock_jira.transitions.return_value = [{"id": "1", "name": "Done"}]

        client = self._make_client(mock_jira)
        with pytest.raises(ValueError, match="In Review"):
            client.transition_issue("PROJ-1", "In Review")

    def test_transition_issue_succeeds(self):
        mock_jira = MagicMock()
        mock_jira.transitions.return_value = [{"id": "21", "name": "In Review"}]

        client = self._make_client(mock_jira)
        client.transition_issue("PROJ-1", "In Review")

        mock_jira.transition_issue.assert_called_once_with("PROJ-1", "21")


# ── Validator ────────────────────────────────────────────────────────────────

class TestValidator:
    def test_run_tests_returns_true_on_success(self, tmp_path):
        validator = Validator(str(tmp_path))
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="1 passed", stderr="")
            passed, output = validator.run_tests()
        assert passed is True
        assert "passed" in output

    def test_run_tests_returns_false_on_failure(self, tmp_path):
        validator = Validator(str(tmp_path))
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stdout="", stderr="AssertionError"
            )
            passed, output = validator.run_tests()
        assert passed is False
        assert "AssertionError" in output

    def test_run_lint_passes_on_valid_files(self, tmp_path):
        (tmp_path / "ok.py").write_text("x = 1\n")
        validator = Validator(str(tmp_path))
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            passed, _ = validator.run_lint()
        assert passed is True

    def test_run_lint_fails_on_syntax_error(self, tmp_path):
        (tmp_path / "bad.py").write_text("def broken(\n")
        validator = Validator(str(tmp_path))
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="SyntaxError")
            passed, output = validator.run_lint()
        assert passed is False
        assert "bad.py" in output

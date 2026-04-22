import logging
import re
import subprocess
from datetime import datetime
from pathlib import Path

_LOG_FILE = Path(__file__).parent.parent / "pipeline.log"


def _setup_logger() -> logging.Logger:
    logger = logging.getLogger("claude_pipeline")
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)
    handler = logging.FileHandler(_LOG_FILE, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s"))
    logger.addHandler(handler)
    return logger


_log = _setup_logger()


class ClaudeAgent:
    def __init__(self, api_key: str = "", model: str = "claude-sonnet-4-6"):
        self.model = model
        self._system_prompt = self._load_system_prompt()
        self._history: list[str] = []
        self._files_context: str = ""

    def fix_code(
        self,
        task_description: str,
        files: dict[str, str],
    ) -> dict[str, str]:
        self._history = []
        self._files_context = self._format_files(files)
        user_msg = (
            f"{self._files_context}\n\n"
            f"## Jira Task\n\n{task_description}\n\n"
            "Implement or fix the code as described above."
        )
        prompt = self._build_prompt(user_msg)

        _log.info("=== Step 4: Claude fix_code started ===")
        _log.info("Model: %s", self.model)
        _log.info("Files in context: %s", list(files.keys()))
        _log.debug("--- PROMPT START ---\n%s\n--- PROMPT END ---", prompt)

        response_text = self._call_claude(prompt)

        _log.debug("--- RESPONSE START ---\n%s\n--- RESPONSE END ---", response_text)

        self._history.append(f"User: {user_msg}\n\nAssistant: {response_text}")
        modified = self._parse_response(response_text)

        if modified:
            _log.info("Modified files (%d): %s", len(modified), list(modified.keys()))
        else:
            _log.info("No files modified (NO_CHANGES_NEEDED or no tags found)")

        return modified

    def _build_prompt(self, user_msg: str) -> str:
        parts = [self._system_prompt, ""]
        if self._history:
            parts += self._history
            parts.append("")
        parts.append(user_msg)
        return "\n".join(parts)

    def _call_claude(self, prompt: str) -> str:
        _log.info("Calling Claude CLI (model=%s) ...", self.model)
        result = subprocess.run(
            ["claude", "-p", prompt, "--model", self.model],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            _log.error("Claude CLI exited %d:\n%s", result.returncode, result.stderr)
            raise RuntimeError(f"Claude CLI error:\n{result.stderr}")
        _log.info("Claude CLI finished (exit 0, %d chars)", len(result.stdout))
        return result.stdout.strip()

    def _format_files(self, files: dict[str, str]) -> str:
        parts = ["## Current Codebase\n"]
        for path, content in files.items():
            parts.append(f"### File: {path}\n```\n{content}\n```\n")
        return "\n".join(parts)

    def _parse_response(self, text: str) -> dict[str, str]:
        if "NO_CHANGES_NEEDED" in text:
            return {}
        pattern = r'<modified_file path="([^"]+)">\n(.*?)\n</modified_file>'
        matches = re.findall(pattern, text, re.DOTALL)
        return dict(matches)

    def _load_system_prompt(self) -> str:
        prompt_path = Path(__file__).parent.parent / "prompts" / "coding_agent.txt"
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8")
        return (
            "You are a senior software engineer. Fix or implement code based on the given task. "
            'Return modified files using <modified_file path="..."> tags.'
        )

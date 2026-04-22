import re
import subprocess
from pathlib import Path


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
        response_text = self._call_claude(prompt)
        self._history.append(f"User: {user_msg}\n\nAssistant: {response_text}")
        return self._parse_response(response_text)

    def _build_prompt(self, user_msg: str) -> str:
        parts = [self._system_prompt, ""]
        if self._history:
            parts += self._history
            parts.append("")
        parts.append(user_msg)
        return "\n".join(parts)

    def _call_claude(self, prompt: str) -> str:
        result = subprocess.run(
            ["claude", "-p", prompt, "--model", self.model],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            raise RuntimeError(f"Claude CLI error:\n{result.stderr}")
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

import re
from pathlib import Path

import anthropic


class ClaudeAgent:
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6"):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self._system_prompt = self._load_system_prompt()

    def fix_code(
        self,
        task_description: str,
        files: dict[str, str],
        test_error: str = None,
        iteration: int = 1,
    ) -> dict[str, str]:
        """
        Send task + code to Claude and return modified files.

        files: {filepath: content}
        Returns: {filepath: new_content}
        """
        if iteration == 1:
            self._conversation: list[dict] = []
            self._files_context = self._format_files(files)

        if iteration == 1:
            user_content = [
                # Cache the files context — reused across retry iterations
                {
                    "type": "text",
                    "text": self._files_context,
                    "cache_control": {"type": "ephemeral"},
                },
                {
                    "type": "text",
                    "text": f"## Jira Task\n\n{task_description}\n\nImplement or fix the code as described above.",
                },
            ]
        else:
            user_content = [
                {
                    "type": "text",
                    "text": (
                        f"## Test Failures (Attempt {iteration})\n\n"
                        f"```\n{test_error}\n```\n\n"
                        "The tests above are failing. Fix the code so all tests pass. "
                        "Return only the files that need to change."
                    ),
                }
            ]

        self._conversation.append({"role": "user", "content": user_content})

        response = self.client.messages.create(
            model=self.model,
            max_tokens=8096,
            system=[
                {
                    "type": "text",
                    "text": self._system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=self._conversation,
        )

        assistant_text = response.content[0].text
        self._conversation.append({"role": "assistant", "content": assistant_text})

        return self._parse_response(assistant_text)

    def _format_files(self, files: dict[str, str]) -> str:
        parts = ["## Current Codebase\n"]
        for path, content in files.items():
            parts.append(f"### File: {path}\n```python\n{content}\n```\n")
        return "\n".join(parts)

    def _parse_response(self, text: str) -> dict[str, str]:
        if "NO_CHANGES_NEEDED" in text:
            return {}

        pattern = r'<modified_file path="([^"]+)">\n(.*?)\n</modified_file>'
        matches = re.findall(pattern, text, re.DOTALL)

        return {path: content for path, content in matches}

    def _load_system_prompt(self) -> str:
        prompt_path = Path(__file__).parent.parent / "prompts" / "coding_agent.txt"
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8")
        return (
            "You are a senior software engineer. Fix or implement code based on the given task. "
            "Return modified files using <modified_file path=\"...\"> tags."
        )

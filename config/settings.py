import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    claude_model: str = field(default_factory=lambda: os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6"))

    jira_server: str = field(default_factory=lambda: os.getenv("JIRA_SERVER", ""))
    jira_email: str = field(default_factory=lambda: os.getenv("JIRA_EMAIL", ""))
    jira_api_token: str = field(default_factory=lambda: os.getenv("JIRA_API_TOKEN", ""))
    jira_review_transition: str = field(default_factory=lambda: os.getenv("JIRA_REVIEW_TRANSITION", "In Review"))

    github_token: str = field(default_factory=lambda: os.getenv("GITHUB_TOKEN", ""))
    github_repo: str = field(default_factory=lambda: os.getenv("GITHUB_REPO", ""))

    repo_local_path: str = field(default_factory=lambda: os.getenv("REPO_LOCAL_PATH", "."))

    def validate(self):
        required = {
            "ANTHROPIC_API_KEY": self.anthropic_api_key,
            "JIRA_SERVER": self.jira_server,
            "JIRA_EMAIL": self.jira_email,
            "JIRA_API_TOKEN": self.jira_api_token,
        }
        missing = [k for k, v in required.items() if not v]
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

    @property
    def github_enabled(self) -> bool:
        return bool(self.github_token and self.github_repo)

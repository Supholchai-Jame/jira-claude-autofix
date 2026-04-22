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

    gitlab_token: str = field(default_factory=lambda: os.getenv("GITLAB_TOKEN", ""))
    gitlab_repo: str = field(default_factory=lambda: os.getenv("GITLAB_REPO", ""))
    gitlab_server: str = field(default_factory=lambda: os.getenv("GITLAB_SERVER", "https://gitlab.com"))
    gitlab_ssl_verify: bool = field(default_factory=lambda: os.getenv("GITLAB_SSL_VERIFY", "true").lower() != "false")

    repo_local_path: str = field(default_factory=lambda: os.getenv("REPO_LOCAL_PATH", "."))
    default_dir: str = field(default_factory=lambda: os.getenv("DEFAULT_DIR", ""))
    scan_extensions: str = field(
        default_factory=lambda: os.getenv(
            "SCAN_EXTENSIONS", ".ts,.js,.java,.html,.scss,.css"
        )
    )

    @property
    def extension_list(self) -> list[str]:
        return [e.strip() for e in self.scan_extensions.split(",") if e.strip()]

    def validate(self):
        required = {
            "JIRA_SERVER": self.jira_server,
            "JIRA_EMAIL": self.jira_email,
            "JIRA_API_TOKEN": self.jira_api_token,
        }
        missing = [k for k, v in required.items() if not v]
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

    @property
    def gitlab_enabled(self) -> bool:
        return bool(self.gitlab_token and self.gitlab_repo)

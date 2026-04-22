from pathlib import Path

import git
import requests


class GitOperations:
    def __init__(self, repo_path: str, gitlab_token: str = "", gitlab_repo: str = "", gitlab_server: str = "https://gitlab.com", ssl_verify: bool = True):
        self.repo_path = Path(repo_path)
        self.repo = git.Repo(repo_path)
        self._gitlab_token = gitlab_token
        self._gitlab_repo = gitlab_repo
        self._gitlab_server = gitlab_server.rstrip("/")
        self._ssl_verify = ssl_verify

    def create_branch(self, branch_name: str):
        default_branch = self._get_default_branch()
        self.repo.git.checkout(default_branch)
        self.repo.git.pull("origin", default_branch)
        self.repo.git.checkout("-b", branch_name)

    def current_branch(self) -> str:
        return self.repo.active_branch.name

    BRANCH_PREFIXES = ("feature/", "fixbug/")

    def validate_branch_matches_ticket(self, ticket_id: str) -> tuple[bool, str]:
        branch = self.current_branch()
        ticket_slug = f"{ticket_id.lower()}-fix"
        for prefix in self.BRANCH_PREFIXES:
            if branch.lower() == f"{prefix}{ticket_slug}":
                return True, branch
        return False, branch

    def commit_and_push(self, file_paths: list[str], commit_message: str, branch_name: str):
        for fp in file_paths:
            self.repo.git.add(fp)

        self.repo.index.commit(commit_message)
        origin = self.repo.remote(name="origin")
        origin.push(refspec=f"{branch_name}:{branch_name}")

    def create_pull_request(
        self,
        branch: str,
        title: str,
        body: str,
        draft: bool = False,
    ) -> str:
        if not self._gitlab_token or not self._gitlab_repo:
            return f"(GitLab not configured — branch '{branch}' pushed but no MR created)"

        encoded_repo = self._gitlab_repo.replace("/", "%2F")
        url = f"{self._gitlab_server}/api/v4/projects/{encoded_repo}/merge_requests"
        default_branch = self._get_default_branch()

        payload = {
            "source_branch": branch,
            "target_branch": default_branch,
            "title": title,
            "description": body,
            "draft": draft,
        }
        headers = {"PRIVATE-TOKEN": self._gitlab_token}
        resp = requests.post(url, json=payload, headers=headers, verify=self._ssl_verify)
        resp.raise_for_status()
        return resp.json().get("web_url", "(MR created but URL not returned)")

    def _get_default_branch(self) -> str:
        try:
            return self.repo.git.symbolic_ref("refs/remotes/origin/HEAD").split("/")[-1]
        except git.GitCommandError:
            for name in ("main", "master"):
                try:
                    self.repo.git.rev_parse("--verify", f"origin/{name}")
                    return name
                except git.GitCommandError:
                    continue
        return "main"

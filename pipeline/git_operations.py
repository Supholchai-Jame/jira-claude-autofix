from pathlib import Path

import git
from github import Github


class GitOperations:
    def __init__(self, repo_path: str, github_token: str = "", github_repo: str = ""):
        self.repo_path = Path(repo_path)
        self.repo = git.Repo(repo_path)
        self._github_token = github_token
        self._github_repo = github_repo

    def create_branch(self, branch_name: str):
        # Start from the latest main/master
        default_branch = self._get_default_branch()
        self.repo.git.checkout(default_branch)
        self.repo.git.pull("origin", default_branch)
        self.repo.git.checkout("-b", branch_name)

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
        if not self._github_token or not self._github_repo:
            return f"(GitHub not configured — branch '{branch}' pushed but no PR created)"

        gh = Github(self._github_token)
        repo = gh.get_repo(self._github_repo)
        default_branch = self._get_default_branch()

        pr = repo.create_pull(
            title=title,
            body=body,
            head=branch,
            base=default_branch,
            draft=draft,
        )
        return pr.html_url

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

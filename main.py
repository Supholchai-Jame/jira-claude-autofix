#!/usr/bin/env python3
"""
Claude AI Pipeline
Full loop: Jira ticket → Claude coding → test → Git PR → Jira update
"""
import argparse
import sys
from pathlib import Path

from config.settings import Settings
from pipeline.claude_agent import ClaudeAgent
from pipeline.git_operations import GitOperations
from pipeline.jira_client import JiraClient
from pipeline.validator import Validator


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Claude AI Pipeline — automated coding from Jira tickets"
    )
    parser.add_argument("ticket_id", help="Jira ticket ID, e.g. PROJ-123")
    parser.add_argument(
        "--files",
        nargs="+",
        metavar="FILE",
        help="Specific files to include as context for Claude",
    )
    parser.add_argument(
        "--dir",
        metavar="DIR",
        help="Directory to scan — all .py files will be included as context",
    )
    parser.add_argument(
        "--test-path",
        metavar="PATH",
        default=None,
        help="Path to pass to pytest (default: project root)",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Max Claude iterations on test failure (default: 3)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without pushing to Git or updating Jira",
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Skip running tests (useful for tasks with no test suite)",
    )
    return parser.parse_args()


def collect_files(file_paths: list[str] | None, directory: str | None) -> dict[str, str]:
    files: dict[str, str] = {}

    if file_paths:
        for fp in file_paths:
            path = Path(fp)
            if not path.exists():
                print(f"  [WARN] File not found: {fp}")
                continue
            files[str(path)] = path.read_text(encoding="utf-8")

    if directory:
        dir_path = Path(directory)
        if not dir_path.is_dir():
            print(f"  [WARN] Directory not found: {directory}")
        else:
            for py_file in sorted(dir_path.rglob("*.py")):
                skip_parts = {".git", "__pycache__", ".venv", "venv", "node_modules"}
                if skip_parts.intersection(py_file.parts):
                    continue
                files[str(py_file)] = py_file.read_text(encoding="utf-8")

    return files


def write_files(modified_files: dict[str, str]):
    for filepath, content in modified_files.items():
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def run_pipeline(args: argparse.Namespace):
    settings = Settings()
    settings.validate()

    # ── 1. Jira ────────────────────────────────────────────────────────────
    print(f"\n[1/5] Fetching Jira ticket {args.ticket_id}...")
    jira = JiraClient(settings.jira_server, settings.jira_email, settings.jira_api_token)
    ticket = jira.get_ticket(args.ticket_id)
    print(f"      {ticket['summary']}")
    print(f"      Status: {ticket['status']}  |  Type: {ticket['issue_type']}")

    # ── 2. Files ───────────────────────────────────────────────────────────
    print("\n[2/5] Loading source files...")
    files = collect_files(args.files, args.dir)
    if not files:
        print("  [ERROR] No files loaded. Use --files or --dir to specify code context.")
        sys.exit(1)
    print(f"      {len(files)} file(s) loaded")

    # ── 3. Git branch ──────────────────────────────────────────────────────
    branch_name = f"claude/{args.ticket_id.lower()}-fix"
    git_ops = GitOperations(
        settings.repo_local_path,
        settings.github_token,
        settings.github_repo,
    )
    if not args.dry_run:
        print(f"\n[3/5] Creating branch '{branch_name}'...")
        git_ops.create_branch(branch_name)
    else:
        print(f"\n[3/5] (dry-run) Would create branch '{branch_name}'")

    # ── 4. Claude + test loop ──────────────────────────────────────────────
    agent = ClaudeAgent(settings.anthropic_api_key, settings.claude_model)
    validator = Validator(settings.repo_local_path)

    modified_files: dict[str, str] = {}
    test_error: str | None = None
    tests_passed = True

    for iteration in range(1, args.max_retries + 1):
        print(f"\n[4/5] Claude coding — attempt {iteration}/{args.max_retries}...")
        modified_files = agent.fix_code(
            task_description=ticket["description"],
            files=files,
            test_error=test_error,
            iteration=iteration,
        )

        if not modified_files:
            print("      Claude reports: no changes needed.")
            break

        print(f"      {len(modified_files)} file(s) modified:")
        for fp in modified_files:
            print(f"        - {fp}")

        write_files(modified_files)

        if args.skip_tests:
            print("      (tests skipped)")
            break

        tests_passed, test_output = validator.run_tests(args.test_path)
        if tests_passed:
            print("      All tests passed.")
            break

        print(f"      Tests failed (attempt {iteration}).")
        test_error = test_output
        if iteration == args.max_retries:
            print("      Max retries reached — will create draft PR.")

    # ── 5. Git commit + PR + Jira ──────────────────────────────────────────
    if args.dry_run:
        print("\n[5/5] (dry-run) Skipping Git push and Jira update.")
        print("      Files that would be committed:")
        for fp in modified_files:
            print(f"        - {fp}")
        return

    if not modified_files:
        print("\n[5/5] No files modified — nothing to commit.")
        return

    print("\n[5/5] Committing, pushing, and creating PR...")
    commit_message = f"fix: {ticket['summary']} ({args.ticket_id})"
    git_ops.commit_and_push(list(modified_files.keys()), commit_message, branch_name)

    pr_body = (
        f"## Summary\n\n"
        f"Automated fix for [{args.ticket_id}]"
        f"({settings.jira_server}/browse/{args.ticket_id})\n\n"
        f"### Task\n{ticket['description']}\n\n"
        f"---\n*Generated by Claude AI Pipeline (`{settings.claude_model}`)*"
    )
    if not tests_passed:
        pr_body += "\n\n> **Warning:** Some tests are failing. This is a draft PR."

    pr_url = git_ops.create_pull_request(
        branch=branch_name,
        title=f"[{args.ticket_id}] {ticket['summary']}",
        body=pr_body,
        draft=not tests_passed,
    )
    print(f"      PR: {pr_url}")

    status_note = "tests passing" if tests_passed else "⚠️ tests failing — please review"
    jira.add_comment(
        args.ticket_id,
        f"Claude AI Pipeline submitted a PR ({status_note}):\n{pr_url}",
    )
    if tests_passed:
        try:
            jira.transition_issue(args.ticket_id, settings.jira_review_transition)
            print(f"      Jira ticket moved to '{settings.jira_review_transition}'")
        except ValueError as e:
            print(f"      [WARN] Could not transition ticket: {e}")

    print(f"\nDone! → {pr_url}\n")


if __name__ == "__main__":
    run_pipeline(parse_args())

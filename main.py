#!/usr/bin/env python3
"""
Claude AI Pipeline
Full loop: Jira ticket → Claude coding → Git PR → Jira update
"""
import argparse
import sys
from pathlib import Path

from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

from config.settings import Settings
from pipeline.claude_agent import ClaudeAgent
from pipeline.git_operations import GitOperations
from pipeline.jira_client import JiraClient

console = Console()
SKIP_DIRS = {
    ".git", "__pycache__", ".venv", "venv",
    "node_modules", "dist", "build", "target", ".angular", ".idea",
}


def make_progress() -> Progress:
    return Progress(
        SpinnerColumn(spinner_name="line"),
        TextColumn("[progress.description]{task.description}", markup=True),
        BarColumn(bar_width=28),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Claude AI Pipeline — automated coding from Jira tickets"
    )
    parser.add_argument("ticket_id", help="Jira ticket ID, e.g. PROJ-123")
    parser.add_argument(
        "--files", nargs="+", metavar="FILE",
        help="Specific files to include as context for Claude",
    )
    parser.add_argument(
        "--dir", metavar="DIR",
        help="Directory to scan for source files",
    )
    parser.add_argument(
        "--ext", nargs="+", metavar="EXT",
        help="File extensions to scan, e.g. --ext .ts .java (overrides SCAN_EXTENSIONS)",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--scope", metavar="SCOPE", default=None,
                        help="Conventional commit scope, e.g. dashboard")
    parser.add_argument("--prefix", metavar="PREFIX", default="feature",
                        choices=["feature", "fixbug"],
                        help="Branch prefix: feature or fixbug (default: feature)")
    return parser.parse_args()


def gather_paths(
    file_paths: list[str] | None,
    directory: str | None,
    extensions: list[str] | None = None,
) -> list[Path]:
    exts = set(extensions or [".ts", ".js", ".java", ".html", ".scss", ".css"])
    paths: list[Path] = []

    if file_paths:
        for fp in file_paths:
            p = Path(fp)
            if p.exists():
                paths.append(p)
            else:
                console.print(f"  [yellow]WARN[/yellow] File not found: {fp}")

    if directory:
        d = Path(directory)
        if d.is_dir():
            paths += [
                p for p in sorted(d.rglob("*"))
                if p.is_file() and p.suffix in exts and not SKIP_DIRS.intersection(p.parts)
            ]
        else:
            console.print(f"  [yellow]WARN[/yellow] Directory not found: {directory}")

    return paths


def write_files(modified_files: dict[str, str]):
    for filepath, content in modified_files.items():
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _step4_claude(
    agent: ClaudeAgent,
    ticket: dict,
    files: dict[str, str],
    progress: Progress,
) -> dict[str, str]:
    t4 = progress.add_task("[cyan]\\[4/5][/cyan] Claude thinking...", total=1)

    modified_files = agent.fix_code(
        task_description=ticket["description"],
        files=files,
    )

    if not modified_files:
        progress.update(t4, advance=1,
                        description="[green]\\[4/5][/green] Claude: no changes needed")
        return modified_files

    write_files(modified_files)
    progress.update(t4, advance=1,
                    description=f"[green]\\[4/5][/green] {len(modified_files)} file(s) modified")
    console.print(f"  [dim]Modified {len(modified_files)} file(s):[/dim]")
    for fp in modified_files:
        console.print(f"  [dim]  {fp}[/dim]")

    return modified_files


def _step5_publish(
    git_ops: GitOperations,
    jira: JiraClient,
    ticket: dict,
    args: argparse.Namespace,
    settings: Settings,
    modified_files: dict[str, str],
    branch_name: str,
    progress: Progress,
) -> str:
    t5 = progress.add_task("[cyan]\\[5/5][/cyan] Committing & pushing...", total=3)

    branch_ok, actual_branch = git_ops.validate_branch_matches_ticket(args.ticket_id)
    if not branch_ok:
        progress.stop()
        console.print(
            f"[red]  ERROR:[/red] Branch mismatch.\n"
            f"  Current : {actual_branch}\n"
            f"  Expected prefix: {args.prefix}/{args.ticket_id.lower()}-fix"
        )
        sys.exit(1)
    progress.advance(t5)

    scope_part = f"({args.scope})" if args.scope else ""
    commit_message = f"{args.ticket_id} fix{scope_part}: {ticket['summary']}"
    console.print(f"  [dim]Commit:[/dim] {commit_message}")
    git_ops.commit_and_push(list(modified_files.keys()), commit_message, branch_name)
    progress.update(t5, advance=1, description="[cyan]\\[5/5][/cyan] Creating pull request...")

    pr_body = (
        f"## Summary\n\n"
        f"Automated fix for [{args.ticket_id}]"
        f"({settings.jira_server}/browse/{args.ticket_id})\n\n"
        f"### Task\n{ticket['description']}\n\n"
        f"---\n*Generated by Claude AI Pipeline (`{settings.claude_model}`)*"
    )
    pr_url = git_ops.create_pull_request(
        branch=branch_name,
        title=f"[{args.ticket_id}] {ticket['summary']}",
        body=pr_body,
        draft=False,
    )
    console.print(f"  [dim]PR:[/dim] {pr_url}")
    progress.update(t5, advance=1, description="[cyan]\\[5/5][/cyan] Updating Jira...")

    jira.add_comment(args.ticket_id, f"Claude AI Pipeline submitted a PR:\n{pr_url}")
    try:
        jira.transition_issue(args.ticket_id, settings.jira_review_transition)
        console.print(f"  [dim]Jira:[/dim] Transitioned to '{settings.jira_review_transition}'")
    except ValueError as e:
        console.print(f"  [yellow]WARN:[/yellow] Could not transition ticket: {e}")

    progress.update(t5, description="[green]\\[5/5][/green] Done — PR created")
    return pr_url


def run_pipeline(args: argparse.Namespace):
    settings = Settings()
    settings.validate()

    pr_url: str = ""

    with make_progress() as progress:

        # ── 1. Jira ───────────────────────────────────────────────────────────
        t1 = progress.add_task(
            f"[cyan]\\[1/5][/cyan] Fetching {args.ticket_id}...", total=1
        )
        jira = JiraClient(settings.jira_server, settings.jira_email, settings.jira_api_token)
        ticket = jira.get_ticket(args.ticket_id)
        progress.update(
            t1, advance=1,
            description=f"[green]\\[1/5][/green] {args.ticket_id}: {ticket['summary'][:55]}",
        )
        console.print(f"  [dim]Status:[/dim] {ticket['status']}  [dim]Type:[/dim] {ticket['issue_type']}")
        if ticket["description"]:
            preview = ticket["description"][:150].replace("\n", " ")
            console.print(f"  [dim]{preview}{'...' if len(ticket['description']) > 150 else ''}[/dim]")

        # ── 2. Files ──────────────────────────────────────────────────────────
        t2 = progress.add_task("[cyan]\\[2/5][/cyan] Scanning source files...", total=None)
        effective_dir = args.dir or settings.default_dir or settings.repo_local_path or None
        extensions = args.ext or settings.extension_list
        paths = gather_paths(args.files, effective_dir, extensions)
        if not paths:
            progress.stop()
            console.print("[red]  ERROR:[/red] No files loaded. Use --files or --dir.")
            sys.exit(1)

        progress.update(t2, total=len(paths))
        files: dict[str, str] = {}
        for p in paths:
            try:
                files[str(p)] = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                pass
            progress.advance(t2)
        progress.update(t2, description=f"[green]\\[2/5][/green] {len(files)} file(s) loaded")
        total_chars = sum(len(c) for c in files.values())
        console.print(f"  [dim]Total size:[/dim] {total_chars:,} chars")
        for fp in list(files.keys())[:8]:
            console.print(f"  [dim]  {fp}[/dim]")
        if len(files) > 8:
            console.print(f"  [dim]  ... and {len(files) - 8} more[/dim]")

        # ── 3. Git branch ─────────────────────────────────────────────────────
        branch_name = f"{args.prefix}/{args.ticket_id.lower()}-fix"
        git_ops = GitOperations(
            settings.repo_local_path,
            settings.gitlab_token,
            settings.gitlab_repo,
            settings.gitlab_server,
            settings.gitlab_ssl_verify,
        )

        if not args.dry_run:
            t3 = progress.add_task(
                f"[cyan]\\[3/5][/cyan] Creating branch '{branch_name}'...", total=1
            )
            git_ops.create_branch(branch_name)
            progress.update(t3, advance=1,
                            description=f"[green]\\[3/5][/green] Branch '{branch_name}' ready")
            console.print(f"  [dim]Branch:[/dim] {git_ops.current_branch()}")
        else:
            console.print(f"  [dim](dry-run) Would create branch '{branch_name}'[/dim]")

        # ── 4. Claude ─────────────────────────────────────────────────────────
        agent = ClaudeAgent(model=settings.claude_model)
        modified_files = _step4_claude(agent, ticket, files, progress)

        # ── 5. Publish ────────────────────────────────────────────────────────
        if args.dry_run:
            console.print("\n  [dim](dry-run) Skipping Git push and Jira update.[/dim]")
            for fp in modified_files:
                console.print(f"    [dim]- {fp}[/dim]")
            return

        if not modified_files:
            console.print("\n  No files modified — nothing to commit.")
            return

        pr_url = _step5_publish(
            git_ops, jira, ticket, args, settings,
            modified_files, branch_name, progress,
        )

    console.print(f"\n[bold green]Done![/bold green] → {pr_url}\n")


if __name__ == "__main__":
    run_pipeline(parse_args())

# Claude AI Pipeline

Full loop automation for software development:
**Jira ticket → Claude coding → pytest → Git PR → Jira update**

```
Jira PROJ-123
     ↓
  Claude (claude-sonnet-4-6)
  reads code + task description
     ↓
  writes modified files
     ↓
  pytest  ──fail──→  Claude retry (max 3x)
     ↓ pass
  validate branch name
  must match: "feature/{ticket_id} {jira_summary}"
           or "fixbug/{ticket_id} {jira_summary}"
  e.g. "feature/KAN2-205 3.1 Feature: Item Master / Parts Management"
       "fixbug/KAN2-205 3.1 Bug: Login page crash"
     ↓ match
  git commit + push
  commit message: "{ticket_id} fix({scope}): {jira_summary}"
  e.g. "KAN2-205 fix(dashboard): 3.1 Feature: Item Master / Parts Management"
     ↓
  GitHub Pull Request (draft if tests fail)
     ↓
  Jira comment + transition "In Review"
```

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# edit .env with your credentials
```

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | ✅ | Anthropic API key |
| `CLAUDE_MODEL` | | Model ID (default: `claude-sonnet-4-6`) |
| `JIRA_SERVER` | ✅ | e.g. `https://yourcompany.atlassian.net` |
| `JIRA_EMAIL` | ✅ | Your Atlassian email |
| `JIRA_API_TOKEN` | ✅ | Jira API token |
| `JIRA_REVIEW_TRANSITION` | | Transition name (default: `In Review`) |
| `GITHUB_TOKEN` | | GitHub PAT for PR creation |
| `GITHUB_REPO` | | e.g. `org/repo-name` |
| `REPO_LOCAL_PATH` | | Absolute path to the repo being modified |

## Usage

```bash
# Fix code for a specific ticket, passing individual files
python main.py PROJ-123 --files src/auth.py src/models/user.py

# Or scan an entire directory
python main.py PROJ-123 --dir src/

# With commit scope → "KAN2-205 fix(dashboard): ..."
python main.py KAN2-205 --dir src/ --scope dashboard

# Dry run — see what Claude would change, without pushing
python main.py PROJ-123 --dir src/ --dry-run

# Skip tests (if project has no test suite yet)
python main.py PROJ-123 --files src/foo.py --skip-tests

# Limit Claude retry attempts
python main.py PROJ-123 --dir src/ --max-retries 2
```

> **Note:** Before committing, the pipeline validates that your current branch name matches the pattern `feature/{ticket_id} {jira_summary}` or `fixbug/{ticket_id} {jira_summary}` (e.g. `feature/KAN2-205 3.1 Feature: Item Master / Parts Management`). If it doesn't match, the pipeline will exit with an error.

## Project Structure

```
Claude-AI-pipeline/
├── pipeline/
│   ├── claude_agent.py     # Anthropic SDK with prompt caching
│   ├── jira_client.py      # Jira API wrapper
│   ├── git_operations.py   # GitPython + GitHub PR creation
│   └── validator.py        # pytest + syntax checker
├── config/
│   └── settings.py         # Environment variable loader
├── prompts/
│   └── coding_agent.txt    # System prompt for Claude
├── tests/
│   └── test_pipeline.py    # Unit tests (mocked external services)
├── main.py                 # Orchestrator
├── .env.example
└── requirements.txt
```

## How Prompt Caching Works

To minimise API cost, the pipeline uses [Anthropic prompt caching](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching):

- The **system prompt** is cached (5-minute TTL)
- The **codebase context** (all files) is cached on the first iteration and reused across retry loops
- Only the **task description** and **test errors** are sent uncached

This reduces input token cost by ~90% on retry iterations.

## Running Tests

```bash
pytest tests/ -v
```

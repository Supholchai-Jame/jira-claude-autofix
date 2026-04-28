import sys
import re
import json
import time
import threading
import urllib.request
import base64
import subprocess
import shutil
import os
from pathlib import Path

def load_env():
    env_path = Path(__file__).parent / '.env'
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, _, value = line.partition('=')
            os.environ.setdefault(key.strip(), value.strip())

load_env()

JIRA_SERVER = os.environ.get('JIRA_SERVER', '')
JIRA_DOMAIN = JIRA_SERVER.replace('https://', '').replace('http://', '')
JIRA_EMAIL  = os.environ.get('JIRA_EMAIL', '')
JIRA_TOKEN  = os.environ.get('JIRA_API_TOKEN', '')
REPO_PATH   = os.environ.get('REPO_LOCAL_PATH', '.')

BAR_WIDTH = 25


# ── Progress bar ──────────────────────────────────────────────────────────────

def print_progress(label, pct, done=False):
    filled = int(BAR_WIDTH * pct / 100)
    bar    = '█' * filled + '░' * (BAR_WIDTH - filled)
    status = '✅' if done else '⏳'
    sys.stdout.write(f'\r{status} [{bar}] {pct:3d}%  {label:<40}')
    sys.stdout.flush()
    if done:
        sys.stdout.write('\n')
        sys.stdout.flush()


class Spinner:
    """ใช้สำหรับ step ที่ใช้เวลานาน (Claude, git push)"""
    FRAMES = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']

    def __init__(self, label):
        self.label   = label
        self._stop   = threading.Event()
        self._thread = threading.Thread(target=self._spin, daemon=True)

    def _spin(self):
        i = 0
        start = time.time()
        while not self._stop.is_set():
            elapsed = time.time() - start
            # asymptotic fill 0→95% (never reaches 100 until task finishes)
            pct   = int(95 * (1 - 2 ** (-elapsed / 10)))
            filled = int(BAR_WIDTH * pct / 100)
            bar    = '█' * filled + '░' * (BAR_WIDTH - filled)
            frame  = self.FRAMES[i % len(self.FRAMES)]
            sys.stdout.write(f'\r{frame} [{bar}] {pct:3d}%  {self.label:<40}')
            sys.stdout.flush()
            time.sleep(0.08)
            i += 1

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *_):
        self._stop.set()
        self._thread.join()
        print_progress(self.label, 100, done=True)


# ── Git helpers ───────────────────────────────────────────────────────────────

def slugify(text):
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_]+', '-', text)
    text = re.sub(r'-+', '-', text)
    return text[:50].rstrip('-')


def git(args):
    return subprocess.run(
        ['git'] + args, cwd=REPO_PATH,
        check=True, capture_output=True, text=True
    )


def branch_exists_local(branch):
    result = subprocess.run(['git', 'branch', '--list', branch], cwd=REPO_PATH, capture_output=True, text=True)
    return branch in result.stdout


def branch_exists_remote(branch):
    result = subprocess.run(['git', 'ls-remote', '--heads', 'origin', branch], cwd=REPO_PATH, capture_output=True, text=True)
    return bool(result.stdout.strip())


def checkout_or_create_branch(branch):
    if branch_exists_local(branch):
        note = f'(local exists) checkout {branch}'
        git(['checkout', branch])
    elif branch_exists_remote(branch):
        note = f'(remote exists) checkout tracking {branch}'
        git(['checkout', '-b', branch, f'origin/{branch}'])
    else:
        note = f'สร้างใหม่ {branch}'
        git(['checkout', '-b', branch])
    return note


# ── Main workflow ─────────────────────────────────────────────────────────────

def run_workflow():
    if len(sys.argv) < 2:
        print('❌ กรุณาระบุเลข Ticket เช่น: python auto_fix.py TMA-1234')
        return

    ticket_id   = sys.argv[1]
    commit_type = sys.argv[2] if len(sys.argv) > 2 else 'feature'
    print(f'\n🚀 เริ่ม Workflow สำหรับ {ticket_id} [{commit_type}]\n')

    try:
        # ── Step 1: ดึง Jira ──────────────────────────────────────────────────
        with Spinner('ดึงข้อมูล Jira...'):
            auth_string = f'{JIRA_EMAIL}:{JIRA_TOKEN}'
            auth_b64    = base64.b64encode(auth_string.encode('ascii')).decode('ascii')

            url = f'https://{JIRA_DOMAIN}/rest/api/2/issue/{ticket_id}'
            req = urllib.request.Request(url)
            req.add_header('Authorization', f'Basic {auth_b64}')
            req.add_header('Accept', 'application/json')

            with urllib.request.urlopen(req) as response:
                jira_data = json.loads(response.read())

        fields      = jira_data.get('fields', {})
        summary     = fields.get('summary', ticket_id)
        description = fields.get('description', 'No description provided')
        desc_short  = next((l.strip() for l in description.splitlines() if l.strip()), summary)
        print(f'   📋 {summary}')

        # ── Step 2: เตรียม Branch ─────────────────────────────────────────────
        branch_name = f'{commit_type}/{ticket_id}-{slugify(summary)}'
        with Spinner(f'เตรียม Branch: {branch_name}'):
            note = checkout_or_create_branch(branch_name)
        print(f'   🌿 {note}')

        # ── Step 3 & 4: Claude แก้โค้ด ────────────────────────────────────────
        prompt = f'Please fix the codebase to resolve this Jira requirement: {description}. Make the necessary changes directly.'
        claude_bin = shutil.which('claude') or 'claude'
        claude_env = {k: v for k, v in os.environ.items() if k != 'ANTHROPIC_API_KEY'}
        with Spinner('Claude กำลังวิเคราะห์และแก้โค้ด...'):
            result = subprocess.run(
                [claude_bin, '--dangerously-skip-permissions', '-p', prompt],
                cwd=REPO_PATH, capture_output=True, text=True, encoding='utf-8',
                env=claude_env
            )
        if result.returncode != 0:
            raise RuntimeError(result.stderr or result.stdout or f'claude exited {result.returncode}')

        print_progress('Claude แก้โค้ดเสร็จแล้ว', 100, done=True)

        # ── Step 5: Commit & Push ─────────────────────────────────────────────
        commit_msg = f'{ticket_id} {commit_type}({summary}): {desc_short}'
        with Spinner('Commit และ Push...'):
            git(['add', '.'])
            git(['commit', '-m', commit_msg])
            git(['push', 'origin', branch_name])
        print(f'   💾 {commit_msg}')

        # ── Step 6: Comment Jira ──────────────────────────────────────────────
        claude_output = result.stdout.strip() if result.stdout.strip() else 'แก้ไขโค้ดเรียบร้อยแล้ว'
        with Spinner('ส่ง Comment กลับ Jira...'):
            comment_url  = f'https://{JIRA_DOMAIN}/rest/api/2/issue/{ticket_id}/comment'
            comment_body = claude_output
            comment_data = json.dumps({'body': comment_body}).encode('utf-8')

            comment_req = urllib.request.Request(comment_url, data=comment_data, method='POST')
            comment_req.add_header('Authorization', f'Basic {auth_b64}')
            comment_req.add_header('Content-Type', 'application/json')

            urllib.request.urlopen(comment_req).close()

        print('\n🎉 Workflow เสร็จสมบูรณ์!\n')

    except subprocess.CalledProcessError as e:
        print(f'\n\n❌ Terminal error: {e.stderr or e}')
    except Exception as e:
        print(f'\n\n❌ เกิดข้อผิดพลาด: {e}')


if __name__ == '__main__':
    run_workflow()

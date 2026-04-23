# Claude AI Auto-Fix Pipeline

ระบบอัตโนมัติที่ใช้ Claude Code แก้ไขโค้ดจาก Jira Ticket แล้ว Commit + Push ขึ้น Git พร้อม Comment กลับ Jira โดยอัตโนมัติ

---

## ภาพรวม Workflow

```
Jira Ticket  →  สร้าง Branch  →  Claude แก้โค้ด  →  Commit & Push  →  Comment Jira
```

| ขั้นตอน | รายละเอียด |
|---------|-----------|
| 1 | ดึงข้อมูล Jira Ticket (Summary + Description) |
| 2 | สร้าง/Checkout Git Branch ชื่อ `{type}/{TICKET-ID}-{summary-slug}` |
| 3–4 | Claude Code วิเคราะห์และแก้ไขโค้ดใน Repo ตาม Description |
| 5 | `git add .` → `git commit` → `git push origin {branch}` |
| 6 | POST comment กลับ Jira ว่าแก้เสร็จแล้วที่ Branch ไหน |

---

## สิ่งที่ต้องมีก่อนใช้งาน

- Python 3.9+
- [Claude Code CLI](https://claude.ai/code) ติดตั้งแล้วและ Login แล้ว (`claude --version`)
- Git ติดตั้งแล้วและ Config `user.name` / `user.email` แล้ว
- มีสิทธิ์ Push ไปยัง GitLab/GitHub Repo ที่ระบุ

---

## การติดตั้ง

```bash
# Clone โปรเจคนี้
git clone <repo-url>
cd Claude-AI-pipeline

# ไม่ต้องติดตั้ง Dependencies เพิ่มเติม (ใช้แค่ stdlib)
```

---

## การตั้งค่า `.env`

สร้างไฟล์ `.env` ใน root ของโปรเจค (ดู `.env.example` เป็นแม่แบบ):

```env
# Anthropic
ANTHROPIC_API_KEY=sk-ant-api03-xxxx
CLAUDE_MODEL=claude-sonnet-4-6

# Jira
JIRA_SERVER=https://your-company.atlassian.net
JIRA_EMAIL=your-email@company.com
JIRA_API_TOKEN=your-jira-api-token
JIRA_REVIEW_TRANSITION=In Review

# GitLab (หรือ GitHub — ใช้สำหรับ push)
GITLAB_SERVER=https://your-gitlab-server
GITLAB_TOKEN=glpat-xxxx
GITLAB_REPO=group/project
GITLAB_SSL_VERIFY=true

# Path ของ Repo ที่จะให้ Claude แก้โค้ด (absolute path)
REPO_LOCAL_PATH=C:\Users\you\Documents\Git\your-repo

# นามสกุลไฟล์ที่ต้องการให้ Claude สแกน (คั่นด้วย comma)
SCAN_EXTENSIONS=.ts,.java,.html,.scss,.css,.js
```

### วิธีสร้าง Jira API Token
1. ไปที่ [https://id.atlassian.com/manage-profile/security/api-tokens](https://id.atlassian.com/manage-profile/security/api-tokens)
2. คลิก **Create API token**
3. Copy token มาใส่ `JIRA_API_TOKEN`

---

## วิธีใช้งาน

```bash
# รูปแบบพื้นฐาน
python auto_fix.py <TICKET-ID>

# ระบุประเภทของ Commit (default: feature)
python auto_fix.py <TICKET-ID> <commit-type>
```

### ตัวอย่าง

```bash
# แก้ Bug จาก Ticket TMA-1234
python auto_fix.py TMA-1234 fix

# เพิ่ม Feature จาก Ticket TMA-5678
python auto_fix.py TMA-5678 feature

# งาน Refactor
python auto_fix.py TMA-9999 refactor
```

### ผลลัพธ์ที่ได้

- Branch ใหม่ชื่อ เช่น `fix/TMA-1234-fix-login-bug`
- Commit message: `TMA-1234 fix(Fix Login Bug): fix login validation error`
- Comment ใน Jira: `✅ Claude Code fixed and pushed to branch 'fix/TMA-1234-fix-login-bug'.`

---

## โครงสร้างไฟล์

```
Claude-AI-pipeline/
├── auto_fix.py       # สคริปต์หลัก
├── .env              # Config (ไม่ commit ขึ้น Git)
├── .env.example      # ตัวอย่าง Config
└── README.md         # คู่มือนี้
```

---

## ข้อควรระวัง

| เรื่อง | รายละเอียด |
|--------|-----------|
| **ไม่ Push โดยตรงไป `main`** | สคริปต์จะสร้าง Branch แยกเสมอ ต้องเปิด MR/PR เองหลังจากนั้น |
| **Claude ใช้ `--dangerously-skip-permissions`** | หมายความว่า Claude จะแก้ไขไฟล์ได้โดยไม่ถามยืนยัน ตรวจสอบโค้ดก่อน Merge เสมอ |
| **ไฟล์ `.env` มี Secret** | ห้าม Commit `.env` ขึ้น Git เด็ดขาด |
| **REPO_LOCAL_PATH ต้องถูกต้อง** | ต้องเป็น absolute path ของ Repo จริงที่ต้องการแก้ ไม่ใช่โปรเจคนี้ |

---

## Troubleshooting

**`claude: command not found`**
```bash
# ตรวจสอบว่า Claude Code ติดตั้งแล้วหรือยัง
claude --version

# ถ้ายังไม่ติดตั้ง ดาวน์โหลดจาก
# https://claude.ai/code
```

**`❌ เกิดข้อผิดพลาด: HTTP Error 401`**
- ตรวจสอบ `JIRA_EMAIL` และ `JIRA_API_TOKEN` ใน `.env`
- ตรวจสอบว่า Token ยังไม่หมดอายุ

**`git push` ล้มเหลว**
- ตรวจสอบว่ามีสิทธิ์ Push ไปยัง Remote Repo
- ถ้าใช้ GitLab self-hosted ลอง set `GITLAB_SSL_VERIFY=false` ก่อน

**Claude ไม่แก้โค้ดอะไรเลย**
- ตรวจสอบว่า `REPO_LOCAL_PATH` ชี้ไปที่ Repo ที่ถูกต้อง
- ลองรัน Claude แบบ manual เพื่อดู error: `claude -p "test" --cwd "path/to/repo"`

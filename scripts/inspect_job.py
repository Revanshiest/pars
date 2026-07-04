"""Inspect a job by id. Usage: python inspect_job.py [job_id]"""
import sqlite3
import sys

DB = "/app/data/jobs.db"
JOB_ID = sys.argv[1] if len(sys.argv) > 1 else None

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

if JOB_ID:
    rows = conn.execute("SELECT * FROM jobs WHERE id=? OR batch_id=?", (JOB_ID, JOB_ID)).fetchall()
else:
    rows = conn.execute(
        "SELECT * FROM jobs ORDER BY created_at DESC LIMIT 5"
    ).fetchall()

for row in rows:
    d = dict(row)
    print("---", d["id"][:8], d["status"], d.get("job_type"), d.get("filename", "")[:60])
    print("   stage:", d.get("stage"), f"{d.get('progress_current')}/{d.get('progress_total')}", d.get("message", "")[:80])
    print("   updated:", d.get("updated_at"))
    logs = conn.execute(
        "SELECT id, stage, message, created_at FROM job_logs WHERE job_id=? ORDER BY id DESC LIMIT 8",
        (d["id"],),
    ).fetchall()
    for lg in reversed(logs):
        print("   ", dict(lg))

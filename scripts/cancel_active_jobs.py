"""Cancel all pending/running jobs in jobs.db."""
import sqlite3
import sys
from datetime import datetime, timezone

DB = sys.argv[1] if len(sys.argv) > 1 else "/app/data/jobs.db"
MSG = "Отменено пользователем: остановка активных задач"
now = datetime.now(timezone.utc).isoformat()

conn = sqlite3.connect(DB)
rows = conn.execute(
    "SELECT id, status, job_type, filename, files_done, files_total FROM jobs "
    "WHERE status IN ('pending', 'running')"
).fetchall()
print(f"Found {len(rows)} active job(s):")
for r in rows:
    print(" ", r)

if rows:
    conn.execute(
        "UPDATE jobs SET status='failed', error=?, message=?, updated_at=? "
        "WHERE status IN ('pending', 'running')",
        (MSG, MSG, now),
    )
    conn.commit()
    print(f"Cancelled {conn.total_changes} job(s).")
else:
    print("Nothing to cancel.")

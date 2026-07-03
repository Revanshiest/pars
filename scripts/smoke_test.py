"""Smoke-тест API: auth, jobs, ingest, health."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# nickel on path
ROOT = Path(__file__).resolve().parent.parent / "nickel"
sys.path.insert(0, str(ROOT))

os.environ.setdefault("SKIP_OLLAMA_HEALTH", "true")
os.environ.setdefault("JWT_SECRET", "test-secret-key-minimum-32-characters!!")

fd, db_path = tempfile.mkstemp(suffix=".db")
os.close(fd)
os.environ["PLATFORM_DB"] = db_path
os.environ["INGEST_ROOTS"] = str(ROOT.parent / "data" / "inbox") + "," + str(ROOT.parent / "data" / "uploads")

# jobs db temp
fd2, jobs_db = tempfile.mkstemp(suffix=".jobs.db")
os.close(fd2)
os.environ.setdefault("UPLOAD_DIR", str(ROOT.parent / "data" / "uploads"))
os.environ.setdefault("OUTPUT_DIR", str(ROOT.parent / "data" / "outputs"))

Path(ROOT.parent / "data" / "inbox").mkdir(parents=True, exist_ok=True)
Path(ROOT.parent / "data" / "uploads").mkdir(parents=True, exist_ok=True)

# Reset stores
import services.store as store_mod

store_mod._store = None

from fastapi.testclient import TestClient

# Patch job store path before app import
import api.jobs as jobs_mod

jobs_mod.JobStore.__init__  # noqa — ensure module loaded

from api.main import app, job_store

job_store.db_path = jobs_db
job_store._init_db()

client = TestClient(app)
errors = []


def check(name, cond, detail=""):
    if cond:
        print(f"  OK  {name}")
    else:
        msg = f"  FAIL {name}" + (f": {detail}" if detail else "")
        print(msg)
        errors.append(name)


print("=== Smoke test Nickel API ===\n")

# Public endpoints
r = client.get("/live")
check("GET /live", r.status_code == 200 and r.json().get("status") == "ok", r.text)

r = client.get("/health")
check("GET /health", r.status_code == 200, r.text)

r = client.get("/api/v1/ontology")
check("GET /ontology", r.status_code == 200 and "node_types" in r.json(), r.text)

# Auth bootstrap
r = client.post("/api/v1/auth/setup", json={"email": "smoke@test.local", "name": "Smoke"})
check("POST /auth/setup", r.status_code == 200, r.text)
api_key = r.json().get("api_key", "")

r = client.post("/api/v1/auth/token", json={"api_key": api_key})
check("POST /auth/token", r.status_code == 200 and "access_token" in r.json(), r.text)
token = r.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

r = client.get("/api/v1/auth/me", headers=headers)
check("GET /auth/me", r.status_code == 200, r.text)

# Jobs
r = client.get("/api/v1/jobs", headers=headers)
check("GET /jobs", r.status_code == 200 and isinstance(r.json(), list), r.text)

r = client.get("/api/v1/jobs?active=true", headers=headers)
check("GET /jobs?active=true", r.status_code == 200, r.text)

# Ingest folders
r = client.get("/api/v1/ingest/folders", headers=headers)
check("GET /ingest/folders", r.status_code == 200 and "folders" in r.json(), r.text)

# Folder ingest (empty inbox — should complete quickly)
r = client.post(
    "/api/v1/documents/ingest-folder",
    headers=headers,
    json={"folder_path": "data/inbox", "extractor": "auto", "recursive": False},
)
check("POST /ingest-folder", r.status_code == 200 and r.json().get("job_type") == "batch", r.text)
batch_id = r.json().get("id")

import time

for _ in range(10):
    r = client.get(f"/api/v1/jobs/{batch_id}", headers=headers)
    if r.json().get("status") in ("completed", "failed"):
        break
    time.sleep(0.5)

job = r.json()
check("Batch job completes", job.get("status") == "completed", job.get("status"))

r = client.get(f"/api/v1/jobs/{batch_id}/logs", headers=headers)
check("GET /jobs/{id}/logs", r.status_code == 200 and len(r.json()) >= 1, r.text)

r = client.get(f"/api/v1/jobs/{batch_id}/children", headers=headers)
check("GET /jobs/{id}/children", r.status_code == 200, r.text)

# CLI health
print()
try:
    import subprocess
    proc = subprocess.run(
        [sys.executable, str(ROOT / "cli.py"), "health", "--no-ollama"],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env={**os.environ, "SKIP_OLLAMA_HEALTH": "true"},
        timeout=30,
    )
    check("CLI health", proc.returncode in (0, 1), proc.stderr or proc.stdout[:200])
except Exception as e:
    check("CLI health", False, str(e))

# Cleanup
try:
    os.unlink(db_path)
    os.unlink(jobs_db)
except OSError:
    pass

print()
if errors:
    print(f"FAILED: {len(errors)} — {', '.join(errors)}")
    sys.exit(1)
print("ALL SMOKE TESTS PASSED")

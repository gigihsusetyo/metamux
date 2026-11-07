#!/usr/bin/env python3
"""End-to-end smoke test for MetaMux - no network, no tokens needed.

Copies the real CLI into a temp folder and proves the core contract:
  1. an approved, due 'dryrun' job is processed and lands in done/ with a result
  2. a 'draft' job is never touched
  3. a not-yet-due approved job stays queued

Run: python3 tests/smoke_test.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def write_job(folder, job):
    path = os.path.join(folder, job["id"] + ".json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(job, f)
    return path


def main():
    tmp = tempfile.mkdtemp(prefix="metamux-smoke-")
    try:
        for name in ("metamux.py", "accounts.example.json"):
            shutil.copy(os.path.join(ROOT, name), os.path.join(tmp, name))

        def mm(*args):
            return subprocess.run(
                [sys.executable, os.path.join(tmp, "metamux.py"), *args],
                capture_output=True, text=True, timeout=60)

        assert mm("init").returncode == 0, "init failed"

        now = datetime.now(timezone.utc)
        past = (now - timedelta(minutes=5)).isoformat()
        future = (now + timedelta(hours=1)).isoformat()

        jobs = [
            {"id": "smoke-due", "caption": "due and approved",
             "media": [], "targets": ["dryrun"], "publish_at": past,
             "status": "approved", "attempts": 0},
            {"id": "smoke-draft", "caption": "draft must not publish",
             "media": [], "targets": ["dryrun"], "publish_at": past,
             "status": "draft", "attempts": 0},
            {"id": "smoke-future", "caption": "approved but not due",
             "media": [], "targets": ["dryrun"], "publish_at": future,
             "status": "approved", "attempts": 0},
        ]
        for job in jobs:
            out = mm("add", write_job(tmp, job))
            assert out.returncode == 0, f"add failed: {out.stdout} {out.stderr}"

        out = mm("run")
        assert out.returncode == 0, f"run failed: {out.stdout} {out.stderr}"

        done = os.path.join(tmp, "done", "smoke-due.json")
        assert os.path.exists(done), "due approved job did not reach done/"
        with open(done, encoding="utf-8") as f:
            result = json.load(f)
        assert "dryrun" in result["result"]["post_ids"], "done job has no result"

        queue = os.listdir(os.path.join(tmp, "queue"))
        assert "smoke-draft.json" in queue, "draft job was touched!"
        assert "smoke-future.json" in queue, "future job ran too early!"
        assert "smoke-due.json" not in queue, "done job still in queue!"

        print("SMOKE TEST PASSED: approved+due published, draft untouched, "
              "future job queued.")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

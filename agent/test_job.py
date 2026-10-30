"""
Test Job Runner - seeds a test signal + fix_job into the existing DB,
then runs the pipeline against it.

Usage:
    venv/Scripts/python.exe test_job.py

It will:
1. Look for an existing repository in the DB
2. Insert a test signal (simulated GitHub issue with a stack trace)
3. Insert a queued fix_job linked to that signal
4. Run the full pipeline against it
5. Print the final job status and any generated patch
"""
import asyncio
import os
import sys
import asyncpg
from dotenv import load_dotenv

load_dotenv()

# Make sure autofix_agent is importable
sys.path.insert(0, os.path.dirname(__file__))

from autofix_agent.pipeline import run_pipeline
from autofix_agent.db import close_pool

FAKE_SIGNAL_CONTENT = """
Bug Report: TypeError when processing payment

Stack trace from production CI:

```
Traceback (most recent call last):
  File "src/payment/processor.py", line 45, in calculate_fee
    fee = amount * rate
TypeError: unsupported operand type(s) for *: 'NoneType' and 'float'
```

The `calculate_fee` function in `processor.py` fails when `rate` is None.
The fix should validate the rate before using it.
"""


async def main():
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("ERROR: DATABASE_URL not set in .env")
        sys.exit(1)

    conn = await asyncpg.connect(url)

    # -----------------------------------------------------------------------
    # 1. Find an existing repo to test with
    # -----------------------------------------------------------------------
    repos = await conn.fetch(
        "SELECT id, owner, name, default_branch FROM repositories LIMIT 3"
    )
    if not repos:
        print("ERROR: No repositories found in the database.")
        print("Please add a repository via the frontend/server first.")
        await conn.close()
        sys.exit(1)

    repo = repos[0]
    repo_id = str(repo["id"])
    print(f"\n✅ Using repository: {repo['owner']}/{repo['name']} (id={repo_id})")

    # -----------------------------------------------------------------------
    # 2. Insert a test signal
    # -----------------------------------------------------------------------
    signal_row = await conn.fetchrow(
        """
        INSERT INTO signals (repo_id, type, source_ref, raw_content, status)
        VALUES ($1, 'github_issue', 'test-issue-001', $2, 'pending')
        RETURNING id
        """,
        repo_id,
        FAKE_SIGNAL_CONTENT,
    )
    signal_id = str(signal_row["id"])
    print(f"✅ Created test signal: {signal_id}")

    # -----------------------------------------------------------------------
    # 3. Insert a queued fix_job
    # -----------------------------------------------------------------------
    job_row = await conn.fetchrow(
        """
        INSERT INTO fix_jobs (repo_id, signal_id, status, attempt_count)
        VALUES ($1, $2, 'queued', 0)
        RETURNING id
        """,
        repo_id,
        signal_id,
    )
    job_id = str(job_row["id"])
    print(f"✅ Created test fix_job: {job_id} (status=queued)")

    await conn.close()

    # -----------------------------------------------------------------------
    # 4. Run the pipeline
    # -----------------------------------------------------------------------
    print(f"\n🚀 Running pipeline for job {job_id}...\n{'=' * 60}")
    job = {
        "id": job_id,
        "repo_id": repo_id,
        "signal_id": signal_id,
        "status": "queued",
        "attempt_count": 0,
    }

    await run_pipeline(job)

    # -----------------------------------------------------------------------
    # 5. Print results
    # -----------------------------------------------------------------------
    conn2 = await asyncpg.connect(url)

    final_job = await conn2.fetchrow(
        "SELECT status, error_message, attempt_count FROM fix_jobs WHERE id = $1",
        job_id,
    )
    print(f"\n{'=' * 60}")
    print(f"📊 Final job status: {final_job['status']}")
    if final_job['error_message']:
        print(f"❌ Error: {final_job['error_message'][:200]}")

    events = await conn2.fetch(
        "SELECT stage, message, created_at FROM job_events WHERE job_id = $1 ORDER BY created_at",
        job_id,
    )
    print(f"\n📋 Job Events ({len(events)} total):")
    for e in events:
        print(f"  [{e['stage']}] {e['message'][:100]}")

    candidates = await conn2.fetch(
        "SELECT rank, score, method FROM localization_candidates WHERE job_id = $1 ORDER BY rank",
        job_id,
    )
    if candidates:
        print(f"\n🎯 Localization Candidates ({len(candidates)} found):")
        for c in candidates:
            print(f"  Rank #{c['rank']} | score={c['score']:.2f} | method={c['method']}")

    patches = await conn2.fetch(
        "SELECT id, attempt_number, validation_passed, explanation FROM patches WHERE job_id = $1",
        job_id,
    )
    if patches:
        print(f"\n🩹 Patches ({len(patches)} generated):")
        for p in patches:
            status_icon = "✅" if p['validation_passed'] else "❌"
            print(f"  {status_icon} Attempt #{p['attempt_number']} | explanation: {(p['explanation'] or '')[:80]}")

    await conn2.close()
    await close_pool()
    print("\n✅ Test job complete!")


if __name__ == "__main__":
    asyncio.run(main())

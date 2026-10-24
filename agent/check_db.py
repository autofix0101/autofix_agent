"""
Quick DB inspection helper - shows what's in the database.
"""
import asyncio
import os
import asyncpg
from dotenv import load_dotenv

load_dotenv()

async def inspect():
    conn = await asyncpg.connect(os.environ["DATABASE_URL"])

    repos = await conn.fetch(
        "SELECT id, owner, name, default_branch, last_commit_sha FROM repositories LIMIT 5"
    )
    print(f"\nREPOSITORIES ({len(repos)} rows):")
    for r in repos:
        sha = r['last_commit_sha']
        sha_short = sha[:8] if sha else "None"
        print(f"  {r['owner']}/{r['name']} | branch={r['default_branch']} | last_sha={sha_short}")

    signals = await conn.fetch("SELECT id, repo_id, type, source_ref, status FROM signals LIMIT 5")
    print(f"\nSIGNALS ({len(signals)} rows):")
    for s in signals:
        print(f"  id={s['id']} | {s['type']} | {s['source_ref']} | status={s['status']}")

    jobs = await conn.fetch("SELECT id, repo_id, signal_id, status, attempt_count FROM fix_jobs LIMIT 5")
    print(f"\nFIX_JOBS ({len(jobs)} rows):")
    for j in jobs:
        print(f"  id={j['id']} | status={j['status']} | attempts={j['attempt_count']}")

    chunk_count = await conn.fetchval("SELECT COUNT(*) FROM code_chunks")
    file_count = await conn.fetchval("SELECT COUNT(*) FROM files")
    print(f"\nFILES: {file_count} rows")
    print(f"CODE_CHUNKS: {chunk_count} rows")

    await conn.close()

if __name__ == "__main__":
    asyncio.run(inspect())

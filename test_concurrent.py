#!/usr/bin/env python3
"""
Watson — Concurrent request test
==================================
Fires N simultaneous requests to your server and polls until all complete.
Usage:
    python test_concurrent.py                     # hits localhost
    python test_concurrent.py http://34.x.x.x:8080  # hits your VM
"""

import asyncio
import sys
import time
import httpx

BASE_URL = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:8080"
CONCURRENT_REQUESTS = 6  # Change this to stress-test


async def fire_and_poll(client: httpx.AsyncClient, ticket_num: int) -> dict:
    """Sends one analyze request, then polls until complete."""

    payload = {
        "ticket_id": f"TICKET-{ticket_num:04d}",
        "group_id": f"group-{ticket_num % 3 + 1}",
        "schema_name": f"schema_{ticket_num % 2 + 1}",
    }

    # Fire
    resp = await client.post(f"{BASE_URL}/analyze", json=payload)
    resp.raise_for_status()
    data = resp.json()
    job_id = data["job_id"]
    print(f"  [{ticket_num}] ACK received — job_id={job_id[:8]}...")

    # Poll
    poll_start = time.monotonic()
    while True:
        await asyncio.sleep(1.0)
        status_resp = await client.get(f"{BASE_URL}/jobs/{job_id}")
        status_resp.raise_for_status()
        job = status_resp.json()
        status = job["status"]

        if status == "complete":
            elapsed = time.monotonic() - poll_start
            print(f"  [{ticket_num}] DONE in {elapsed:.1f}s — note_posted={job['result']['internal_note_posted']}")
            return job
        elif status == "failed":
            print(f"  [{ticket_num}] FAILED — {job['error']}")
            return job
        else:
            print(f"  [{ticket_num}] still {status}...")


async def main():
    print(f"\nWatson concurrent test → {BASE_URL}")
    print(f"Firing {CONCURRENT_REQUESTS} simultaneous requests...\n")

    # Check server is up
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            health = await client.get(f"{BASE_URL}/health")
            print(f"Health: {health.json()}\n")
        except Exception as e:
            print(f"Cannot reach {BASE_URL}: {e}")
            return

        start = time.monotonic()
        # Fire all requests at the same time
        results = await asyncio.gather(
            *[fire_and_poll(client, i + 1) for i in range(CONCURRENT_REQUESTS)]
        )
        total = time.monotonic() - start

    completed = sum(1 for r in results if r["status"] == "complete")
    failed = sum(1 for r in results if r["status"] == "failed")

    print(f"\n{'─' * 50}")
    print(f"Results: {completed} complete, {failed} failed")
    print(f"Total wall-clock time: {total:.1f}s")
    print(f"{'─' * 50}\n")


if __name__ == "__main__":
    asyncio.run(main())

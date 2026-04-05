"""
Watson — Investigation Worker
================================
Each function here is one step in the investigation pipeline.
Right now they all return stub data.

When you get access to the real tools, replace each function body:
  - collect_sync_metadata  →  query your internal sync DB / API
  - fetch_recent_syncs     →  pull sync run records
  - compare_runs           →  diff failed vs last-good logs
  - search_prior_incidents →  search Zendesk for matching past tickets
  - generate_summary       →  call Claude / GPT with the collected context
  - post_internal_note     →  Zendesk API: create internal note on ticket
"""

import asyncio
import random
import logging

logger = logging.getLogger("watson.worker")


# ── Pipeline entry point ───────────────────────────────────────────────────

async def run_investigation(ticket_id: str, group_id: str, schema_name: str) -> dict:
    """
    Runs all investigation steps in sequence.
    Returns a dict that becomes the job's `result` field.
    """
    logger.info(f"[{ticket_id}] Starting investigation (group={group_id}, schema={schema_name})")

    # Step 1 — gather what we know about the connection
    metadata = await collect_sync_metadata(ticket_id, group_id, schema_name)

    # Step 2 — find the most recent syncs (failed + last successful)
    syncs = await fetch_recent_syncs(ticket_id, metadata)

    # Step 3 — diff the two runs to spot what changed
    diff = await compare_runs(ticket_id, syncs)

    # Step 4 — look for similar past tickets
    prior_incidents = await search_prior_incidents(ticket_id, schema_name, diff)

    # Step 5 — produce the investigation summary + customer response
    summary = await generate_summary(ticket_id, metadata, diff, prior_incidents)

    # Step 6 — write both as an internal note on the ticket (stub for now)
    note_posted = await post_internal_note(ticket_id, summary)

    logger.info(f"[{ticket_id}] Investigation complete.")

    return {
        "ticket_id": ticket_id,
        "schema_name": schema_name,
        "metadata": metadata,
        "recent_syncs": syncs,
        "diff": diff,
        "prior_incidents": prior_incidents,
        "investigation_summary": summary["internal"],
        "customer_response": summary["customer"],
        "internal_note_posted": note_posted,
    }


# ── Individual steps (all stubs) ───────────────────────────────────────────

async def collect_sync_metadata(ticket_id: str, group_id: str, schema_name: str) -> dict:
    """
    TODO: Query your sync metadata API or DB for this connection.
    Should return connector type, update method, sync frequency, etc.
    """
    await _simulate_work(0.4, 0.8, step="collect_sync_metadata", ticket_id=ticket_id)
    return {
        "connector": "Amazon Aurora MySQL (stub)",
        "update_method": "Detect Changes via Fivetran Teleport Sync (stub)",
        "sync_frequency": "30 minutes (stub)",
        "group_id": group_id,
        "schema_name": schema_name,
    }


async def fetch_recent_syncs(ticket_id: str, metadata: dict) -> dict:
    """
    TODO: Fetch the latest failed sync and the last successful sync.
    Pull their log URLs from GCP / Grafana.
    """
    await _simulate_work(0.5, 1.0, step="fetch_recent_syncs", ticket_id=ticket_id)
    return {
        "latest_failed": {
            "sync_id": "stub-sync-failed-001",
            "started_at": "2025-04-04T12:30:00Z",
            "grafana_url": "https://example.grafana.net/goto/stub-failed",
            "status": "failed",
        },
        "last_successful": {
            "sync_id": "stub-sync-ok-001",
            "started_at": "2025-04-04T12:00:00Z",
            "grafana_url": "https://example.grafana.net/goto/stub-success",
            "status": "success",
        },
    }


async def compare_runs(ticket_id: str, syncs: dict) -> dict:
    """
    TODO: Download GCP logs for both sync runs and diff them.
    Look for new exceptions, schema changes, flag changes, etc.
    """
    await _simulate_work(0.8, 1.5, step="compare_runs", ticket_id=ticket_id)
    return {
        "schema_changes": [],
        "flag_changes": [],
        "new_exceptions": [
            {
                "table": "stub_schema.ProductRecommendations",
                "error": "1114-HY000: The table '/rdsdbdata/tmp/#sql...' is full (stub)",
            }
        ],
        "summary": "One new exception detected in the failed sync vs the last successful run. (stub)",
    }


async def search_prior_incidents(ticket_id: str, schema_name: str, diff: dict) -> list:
    """
    TODO: Search your Zendesk ticket history for similar errors.
    Use the exception message as the search query.
    """
    await _simulate_work(0.5, 1.0, step="search_prior_incidents", ticket_id=ticket_id)
    return [
        {
            "ticket_id": "stub-100001",
            "url": "https://yourcompany.zendesk.com/agent/tickets/100001",
            "summary": "Similar tmp table full error — resolved by increasing temptable_max_ram. (stub)",
        }
    ]


async def generate_summary(
    ticket_id: str,
    metadata: dict,
    diff: dict,
    prior_incidents: list,
) -> dict:
    """
    TODO: Call an LLM (Claude/GPT) with all the context above to produce:
      - An internal investigation summary for the support engineer
      - A customer-ready draft response

    For now returns a structured stub that mirrors what the real output will look like.
    """
    await _simulate_work(1.0, 2.0, step="generate_summary", ticket_id=ticket_id)

    connector = metadata.get("connector", "unknown connector")
    error_summary = diff.get("summary", "No diff available")
    related = "\n".join(f"  - {i['url']}: {i['summary']}" for i in prior_incidents) or "  None found"
    exceptions = "\n".join(
        f"  [{e['table']}]: {e['error']}" for e in diff.get("new_exceptions", [])
    ) or "  None"

    internal = f"""[STUB — replace with LLM output]

Connector : {connector}
Update    : {metadata.get('update_method')}
Frequency : {metadata.get('sync_frequency')}

Diff summary:
  {error_summary}

New exceptions:
{exceptions}

Related prior tickets:
{related}

Recommended action:
  Investigate temp table disk limits on the DB instance. (stub)
"""

    customer = f"""[STUB — replace with LLM output]

Hi <user>,

I've reviewed the recent sync failures for your {connector} connection.

The logs show the following errors (stub):
{exceptions}

This typically means the MySQL temp table storage has run out of space.
I'd suggest checking the temptable_max_ram parameter on your instance.

Please let me know what you find and I'm happy to help further!
"""

    return {"internal": internal.strip(), "customer": customer.strip()}


async def post_internal_note(ticket_id: str, summary: dict) -> bool:
    """
    TODO: Use the Zendesk API to create an internal note on the ticket.

    Replace this stub with:
        headers = {"Authorization": f"Bearer {ZENDESK_API_TOKEN}"}
        payload = {
            "ticket": {
                "comment": {
                    "body": summary["internal"] + "\\n\\n---\\n\\n" + summary["customer"],
                    "public": False,  # internal note
                }
            }
        }
        async with httpx.AsyncClient() as client:
            resp = await client.put(
                f"https://yourcompany.zendesk.com/api/v2/tickets/{ticket_id}.json",
                json=payload,
                headers=headers,
            )
            return resp.status_code == 200
    """
    await _simulate_work(0.3, 0.6, step="post_internal_note", ticket_id=ticket_id)
    logger.info(f"[{ticket_id}] Internal note would be posted here (stub).")
    return False  # Change to True once Zendesk API is wired in


# ── Helper ─────────────────────────────────────────────────────────────────

async def _simulate_work(min_s: float, max_s: float, step: str, ticket_id: str):
    """Fakes async I/O delay so concurrent tests behave realistically."""
    delay = random.uniform(min_s, max_s)
    logger.debug(f"[{ticket_id}] {step} — simulating {delay:.2f}s")
    await asyncio.sleep(delay)

"""A background job worker, deliberately capable of hanging.

Pulls job names off a Redis list ("jobs") and "processes" them. Every
successful iteration -- including idle polls with nothing to do -- touches
a heartbeat file; healthcheck.py (run by Docker's HEALTHCHECK) fails once
that file goes stale, which is how Docker (and this demo's MCP tools)
notice something is wrong without the process having crashed.

One job name is special: "poison" makes this worker hang forever without
touching the heartbeat again -- a stuck-process incident, the kind
`docker restart` genuinely fixes because the process itself will never
recover on its own. demo/scenario.py is what actually enqueues it; this
script has no idea the scenario exists, which is the point -- it behaves
like a real (if deliberately fragile) worker, not a scripted actor.
"""

from __future__ import annotations

import os
import sys
import time

import redis

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
HEARTBEAT_FILE = os.environ.get("HEARTBEAT_FILE", "/tmp/worker-heartbeat")
QUEUE_KEY = "jobs"
POISON_JOB = "poison"
POLL_TIMEOUT_SECONDS = 5
WORK_SECONDS = 1


def touch_heartbeat() -> None:
    with open(HEARTBEAT_FILE, "w", encoding="utf-8") as fh:
        fh.write(str(time.time()))


def main() -> None:
    print(f"worker starting, queue={QUEUE_KEY!r} redis={REDIS_URL!r}", flush=True)
    client = redis.from_url(REDIS_URL)
    touch_heartbeat()

    while True:
        item = client.blpop([QUEUE_KEY], timeout=POLL_TIMEOUT_SECONDS)
        if item is None:
            # Nothing to do, but we're still alive -- prove it.
            touch_heartbeat()
            continue

        _, raw_job = item
        job = raw_job.decode("utf-8")
        print(f"picked up job: {job!r}", flush=True)

        if job == POISON_JOB:
            print(
                "this job hangs the worker on purpose -- no more heartbeats "
                "until something restarts this process",
                flush=True,
            )
            while True:
                time.sleep(3600)

        time.sleep(WORK_SECONDS)
        touch_heartbeat()
        print(f"finished job: {job!r}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)

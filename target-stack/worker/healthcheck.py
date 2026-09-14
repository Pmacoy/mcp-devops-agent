"""Docker HEALTHCHECK for the worker: exit 0 if it's heartbeating, 1 if not.

Kept deliberately dumb (read a file, compare a timestamp) so a hang in
worker.py's actual job-processing logic can't also break the healthcheck
itself -- the whole point is that this keeps working, and keeps reporting
"unhealthy", exactly while the worker process is stuck.
"""

from __future__ import annotations

import os
import sys
import time

HEARTBEAT_FILE = os.environ.get("HEARTBEAT_FILE", "/tmp/worker-heartbeat")
STALE_AFTER_SECONDS = float(os.environ.get("HEARTBEAT_STALE_SECONDS", "12"))


def main() -> int:
    if not os.path.exists(HEARTBEAT_FILE):
        return 1
    try:
        with open(HEARTBEAT_FILE, encoding="utf-8") as fh:
            last_beat = float(fh.read().strip())
    except (OSError, ValueError):
        return 1

    age = time.time() - last_beat
    return 0 if age <= STALE_AFTER_SECONDS else 1


if __name__ == "__main__":
    sys.exit(main())

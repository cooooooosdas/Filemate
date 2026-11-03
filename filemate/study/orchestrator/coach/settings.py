"""Default-off rollout and non-increasing fixed learning coach limits."""

import os

HARD_TIMEOUT_SECONDS = 60
LEASE_SECONDS = 120
QUOTA_BUCKET = "learning-coach:v1"
MAX_REQUESTS_PER_WINDOW = 30


def enabled() -> bool:
    return (
        os.getenv("FILEMATE_ENABLE_LEARNING_ORCHESTRATOR", "0") == "1"
        and os.getenv("FILEMATE_ENABLE_LEARNING_COACH", "0") == "1"
    )

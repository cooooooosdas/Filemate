"""Default-off rollout and fixed limits for learning decisions."""

import os


def enabled() -> bool:
    return os.getenv('FILEMATE_ENABLE_LEARNING_ORCHESTRATOR', '0') == '1'

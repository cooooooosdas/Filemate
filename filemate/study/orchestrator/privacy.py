"""Invalidate restored write authority while retaining schedule and audit history."""


def normalize_restored_orchestrator(conn):
    exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='data_action_previews'").fetchone()
    if exists:
        conn.execute("DELETE FROM data_action_previews WHERE action IN ('orchestrator_confirm','orchestrator_undo')")

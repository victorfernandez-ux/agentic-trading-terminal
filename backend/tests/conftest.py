"""Test isolation: point the DB at a throwaway SQLite file, not the dev DB.

Must set the env var BEFORE app.config is imported, so settings pick it up.
"""

import os
import tempfile

_TEST_DB = os.path.join(tempfile.gettempdir(), "att_test.db")
if os.path.exists(_TEST_DB):
    os.remove(_TEST_DB)
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB}"
# Run cards (B1) write files; keep test artifacts out of .private/runs.
os.environ["RUNS_DIR"] = tempfile.mkdtemp(prefix="att_test_runs_")

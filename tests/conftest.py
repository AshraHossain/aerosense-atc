"""Shared test setup.

`core/config.py` requires GOOGLE_API_KEY at import time (it calls genai.configure).
We set a dummy key here BEFORE any core import so the deterministic test suite runs
in CI with no real credentials. None of the M0 tests call Gemini — routers, state,
and config are pure — so the dummy key is never used for a network request.
"""

import os

os.environ.setdefault("GOOGLE_API_KEY", "test-key-not-real-deterministic-suite")

"""
conftest.py - runs before every test.

Tests never call real PayPal or the real AI, and never touch your demo data:
empty keys mean simulated PayPal and offline agents, and DATA_DIR points to a
throwaway folder.
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ["PAYPAL_CLIENT_ID"] = ""
os.environ["PAYPAL_CLIENT_SECRET"] = ""
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["AI_MODE"] = "offline"
os.environ["MOCK_LATENCY_S"] = "0.05"
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="cx-tests-")

# Let tests import "backend" and "evals" from the project root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from backend.config import settings  # noqa: E402

# The efficient design, whatever your .env says, so tests always check the same thing.
ORIGINAL = {
    "ai_mode": "offline", "use_cache": True, "parallel": True,
    "skip_trial_on_rule_fail": True, "shopper_uses_ai": False, "use_case_law": True,
    "fast_model": settings.fast_model, "judge_model": settings.judge_model,
}


@pytest.fixture(autouse=True)
def fresh_settings_and_data():
    """Every test starts with the normal settings and an empty data folder."""
    for name, value in ORIGINAL.items():
        setattr(settings, name, value)
    settings.data_dir = Path(tempfile.mkdtemp(prefix="cx-test-"))
    yield

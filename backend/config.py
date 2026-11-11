"""
config.py - every setting for Countersign lives here.

Settings come from the .env file in the project root (or from real
environment variables). Other files use them like this:

    from .config import settings
    print(settings.paypal_mode)
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# The project root is one folder above this file (backend/ -> project root).
ROOT = Path(__file__).resolve().parent.parent

# Read the .env file. Values already set in the real environment win.
load_dotenv(ROOT / ".env")


def env_text(name, default=""):
    """Read a text setting, for example a key or a model name."""
    return os.getenv(name, default).strip()


def env_number(name, default):
    """Read a number setting. If it is empty or not a number, use the default."""
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return float(default)


def env_flag(name, default):
    """Read a true/false setting. 'true', '1' and 'yes' all count as true."""
    value = os.getenv(name, str(default)).strip().lower()
    return value in ("true", "1", "yes")


class Settings:
    def __init__(self):
        # ---------- PayPal (developer.paypal.com > Apps & Credentials > Sandbox) ----------
        self.paypal_client_id = env_text("PAYPAL_CLIENT_ID")
        self.paypal_client_secret = env_text("PAYPAL_CLIENT_SECRET")
        self.paypal_env = env_text("PAYPAL_ENV", "sandbox")

        # ---------- AI agents (console.anthropic.com) ----------
        self.anthropic_api_key = env_text("ANTHROPIC_API_KEY")
        # AI_MODE: auto = live if you have a key, otherwise offline
        #          offline = pattern-matching analyzers, no AI at all
        #          mock = offline answers with a fake delay, to test speed without a key
        #          live = the real model
        self.ai_mode = env_text("AI_MODE", "auto").lower()
        # A small, fast model reads fine print and does the quick check.
        # The bigger model is only used to judge gray areas.
        self.fast_model = env_text("FAST_MODEL", "claude-haiku-5-5")
        self.judge_model = env_text("JUDGE_MODEL", "claude-sonnet-5-5")
        # If one AI call takes longer than this, the offline analyzer takes over.
        self.ai_timeout_s = env_number("AI_TIMEOUT_S", 15)
        # Fake delay per call in mock mode.
        self.mock_latency_s = env_number("MOCK_LATENCY_S", 0.4)

        # ---------- Prices, in dollars per million tokens (copy from Anthropic's pricing page) ----------
        self.price_fast_in = env_number("PRICE_FAST_IN", 0)
        self.price_fast_out = env_number("PRICE_FAST_OUT", 0)
        self.price_judge_in = env_number("PRICE_JUDGE_IN", 0)
        self.price_judge_out = env_number("PRICE_JUDGE_OUT", 0)

        # ---------- Speed and cost switches (all on = the efficient design) ----------
        self.use_cache = env_flag("USE_CACHE", True)                      # remember facts read from fine print
        self.parallel = env_flag("PARALLEL", True)                        # run independent AI calls at the same time
        self.skip_trial_on_rule_fail = env_flag("SKIP_TRIAL_ON_RULE_FAIL", True)  # a failed rule decides, no trial
        self.shopper_uses_ai = env_flag("SHOPPER_USES_AI", False)         # old design: ask the AI for the cheapest offer
        self.use_case_law = env_flag("USE_CASE_LAW", True)                # remember merchants caught before

        # ---------- App ----------
        self.port = int(env_number("PORT", 3000))
        self.data_dir = Path(env_text("DATA_DIR", str(ROOT / "data")))

    # ----- Things worked out from the settings above -----

    @property
    def paypal_mode(self):
        """'sandbox' when both PayPal keys are set, otherwise 'simulated'."""
        if self.paypal_client_id and self.paypal_client_secret:
            return "sandbox"
        return "simulated"

    @property
    def paypal_base_url(self):
        if self.paypal_env == "live":
            return "https://api-m.paypal.com"
        return "https://api-m.sandbox.paypal.com"

    @property
    def llm_mode(self):
        """Which kind of AI the agents use: 'live', 'mock' or 'offline'."""
        if self.ai_mode == "auto":
            if self.anthropic_api_key:
                return "live"
            return "offline"
        return self.ai_mode

    def efficiency_flags(self):
        """The four speed/cost switches, as a dictionary (shown in the web app)."""
        return {
            "useCache": self.use_cache,
            "parallel": self.parallel,
            "skipTrialOnRuleFail": self.skip_trial_on_rule_fail,
            "shopperUsesAi": self.shopper_uses_ai,
        }


# One shared Settings object for the whole app.
settings = Settings()

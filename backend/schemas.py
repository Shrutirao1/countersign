"""
schemas.py - the shapes of data that move around Countersign.

We use pydantic models. A model checks data for us: if a field is missing
or has the wrong type, pydantic raises an error instead of letting bad data in.

1) What the browser sends to the server (Rules, MandateRequest, RunRequest)
2) What each AI agent must reply with (ShopperPick, ExtractedFacts, ArgumentList, Ruling)
"""
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------
# 1) Requests from the browser
# ---------------------------------------------------------------
class Rules(BaseModel):
    """The guardian's rules. Code checks these, never the AI."""
    budget: float = Field(gt=0, le=10_000)      # must be more than 0
    noSubscriptions: bool = True
    maxMonthly: float = Field(default=0, ge=0)
    requireFreeReturns: bool = False
    noHiddenFees: bool = True


class MandateRequest(BaseModel):
    """Create the PayPal hold for a scenario."""
    scenarioId: str
    rules: Rules


class RunRequest(BaseModel):
    """Run a whole case after the buyer approved the PayPal hold."""
    orderId: str
    scenarioId: str
    rules: Rules


# ---------------------------------------------------------------
# 2) Replies from the AI agents
# ---------------------------------------------------------------
class ShopperPick(BaseModel):
    offerId: str
    reason: str = ""


class Recurring(BaseModel):
    amount: float = Field(gt=0)
    interval: Literal["week", "month", "year"]


class HiddenFee(BaseModel):
    label: str
    amount: float = Field(gt=0)


class ExtractedFacts(BaseModel):
    """What the fine-print reader must return."""
    totalDueToday: float = Field(ge=0)
    recurring: Optional[Recurring] = None
    returnCost: Optional[float] = Field(default=None, ge=0)
    hiddenFees: list[HiddenFee] = []
    evidence: dict[str, list[str]] = {}


class Argument(BaseModel):
    """One point made by the prosecutor or the defense."""
    point: str = Field(min_length=1)
    severity: Literal["critical", "major", "minor"] = "minor"
    evidence: list[str] = []

    # If the AI invents a severity like "high", treat it as "minor" instead of failing.
    @field_validator("severity", mode="before")
    @classmethod
    def unknown_severity_is_minor(cls, value):
        if value in ("critical", "major", "minor"):
            return value
        return "minor"


class ArgumentList(BaseModel):
    arguments: list[Argument]


class Finding(BaseModel):
    point: str
    evidence: list[str] = []


class Ruling(BaseModel):
    """What the judge must return."""
    verdict: Literal["APPROVE", "REJECT"]
    reasoning: str = ""
    keyFindings: list[Finding] = []

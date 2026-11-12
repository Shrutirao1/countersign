"""The evaluation dataset and runner work (the AI's own scores come from running it with your key)."""
from collections import Counter

from evals import report as report_module
from evals import run as run_module
from evals.dataset import OFFERS, offers_in


def test_dataset_has_40_labeled_offers_split_20_20():
    assert len(OFFERS) == 40
    assert len(offers_in("dev")) == 20 and len(offers_in("test")) == 20
    assert len(set(item["id"] for item in OFFERS)) == 40
    groups = Counter(item["group"] for item in OFFERS)
    assert groups == {"clean": 10, "sub_trap": 8, "hidden_fee": 6, "returns": 5, "gray": 6, "safe_words": 5}


def test_every_label_is_complete():
    for item in OFFERS:
        expected = item["expected"]
        assert expected["verdict"] in ("APPROVE", "REJECT")
        assert expected["totalDueToday"] > 0
        if item["group"] == "sub_trap":
            assert expected["recurring"] is not None


def test_runner_scores_the_offline_baseline(tmp_path, monkeypatch):
    # Write results to a temp folder, not into the repo.
    monkeypatch.setattr(run_module, "RESULTS", tmp_path)
    monkeypatch.setattr(report_module, "RESULTS", tmp_path)
    monkeypatch.setattr(report_module, "REPORT", tmp_path / "report.md")
    result = run_module.run("offline", "dev", 1)
    summary = result["summary"]
    assert summary["offers"] == 20 and len(result["rows"]) == 20
    assert [bar["metric"] for bar in summary["bars"]][0] == "Traps approved"
    assert (tmp_path / "offline-dev.json").exists() and (tmp_path / "report.md").exists()

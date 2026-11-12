"""Receipts form a hash chain: editing any old receipt is detected."""
import json

from backend.receipts import load_receipts, receipts_dir, save_receipt, verify_chain


def test_chain_links_each_receipt_to_the_one_before():
    first = save_receipt({"outcome": "approved", "amount": 52})
    second = save_receipt({"outcome": "voided", "amount": 0})
    assert first["previousHash"] == "GENESIS"
    assert second["previousHash"] == first["hash"]
    assert verify_chain() == {"ok": True, "checked": 2, "brokenAt": None, "problem": None}


def test_editing_an_old_receipt_breaks_the_chain():
    save_receipt({"outcome": "approved", "amount": 52})
    save_receipt({"outcome": "voided", "amount": 0})
    path = sorted(receipts_dir().glob("*.json"))[0]
    receipt = json.loads(path.read_text())
    receipt["body"]["amount"] = 5        # someone changes the amount
    path.write_text(json.dumps(receipt))
    result = verify_chain()
    assert result["ok"] is False and result["brokenAt"] == "CS-0001"
    assert len(load_receipts()) == 2

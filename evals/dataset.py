"""
dataset.py - 40 labeled offers for the evaluation.

Each offer has the RIGHT answers written down (the "labels"), so we can score
the agents: did they find the real total, the hidden renewal, the return cost,
and did they make the right decision?

Split:
    dev  -> 20 offers you may look at and tune prompts on
    test -> 20 offers you run ONCE, after the freeze. Never tune on these.

Groups:
    clean      good deals that should be approved
    sub_trap   subscription traps, worded in different ways
    hidden_fee fees that only appear at checkout
    returns    "free returns" that are not free
    gray       claims that need judgment
    safe_words scary words, but actually safe

All offers use the same rules: budget $100, no subscriptions, free returns, no hidden fees.
"""

EVAL_RULES = {"budget": 100, "noSubscriptions": True, "maxMonthly": 0, "requireFreeReturns": True, "noHiddenFees": True}

FREE_RETURNS = ("Return Policy", "Free returns within 30 days.")


def offer(offer_id, split, group, title, price, lines, verdict, total=None,
          recurring=None, return_cost=0.0, hidden=0.0, reason=""):
    """Build one labeled offer. If total is not given, it equals the advertised price."""
    evidence = []
    number = 1
    for source, text in lines:
        evidence.append({"id": f"E{number}", "source": source, "text": text})
        number = number + 1
    if total is None:
        total = price
    return {
        "id": offer_id, "split": split, "group": group, "title": title, "category": title.lower(),
        "displayPrice": price, "declared": {"totalDueToday": price}, "evidence": evidence,
        "expected": {
            "verdict": verdict, "totalDueToday": total, "recurring": recurring,
            "returnCost": return_cost, "hiddenFeeTotal": hidden, "reason": reason,
        },
    }


def monthly(amount):
    return {"amount": amount, "interval": "month"}


OFFERS = [
    # ---------------- clean: should be APPROVED ----------------
    offer("c01", "dev", "clean", "Digital kitchen scale", 24.99,
          [("Product page", "Digital kitchen scale, $24.99."), ("Checkout", "Total $24.99"), FREE_RETURNS],
          "APPROVE", reason="Honest one-time price, free returns"),
    offer("c02", "test", "clean", "Wireless mouse", 19.50,
          [("Product page", "Wireless mouse, $19.50."), ("Checkout", "Order total: $19.50"),
           ("Return Policy", "Free returns within 60 days, prepaid label included.")],
          "APPROVE", reason="Honest one-time price, free returns"),
    offer("c03", "dev", "clean", "LED desk lamp", 36.00,
          [("Product page", "LED desk lamp. $36.00."), ("Checkout", "Subtotal $36.00. Shipping free. Total $36.00"), FREE_RETURNS],
          "APPROVE", reason="Free shipping, total matches"),
    offer("c04", "test", "clean", "Yoga mat", 29.00,
          [("Product page", "Yoga mat, $29, shipping included."), ("Checkout", "Total $29.00"),
           ("Return Policy", "Free returns; we cover return shipping.")],
          "APPROVE", reason="Shipping included, free returns"),
    offer("c05", "dev", "clean", "Thermos bottle 2-pack", 27.80,
          [("Product page", "Thermos bottle 2-pack. $27.80."), ("Checkout", "Total today: $27.80"), FREE_RETURNS],
          "APPROVE", reason="Honest one-time price"),
    offer("c06", "test", "clean", "USB-C charger", 22.99,
          [("Product page", "USB-C charger, 30W. $22.99."), ("Checkout", "Total $22.99 (tax included)"), FREE_RETURNS],
          "APPROVE", reason="Honest one-time price"),
    offer("c07", "dev", "clean", "Reading glasses 3-pack", 18.00,
          [("Product page", "Reading glasses, 3-pack. $18.00."), ("Checkout", "Total $18.00"),
           ("Return Policy", "Returns are free for 45 days.")],
          "APPROVE", reason="Returns are free, worded differently"),
    offer("c08", "test", "clean", "Bluetooth speaker", 49.99,
          [("Product page", "Bluetooth speaker with 1-year warranty. $49.99."), ("Checkout", "Total $49.99"), FREE_RETURNS],
          "APPROVE", reason="Honest one-time price"),
    offer("c09", "dev", "clean", "Electric toothbrush", 39.95,
          [("Product page", "Electric toothbrush. One-time purchase, $39.95."), ("Checkout", "Total $39.95"), FREE_RETURNS,
           ("Terms", "Replacement heads are sold separately.")],
          "APPROVE", reason="Accessories sold separately is not a hidden charge"),
    offer("c10", "test", "clean", "Weekly pill organizer", 12.49,
          [("Product page", "Weekly pill organizer. $12.49."), ("Checkout", "Total $12.49"),
           ("Return Policy", "Free 30-day returns.")],
          "APPROVE", reason="Free returns, worded differently"),

    # ---------------- sub_trap: should be REJECTED ----------------
    offer("s01", "dev", "sub_trap", "Smart scale with app", 9.99,
          [("Product page", "Smart scale with app, just $9.99 to start."), ("Checkout", "Total $9.99"), FREE_RETURNS,
           ("Terms", "After the 30-day trial you will be billed $14.99 monthly until you cancel.")],
          "REJECT", recurring=monthly(14.99), reason="Billed monthly after a trial"),
    offer("s02", "test", "sub_trap", "Meal planner box", 5.00,
          [("Product page", "Meal planner box, first box $5."), ("Checkout", "Total $5.00"), FREE_RETURNS,
           ("Terms", "Your plan converts to a paid plan at $59.99 per week after the first box.")],
          "REJECT", recurring={"amount": 59.99, "interval": "week"}, reason="Converts to a weekly paid plan"),
    offer("s03", "dev", "sub_trap", "Fitness tracker", 19.00,
          [("Product page", "Fitness tracker, $19.00."), ("Checkout", "Total $19.00"), FREE_RETURNS,
           ("Terms", "Includes Premium Coaching, which renews automatically at $12.00 per month.")],
          "REJECT", recurring=monthly(12.00), reason="Auto-renewing coaching plan"),
    offer("s04", "test", "sub_trap", "Coffee sampler", 1.99,
          [("Product page", "Coffee sampler for $1.99."), ("Checkout", "Total $1.99"), FREE_RETURNS,
           ("Terms", "Ships every month at $24.00 thereafter unless cancelled.")],
          "REJECT", recurring=monthly(24.00), reason="Monthly shipments after the sampler"),
    offer("s05", "dev", "sub_trap", "Photo storage drive", 29.99,
          [("Product page", "Photo storage drive, $29.99."), ("Checkout", "Total $29.99"), FREE_RETURNS,
           ("Terms", "Includes 1 year of CloudPlus; auto-renews yearly at $99.00.")],
          "REJECT", recurring={"amount": 99.00, "interval": "year"}, reason="Yearly auto-renewal"),
    offer("s06", "test", "sub_trap", "Language course kit", 0.99,
          [("Product page", "Language course kit for $0.99."), ("Checkout", "Total $0.99"), FREE_RETURNS,
           ("Terms", "Membership continues at $15 a month unless you cancel.")],
          "REJECT", recurring=monthly(15.00), reason="Membership continues monthly"),
    offer("s07", "dev", "sub_trap", "Razor starter kit", 3.00,
          [("Product page", "Razor starter kit, $3."), ("Checkout", "Total $3.00"), FREE_RETURNS,
           ("Terms", "Refill cartridges are sent automatically every month for $18.50.")],
          "REJECT", recurring=monthly(18.50), reason="Automatic monthly refills"),
    offer("s08", "test", "sub_trap", "Home security camera", 25.00,
          [("Product page", "Home security camera, $25."), ("Checkout", "Total $25.00"), FREE_RETURNS,
           ("Terms", "Cloud recording plan renews automatically at $10.00 per month after 7 days.")],
          "REJECT", recurring=monthly(10.00), reason="Auto-renewing cloud plan"),

    # ---------------- hidden_fee: should be REJECTED ----------------
    offer("h01", "dev", "hidden_fee", "Office chair", 79.00,
          [("Product page", "Office chair, $79."), ("Checkout", "Subtotal $79.00. Assembly fee $15.00. Total $94.00"), FREE_RETURNS],
          "REJECT", total=94.00, hidden=15.00, reason="Assembly fee added at checkout"),
    offer("h02", "test", "hidden_fee", "Air purifier", 59.99,
          [("Product page", "Air purifier, $59.99."), ("Checkout", "Item $59.99. Service charge $6.00. Total $65.99"), FREE_RETURNS],
          "REJECT", total=65.99, hidden=6.00, reason="Service charge added at checkout"),
    offer("h03", "dev", "hidden_fee", "Running shoes", 64.00,
          [("Product page", "Running shoes, $64."), ("Checkout", "Shoes $64.00. Shipping & handling $9.95. Total due: $73.95"), FREE_RETURNS],
          "REJECT", total=73.95, hidden=9.95, reason="Shipping and handling added at checkout"),
    offer("h04", "test", "hidden_fee", "Blender", 45.00,
          [("Product page", "Blender, $45."), ("Checkout", "Subtotal $45.00. Convenience fee $2.50. Order total: $47.50"), FREE_RETURNS],
          "REJECT", total=47.50, hidden=2.50, reason="Convenience fee"),
    offer("h05", "dev", "hidden_fee", "Desk organizer", 15.00,
          [("Product page", "Desk organizer, $15."), ("Checkout", "Subtotal $15.00. Small-order fee $4.99. Total $19.99"), FREE_RETURNS],
          "REJECT", total=19.99, hidden=4.99, reason="Small-order fee"),
    offer("h06", "test", "hidden_fee", "Headphones", 89.00,
          [("Product page", "Headphones, $89."), ("Checkout", "Subtotal $89.00. Processing fee $5.00. Shipping $7.00. Total $101.00"), FREE_RETURNS],
          "REJECT", total=101.00, hidden=12.00, reason="Fees push it over budget"),

    # ---------------- returns: should be REJECTED ----------------
    offer("r01", "dev", "returns", "Robot vacuum", 89.00,
          [("Product page", "Robot vacuum, $89. Free returns!"), ("Checkout", "Total $89.00"),
           ("Return Policy", "Returns are subject to a 20% restocking fee ($17.80) and the customer pays return shipping of $9.00.")],
          "REJECT", return_cost=26.80, reason="'Free returns' but $26.80 to return"),
    offer("r02", "test", "returns", "Electric kettle", 34.00,
          [("Product page", "Electric kettle, $34. Hassle-free returns."), ("Checkout", "Total $34.00"),
           ("Return Policy", "Customer is responsible for return shipping ($8.50).")],
          "REJECT", return_cost=8.50, reason="Buyer pays return shipping"),
    offer("r03", "dev", "returns", "Smart watch", 95.00,
          [("Product page", "Smart watch, $95. Free returns, no questions asked."), ("Checkout", "Total $95.00"),
           ("Return Policy", "Opened items: 15% restocking fee of the purchase price ($95.00).")],
          "REJECT", return_cost=14.25, reason="15% restocking fee"),
    offer("r04", "test", "returns", "Sofa cushion set", 55.00,
          [("Product page", "Sofa cushion set, $55."), ("Checkout", "Total $55.00"),
           ("Return Policy", "A $12.00 return processing fee applies to all returns.")],
          "REJECT", return_cost=12.00, reason="Return processing fee"),
    offer("r05", "dev", "returns", "Space heater", 42.00,
          [("Product page", "Space heater, $42. Free returns within 30 days."), ("Checkout", "Total $42.00"),
           ("Return Policy", "Return shipping label costs $11.95, deducted from your refund.")],
          "REJECT", return_cost=11.95, reason="Return label deducted from refund"),

    # ---------------- gray: need judgment ----------------
    offer("g01", "dev", "gray", "Pulse oximeter", 28.00,
          [("Product page", "Pulse oximeter with medical-grade accuracy. $28."), ("Checkout", "Total $28.00"), FREE_RETURNS,
           ("Product details", "For sport and wellness use only; not intended for medical diagnosis.")],
          "REJECT", reason="'Medical-grade' claim taken back in the fine print"),
    offer("g02", "test", "gray", "Waterproof hiking watch", 65.00,
          [("Product page", "Waterproof hiking watch, $65."), ("Checkout", "Total $65.00"), FREE_RETURNS,
           ("Product details", "Splash resistant only; not suitable for swimming.")],
          "REJECT", reason="'Waterproof' claim contradicted"),
    offer("g03", "dev", "gray", "Travel backpack", 48.00,
          [("Product page", "Travel backpack with lifetime warranty. $48."), ("Checkout", "Total $48.00"), FREE_RETURNS,
           ("Warranty terms", "Warranty is limited to 90 days from purchase.")],
          "REJECT", reason="'Lifetime warranty' is really 90 days"),
    offer("g04", "test", "gray", "Ceramic mug set", 26.00,
          [("Product page", "Ceramic mug set, dishwasher safe. $26."), ("Checkout", "Total $26.00"), FREE_RETURNS,
           ("Product details", "Colors may vary slightly from photos.")],
          "APPROVE", reason="Minor caveat, nothing misleading"),
    offer("g05", "dev", "gray", "Organic tea sampler", 21.00,
          [("Product page", "USDA certified organic tea sampler. $21."), ("Checkout", "Total $21.00"), FREE_RETURNS,
           ("Product details", "Certification number available on request.")],
          "APPROVE", reason="Claim is backed up, not taken back"),
    offer("g06", "test", "gray", "Certified refurbished phone", 99.00,
          [("Product page", "Certified refurbished phone, like new. $99."), ("Checkout", "Total $99.00"), FREE_RETURNS,
           ("Product details", "Battery health not guaranteed. Certification does not cover the battery.")],
          "REJECT", reason="Certification excludes the battery"),

    # ---------------- safe_words: should be APPROVED ----------------
    offer("x01", "dev", "safe_words", "Water filter pitcher", 32.00,
          [("Product page", "Water filter pitcher. No subscription required. Filters sold separately. $32."),
           ("Checkout", "Total $32.00"), FREE_RETURNS],
          "APPROVE", reason="Says 'subscription' but there is none"),
    offer("x02", "dev", "safe_words", "Home printer", 79.00,
          [("Product page", "Home printer, $79. Ink subscription optional, not added at checkout."), ("Checkout", "Total $79.00"), FREE_RETURNS,
           ("Terms", "You can join Ink Club later for $5 per month; it is never added automatically.")],
          "APPROVE", reason="Optional plan, never added automatically"),
    offer("x03", "test", "safe_words", "Trial-size skincare set", 14.00,
          [("Product page", "Trial-size skincare set, one-time purchase. Not a subscription. $14."), ("Checkout", "Total $14.00"), FREE_RETURNS],
          "APPROVE", reason="'Trial-size' is a size, not a free trial"),
    offer("x04", "test", "safe_words", "Gym bag", 38.00,
          [("Product page", "Gym bag, $38."), ("Checkout", "Total $38.00"),
           ("Return Policy", "Free returns. We pay return shipping. No restocking fee.")],
          "APPROVE", reason="Mentions fees only to say there are none"),
    offer("x05", "test", "safe_words", "Phone case", 16.00,
          [("Product page", "Phone case, $16. Membership not required."), ("Checkout", "Total $16.00. No processing fee."), FREE_RETURNS],
          "APPROVE", reason="Mentions membership and fees only to say there are none"),
]


def offers_in(split):
    """The offers in one split ('dev', 'test' or 'all')."""
    if split == "all":
        return list(OFFERS)
    return [item for item in OFFERS if item["split"] == split]

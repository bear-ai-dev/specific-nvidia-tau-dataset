"""Executable mock tools for the telecom (ClearWave Mobile) domain.

Each tool is ``f(db, args) -> dict`` where ``db`` is the seed database's
``tables`` dict (mutated in place by write tools). All conversation-specific
facts (identities, usage windows, scheduled read timestamps, reserved
transaction ids) live in the seed database; the logic here is generic
domain behavior. Deterministic: no randomness, no wall clock.
"""

IDENTITY_FACTORS = ("mobile_number", "full_name", "date_of_birth")


# ---------------------------------------------------------------- helpers

def _table(db, name):
    return db.setdefault(name, {})


def _next_scheduled(rec, key):
    """Pop the next scheduled timestamp from rec[key] (a list), reusing the
    last entry once exhausted. Falls back to the scenario time if absent."""
    schedule = rec.get(key) or []
    cursor_key = "_%s_cursor" % key
    cursor = rec.get(cursor_key, 0)
    rec[cursor_key] = cursor + 1
    if schedule:
        return schedule[min(cursor, len(schedule) - 1)]
    return None


def _require_verification(db, verification_id):
    rec = _table(db, "verifications").get(verification_id)
    if rec is None or rec.get("status") != "verified":
        raise ValueError("verification %r is not a successful identity verification" % verification_id)
    return rec


def _find_line(db, line_id):
    line = _table(db, "lines").get(line_id)
    if line is None:
        raise ValueError("unknown line %r" % line_id)
    return line


def _find_customer(db, customer_id):
    cust = _table(db, "customers").get(customer_id)
    if cust is None:
        raise ValueError("unknown customer %r" % customer_id)
    return cust


def _scenario_time(db):
    return (db.get("_context") or {}).get("scenario_time")


# ------------------------------------------------------------------ tools

def lookup_customer(db, args):
    matches = [
        rec for rec in _table(db, "customers").values()
        if rec.get("mobile_number") == args.get("mobile_number")
        and rec.get("full_name") == args.get("full_name")
        and rec.get("date_of_birth") == args.get("date_of_birth")
    ]
    if not matches:
        return {"match": "none"}
    if len(matches) > 1:
        return {"match": "multiple"}
    rec = matches[0]
    return {
        "customer_id": rec["customer_id"],
        "match": "unique",
        "required_verification_factors": list(rec.get("required_verification_factors", [])),
    }


def verify_customer_identity(db, args):
    cust = _find_customer(db, args["customer_id"])
    candidates = sorted(
        (rec for rec in _table(db, "verifications").values()
         if rec.get("customer_id") == args["customer_id"]),
        key=lambda r: r.get("verification_id", ""),
    )
    if not candidates:
        raise ValueError("no verification record provisioned for customer %r" % args["customer_id"])
    ver = candidates[0]

    matched = [f for f in IDENTITY_FACTORS if args.get(f) == cust.get(f)]
    required = cust.get("required_verification_factors", list(IDENTITY_FACTORS))
    status = "verified" if all(f in matched for f in required) else "failed"

    ver["status"] = status
    ver["matched_factors"] = matched
    return {
        "verification_id": ver["verification_id"],
        "status": status,
        "matched_factors": matched,
        "access_scope": list(ver.get("access_scope", [])),
        "verified_at": ver.get("verified_at") or _scenario_time(db),
    }


def get_customer_account(db, args):
    _require_verification(db, args["verification_id"])
    cust = _find_customer(db, args["customer_id"])
    line_ids = cust.get("line_ids", [])
    include = args["include"]

    out = {"customer_id": cust["customer_id"]}
    if "lines" in include:
        out["lines"] = [
            {
                "line_id": ln["line_id"],
                "masked_mobile_number": ln["masked_mobile_number"],
                "status": ln["status"],
                "billing_cycle_id": ln["billing_cycle_id"],
            }
            for lid in line_ids
            for ln in [_find_line(db, lid)]
        ]
    if "devices" in include:
        out["devices"] = [
            {
                "device_id": dev["device_id"],
                "model": dev["model"],
                "line_id": dev["line_id"],
                "provisioning_status": dev["provisioning_status"],
            }
            for dev in sorted(_table(db, "devices").values(), key=lambda d: d["device_id"])
            if dev.get("line_id") in line_ids
        ]
    if "plans" in include:
        out["plans"] = [
            {
                "plan_id": pl["plan_id"],
                "name": pl["name"],
                "line_id": pl["line_id"],
            }
            for pl in sorted(_table(db, "plans").values(), key=lambda p: p["plan_id"])
            if pl.get("line_id") in line_ids
        ]
    return out


def get_line_data_usage(db, args):
    _require_verification(db, args["verification_id"])
    line = _find_line(db, args["line_id"])
    window = args["window"]

    if window == "custom":
        usage = dict(line.get("usage_custom") or line.get("usage_current_billing_cycle") or {})
        usage["window_start"] = args["window_start"]
        usage["window_end"] = args["window_end"]
    else:
        # Named windows carry their carrier-recorded bounds on the usage record.
        usage = line["usage_%s" % window]

    return {
        "line_id": line["line_id"],
        "billing_cycle_id": line["billing_cycle_id"],
        "measurement_source": usage.get("measurement_source", "carrier_metering"),
        "window_start": usage["window_start"],
        "window_end": usage["window_end"],
        "used_gigabytes": usage["used_gigabytes"],
        "remaining_high_speed_gigabytes": line["remaining_high_speed_gigabytes"],
        "app_attribution_available": usage.get("app_attribution_available", False),
        "as_of": _next_scheduled(line, "usage_as_of_schedule") or _scenario_time(db),
    }


def get_customer_bills(db, args):
    _require_verification(db, args["verification_id"])
    _find_customer(db, args["customer_id"])
    bills = sorted(
        (b for b in _table(db, "bills").values()
         if b.get("customer_id") == args["customer_id"] and b.get("status") == args["status"]),
        key=lambda b: b.get("bill_id", ""),
    )
    if not bills:
        raise ValueError("no %s bill for customer %r" % (args["status"], args["customer_id"]))
    bill = bills[0]
    include = args["include"]

    out = {
        "bill_id": bill["bill_id"],
        "billing_cycle_id": bill["billing_cycle_id"],
    }
    if "cycle" in include:
        out["cycle_start"] = bill["cycle_start"]
        out["cycle_end"] = bill["cycle_end"]
        out["cycle_resets_in_days"] = bill["cycle_resets_in_days"]
    if "charges" in include or "overages" in include:
        out["overage_charge"] = bill["overage_charge"]
        out["currency"] = bill["currency"]
    if "plan_behavior" in include:
        out["after_high_speed_allowance"] = bill["after_high_speed_allowance"]
    out["as_of"] = _next_scheduled(bill, "as_of_schedule") or _scenario_time(db)
    return out


def get_data_addon_offers(db, args):
    _require_verification(db, args["verification_id"])
    line = _find_line(db, args["line_id"])
    offers = [
        {
            "offer_id": o["offer_id"],
            "eligibility_status": o["eligibility_status"],
            "data_gigabytes": o["data_gigabytes"],
            "price": o["price"],
            "currency": o["currency"],
            "billing_timing": o["billing_timing"],
            "effective_timing": o["effective_timing"],
            "expires_at": o["expires_at"],
        }
        for o in sorted(_table(db, "data_addon_offers").values(), key=lambda o: o["offer_id"])
        if o.get("line_id") == args["line_id"]
    ]
    return {
        "line_id": line["line_id"],
        "offers": offers,
        "as_of": _next_scheduled(line, "offers_as_of_schedule") or _scenario_time(db),
    }


def add_data_addon(db, args):
    line = _find_line(db, args["line_id"])
    offer = _table(db, "data_addon_offers").get(args["offer_id"])
    if offer is None or offer.get("line_id") != args["line_id"]:
        raise ValueError("offer %r is not available for line %r" % (args["offer_id"], args["line_id"]))
    if offer.get("eligibility_status") != "eligible":
        raise ValueError("offer %r is not eligible" % args["offer_id"])
    if not args.get("customer_authorized"):
        raise ValueError("customer authorization is required to activate a data add-on")

    bill_candidates = sorted(
        (b for b in _table(db, "bills").values()
         if b.get("billing_cycle_id") == line["billing_cycle_id"] and b.get("status") == "current"),
        key=lambda b: b.get("bill_id", ""),
    )
    if not bill_candidates:
        raise ValueError("no current bill for billing cycle %r" % line["billing_cycle_id"])
    bill = bill_candidates[0]

    transaction_id = line.get("next_addon_transaction_id")
    if not transaction_id:
        raise ValueError("no add-on transaction id provisioned for line %r" % line["line_id"])
    effective_at = line.get("next_addon_effective_at") or _scenario_time(db)

    # New balance is derived from stored DB values, never hardcoded.
    remaining = line["remaining_high_speed_gigabytes"] + offer["data_gigabytes"]

    txn = {
        "entity_type": "addon_transaction",
        "transaction_id": transaction_id,
        "status": "active",
        "offer_id": offer["offer_id"],
        "line_id": line["line_id"],
        "charged_price": offer["price"],
        "currency": offer["currency"],
        "bill_reference": bill["bill_id"],
        "effective_at": effective_at,
        "added_high_speed_gigabytes": offer["data_gigabytes"],
        "remaining_high_speed_gigabytes": remaining,
    }
    _table(db, "addon_transactions")[transaction_id] = txn
    line["remaining_high_speed_gigabytes"] = remaining
    line["active_addon_transaction_id"] = transaction_id

    return {
        "transaction_id": transaction_id,
        "status": "active",
        "offer_id": offer["offer_id"],
        "effective_at": effective_at,
        "bill_reference": bill["bill_id"],
        "charged_price": offer["price"],
        "currency": offer["currency"],
        "added_high_speed_gigabytes": offer["data_gigabytes"],
        "remaining_high_speed_gigabytes": remaining,
    }


def transfer_to_specialist(db, args):
    counters = _table(db, "counters").get("transfer", {})
    transfer_id = counters.get("next_transfer_id")
    if not transfer_id:
        return {"status": "failed"}
    _table(db, "transfers")[transfer_id] = {
        "entity_type": "specialist_transfer",
        "transfer_id": transfer_id,
        "reason": args["reason"],
        "summary": args["summary"],
        "status": "accepted",
    }
    return {"status": "accepted", "transfer_id": transfer_id}


TOOLS = {
    "lookup_customer": lookup_customer,
    "verify_customer_identity": verify_customer_identity,
    "get_customer_account": get_customer_account,
    "get_line_data_usage": get_line_data_usage,
    "get_customer_bills": get_customer_bills,
    "get_data_addon_offers": get_data_addon_offers,
    "add_data_addon": add_data_addon,
    "transfer_to_specialist": transfer_to_specialist,
}

"""Executable mock tools for the pharmacy domain.

Each tool has the signature  tool(db, args) -> dict  where db is the seed
database's ``tables`` dict (mutated in place by write tools) and args is the
parsed arguments object of the recorded call.  All behavior is generic domain
logic driven by DB content: claim/queue/workflow transitions are real state
machine steps, and every ID or amount that appears in an output is stored in
the DB (adjudication rules, per-reason override rules, counters), never
generated randomly.
"""

# Prescription lifecycle states considered "active" for patient-facing reads.
_ACTIVE_STATUSES = {
    "received", "claim_pending", "claim_rejected", "claim_paid",
    "awaiting_pharmacist_verification", "ready_for_pickup",
}


def _queue_view(queue, keys):
    """Project the stored queue record onto the given output keys, skipping
    fields the record does not have."""
    out = {}
    for k in keys:
        if k in queue:
            out[k] = queue[k]
    return out


def _find_destination(db, patient_id, destination_id):
    patient = db.get("patients", {}).get(patient_id)
    if not patient:
        return None
    for dest in patient.get("verified_notification_destinations", []):
        if dest.get("destination_id") == destination_id:
            return dest
    return None


def lookup_patient(db, args):
    name = args["full_name"].strip().casefold()
    dob = args["date_of_birth"]
    matches = [
        p for p in db.get("patients", {}).values()
        if p.get("full_name", "").strip().casefold() == name
        and p.get("date_of_birth") == dob
    ]
    if not matches:
        return {"patient_id": "", "match": "not_found"}
    if len(matches) > 1:
        return {"patient_id": "", "match": "multiple_matches"}
    patient = matches[0]
    return {
        "patient_id": patient["patient_id"],
        "match": "unique",
        "verified_notification_destinations": [
            {
                "destination_id": d["destination_id"],
                "channel": d["channel"],
                "masked_destination": d["masked_destination"],
                "verified": d["verified"],
            }
            for d in patient.get("verified_notification_destinations", [])
        ],
    }


def _select_prescription(db, patient_id, medication_name=None):
    candidates = [
        rx for rx in db.get("prescriptions", {}).values()
        if rx.get("patient_id") == patient_id
        and rx.get("workflow_status") in _ACTIVE_STATUSES
    ]
    if medication_name:
        needle = medication_name.strip().casefold()
        candidates = [
            rx for rx in candidates
            if needle in rx.get("medication_name", "").casefold()
            or rx.get("medication_name", "").casefold() in needle
        ]
    if not candidates:
        return None
    return max(candidates, key=lambda rx: rx.get("received_at", ""))


def get_prescription(db, args):
    rx = _select_prescription(db, args["patient_id"], args.get("medication_name"))
    if rx is None:
        raise KeyError("no active prescription found for patient")
    store = db["stores"][rx["fill_store_id"]]
    claim = rx["claim"]
    claim_out = {"status": claim["status"]}
    if claim["status"] == "rejected" and "reason" in claim:
        claim_out["reason"] = claim["reason"]
    return {
        "prescription_id": rx["prescription_id"],
        "medication_id": rx["medication_id"],
        "medication_name": rx["medication_name"],
        "received_at": rx["received_at"],
        "prescription_valid": rx["prescription_valid"],
        "workflow_status": rx["workflow_status"],
        "customer_facing_status": rx["customer_facing_status"],
        "fill_store": {
            "store_id": store["store_id"],
            "display_name": store["display_name"],
            "counter_closes_at": store["counter_closes_at"],
            "front_store_closes_later": store["front_store_closes_later"],
        },
        "claim": claim_out,
        "queue": _queue_view(rx["queue"], ("status", "position", "estimated_minutes")),
        "notification": {
            "ready_alert_destination_id": rx["notification"]["ready_alert_destination_id"],
        },
        "payment_options": list(rx["payment_options"]),
    }


def request_claim_override(db, args):
    rx = db["prescriptions"][args["prescription_id"]]
    reason = args["reason"]
    rules = rx.get("insurance", {}).get("override_rules", {})
    rule = rules.get(reason)
    if rule is None:
        counters = db["system"]["counters"]
        seq = counters["next_override_seq"]
        counters["next_override_seq"] = seq + 1
        rule = {"override_id": "override-%04d" % seq, "decision": "denied"}
    override = {
        "entity_type": "payer_claim_override",
        "override_id": rule["override_id"],
        "prescription_id": rx["prescription_id"],
        "reason": reason,
        "status": rule["decision"],
    }
    if args.get("urgency_context"):
        override["urgency_context"] = args["urgency_context"]
    db.setdefault("claim_overrides", {})[rule["override_id"]] = override
    return {"override_id": rule["override_id"], "status": rule["decision"]}


def submit_prescription_claim(db, args):
    rx = db["prescriptions"][args["prescription_id"]]
    insurance = rx.get("insurance", {})
    override = None
    if args.get("override_id"):
        override = db.get("claim_overrides", {}).get(args["override_id"])

    approved = override is not None and override.get("status") in (
        "approved", "approved_one_time")

    if approved:
        # Paid claim: real state-machine step -> claim paid, queue activates,
        # prescription moves on to pharmacist verification.
        copay = insurance["copay"]
        currency = insurance["currency"]
        rx["claim"] = {
            "status": "paid",
            "copay": copay,
            "override_id": override["override_id"],
        }
        if override.get("status") == "approved_one_time":
            override["consumed"] = True
        next_status = "awaiting_pharmacist_verification"
        rx["workflow_status"] = next_status
        store = db["stores"][rx["fill_store_id"]]
        position = store["queue_next_position"]
        store["queue_next_position"] = position + 1
        rx["queue"] = {
            "status": "active",
            "position": position,
            "estimated_minutes": store["queue_estimated_minutes"],
            "pharmacist_verification_required": True,
        }
        rx["payment_options"] = list(insurance.get("paid_payment_options", []))
        return {
            "claim_status": "paid",
            "copay": copay,
            "currency": currency,
            "next_workflow_status": next_status,
            "queue": _queue_view(rx["queue"], ("status", "position", "estimated_minutes")),
            "payment_options": list(rx["payment_options"]),
        }

    # No usable override: the payer re-adjudicates and the prior rejection
    # (or a fresh rejection reason stored on the claim) stands.
    reason = rx["claim"].get("reason", "refill_too_soon")
    rx["claim"] = {"status": "rejected", "reason": reason}
    rx["workflow_status"] = "claim_rejected"
    rx["queue"] = {"status": "blocked_by_claim"}
    return {
        "claim_status": "rejected",
        "next_workflow_status": "claim_rejected",
        "queue": _queue_view(rx["queue"], ("status", "position", "estimated_minutes")),
    }


def get_store_inventory(db, args):
    key = "%s:%s" % (args["store_id"], args["medication_id"])
    rec = db["store_inventory"].get(key)
    if rec is None:
        return {
            "store_id": args["store_id"],
            "medication_id": args["medication_id"],
            "in_stock": False,
            "reserved": False,
        }
    return {
        "store_id": rec["store_id"],
        "medication_id": rec["medication_id"],
        "in_stock": rec["in_stock"],
        "reserved": rec["reserved"],
    }


def search_pharmacy_locations(db, args):
    origin = args.get("origin_store_id")
    open_after = args.get("open_after_local_time")
    query = (args.get("query") or "").strip().casefold()
    locations = []
    for store_id in sorted(db["stores"]):
        store = db["stores"][store_id]
        if origin and store_id == origin:
            continue
        # HH:MM strings compare correctly lexicographically.
        if open_after and not store["counter_closes_at"] > open_after:
            continue
        if query and query not in store["display_name"].casefold() \
                and query not in store.get("address", "").casefold():
            continue
        item = {
            "store_id": store["store_id"],
            "display_name": store["display_name"],
            "counter_closes_at": store["counter_closes_at"],
            "timezone": store["timezone"],
        }
        for opt in ("address", "front_store_closes_at", "services"):
            if opt in store:
                item[opt] = store[opt]
        locations.append(item)
    return {"locations": locations}


def request_prescription_transfer(db, args):
    rx = db["prescriptions"][args["prescription_id"]]
    dest_id = args["destination_store_id"]
    if not args.get("patient_authorized") or dest_id not in db["stores"]:
        return {
            "status": "rejected",
            "destination_store_id": dest_id,
        }
    counters = db["system"]["counters"]
    seq = counters["next_transfer_request_seq"]
    counters["next_transfer_request_seq"] = seq + 1
    request_id = "transfer-request-%04d" % seq
    record = {
        "entity_type": "prescription_transfer_request",
        "transfer_request_id": request_id,
        "prescription_id": rx["prescription_id"],
        "source_store_id": rx["fill_store_id"],
        "destination_store_id": dest_id,
        "status": "pending_pharmacist_review",
        "original_fill_active": True,
    }
    if args.get("reason"):
        record["reason"] = args["reason"]
    db.setdefault("transfer_requests", {})[request_id] = record
    return {
        "status": record["status"],
        "source_store_id": record["source_store_id"],
        "destination_store_id": record["destination_store_id"],
        "original_fill_active": record["original_fill_active"],
    }


def update_prescription(db, args):
    rx = db["prescriptions"][args["prescription_id"]]
    updated = []
    out = {"status": "updated", "updated_fields": updated}

    if args.get("priority_reason") is not None:
        rx["priority_reason"] = args["priority_reason"]
        rx["queue"]["priority_note"] = "present"
        updated.append("priority_reason")

    notification_changed = False
    if args.get("notification_channel") is not None:
        rx["notification"]["channel"] = args["notification_channel"]
        rx["notification"]["ready_alert"] = "enabled"
        updated.append("notification_channel")
        notification_changed = True
    if args.get("notification_destination_id") is not None:
        dest = _find_destination(db, rx["patient_id"], args["notification_destination_id"])
        if dest is None:
            return {"status": "rejected", "updated_fields": []}
        rx["notification"]["destination_id"] = dest["destination_id"]
        rx["notification"]["ready_alert_destination_id"] = dest["destination_id"]
        rx["notification"]["masked_destination"] = dest["masked_destination"]
        rx["notification"]["verified"] = dest["verified"]
        rx["notification"]["ready_alert"] = "enabled"
        updated.append("notification_destination")
        notification_changed = True

    if not updated:
        return {"status": "rejected", "updated_fields": []}

    if notification_changed:
        n = rx["notification"]
        out["notification"] = {
            "ready_alert": n["ready_alert"],
            "destination_id": n["destination_id"],
            "masked_destination": n["masked_destination"],
            "verified": n["verified"],
        }
        # Notification-only updates echo just the priority-note flag; an
        # update that touched operational priority returns the fuller view.
        out["queue"] = {"priority_note": rx["queue"].get("priority_note", "absent")}
    if "priority_reason" in updated:
        queue = rx["queue"]
        view = _queue_view(queue, ("status", "estimated_minutes"))
        if "pharmacist_verification_required" in queue:
            view["pharmacist_verification_required"] = queue["pharmacist_verification_required"]
        out["queue"] = view
    return out


def transfer_to_specialist(db, args):
    counters = db["system"]["counters"]
    seq = counters["next_specialist_transfer_seq"]
    counters["next_specialist_transfer_seq"] = seq + 1
    transfer_id = "specialist-transfer-%04d" % seq
    db.setdefault("specialist_transfers", {})[transfer_id] = {
        "entity_type": "specialist_transfer",
        "transfer_id": transfer_id,
        "reason": args["reason"],
        "summary": args["summary"],
        "status": "initiated",
    }
    return {"status": "initiated", "transfer_id": transfer_id}


TOOLS = {
    "lookup_patient": lookup_patient,
    "get_prescription": get_prescription,
    "request_claim_override": request_claim_override,
    "submit_prescription_claim": submit_prescription_claim,
    "get_store_inventory": get_store_inventory,
    "search_pharmacy_locations": search_pharmacy_locations,
    "request_prescription_transfer": request_prescription_transfer,
    "update_prescription": update_prescription,
    "transfer_to_specialist": transfer_to_specialist,
}

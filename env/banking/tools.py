"""Executable mock tools for the banking domain.

Contract (see env/replay.py): every tool is `fn(db, args) -> dict` where `db`
is the conversation's seed `tables` dict. Write tools mutate `db` in place.
`db['_context']` holds {'scenario_time', 'conversation_id'}.

All tools are generic banking logic driven purely by DB content; nothing
branches on the conversation. Deterministic: no randomness, no wall clock.
Identifiers that appear in outputs (verification ids, confirmation ids,
session ids, notice ids, notification ids) are pre-provisioned records in the
seed database, never generated.

Standard tables (a seed includes only the ones its bank uses):
  customers, identity_verifications, trusted_channel_confirmations,
  knowledge_base, card_accounts, referrals, transactions,
  secure_self_service_sessions, notifications, service_state
"""
import re
from datetime import datetime, timedelta

# The banking registry types every monetary amount as USD (closed enum), so
# currency siblings are decoration added at read time, not stored per record.
CURRENCY = "USD"

# Record fields that are backend-internal and never surfaced in tool outputs.
_INTERNAL_KEYS = ("queries", "entity_type")


# ---------------------------------------------------------------- helpers

def _mask_email(email):
    local, domain = email.split("@", 1)
    return local[0] + "***@" + domain


def _customer_email(rec):
    return rec.get("notification_email") or rec.get("primary_email") or rec.get("email")


def _customers(db):
    return db.get("customers", {})


def _get_customer(db, customer_id):
    table = _customers(db)
    if customer_id in table:
        return table[customer_id]
    for key in sorted(table):
        if table[key].get("customer_id") == customer_id:
            return table[key]
    raise KeyError("unknown customer: %s" % customer_id)


def _find_card(db, customer_id, card_last4=None):
    table = db.get("card_accounts", {})
    for key in sorted(table):
        card = table[key]
        if card.get("customer_id") != customer_id:
            continue
        if card_last4 is not None and card.get("card_last4") != card_last4:
            continue
        return card
    raise KeyError("no card account for customer %s" % customer_id)


def _copy_if(src, dst, keys):
    for k in keys:
        if k in src:
            dst[k] = src[k]
    return dst


def _tokens(text):
    return set(re.findall(r"[a-z0-9$]+", text.lower()))


# ---------------------------------------------------------------- lookup

def lookup_customer(db, args):
    table = _customers(db)
    rec = None
    if args.get("account_id"):
        for key in sorted(table):
            r = table[key]
            if args["account_id"] in (r.get("account_id"), r.get("customer_id"), key):
                rec = r
                break
    elif args.get("email"):
        for key in sorted(table):
            r = table[key]
            if args["email"] in (r.get("email"), r.get("primary_email"), r.get("notification_email")):
                rec = r
                break
    elif args.get("full_name"):
        for key in sorted(table):
            r = table[key]
            if r.get("full_name") == args["full_name"]:
                if args.get("billing_zip") and r.get("billing_zip") != args["billing_zip"]:
                    continue
                if args.get("card_last4") and r.get("card_last4") != args["card_last4"]:
                    continue
                rec = r
                break
    if rec is None:
        raise KeyError("no unique customer match")

    out = {
        "customer_id": rec["customer_id"],
        "match": rec.get("lookup_match", "unique"),
    }
    # The account-number lookup path confirms the account holder's name; a
    # lookup that was keyed on the caller's own stated name/email does not
    # echo profile fields back.
    if args.get("account_id") and "full_name" in rec:
        out["full_name"] = rec["full_name"]
    if "caller_phone_match" in rec:
        out["caller_phone_match"] = rec["caller_phone_match"]
    if "required_verification_methods" in rec:
        out["required_verification_methods"] = list(rec["required_verification_methods"])
    if rec.get("trusted_channels"):
        out["trusted_channels"] = [
            _copy_if(ch, {}, ("channel_id", "type", "masked_destination"))
            for ch in rec["trusted_channels"]
        ]
    return out


# ---------------------------------------------------------------- time

def get_current_time(db, args):
    clock = db.get("service_state", {}).get("clock")
    scenario_time = db.get("_context", {}).get("scenario_time")
    if not clock or not scenario_time:
        return {"status": "unavailable"}
    t = datetime.fromisoformat(scenario_time) + timedelta(seconds=clock.get("offset_seconds", 0))
    return {
        "status": "available",
        "timestamp": t.isoformat(),
        "timezone": clock["timezone"],
    }


# ---------------------------------------------------------------- identity

def verify_customer_identity(db, args):
    rec = _get_customer(db, args["customer_id"])

    # Validate every supplied non-secret factor against the stored profile.
    for factor in ("billing_zip", "mobile_last4", "card_last4", "birth_month_day"):
        if factor in args and args[factor] != rec.get(factor):
            raise ValueError("identity factor mismatch: %s" % factor)

    # A verified customer matches every factor the profile requires;
    # caller_phone is corroborated automatically from the trusted channel.
    matched = list(rec.get("required_verification_methods", []))

    table = db.get("identity_verifications", {})
    ver = None
    for key in sorted(table):
        if table[key].get("customer_id") == args["customer_id"]:
            ver = table[key]
            if ver.get("status") != "verified":
                break
    if ver is None:
        raise KeyError("no verification record provisioned for %s" % args["customer_id"])

    ver["status"] = "verified"
    ver["matched_methods"] = matched
    out = {
        "verification_id": ver["verification_id"],
        "status": ver["status"],
        "matched_methods": list(matched),
    }
    if args.get("verified_at"):
        ver["verified_at"] = args["verified_at"]
        out["verified_at"] = args["verified_at"]
    return out


# ------------------------------------------- trusted-channel confirmation

def _require_verified(db, verification_id):
    ver = db.get("identity_verifications", {}).get(verification_id)
    if not ver or ver.get("status") != "verified":
        raise ValueError("verification %s is not verified" % verification_id)
    return ver


def start_trusted_channel_confirmation(db, args):
    _require_verified(db, args["verification_id"])
    table = db.get("trusted_channel_confirmations", {})
    rec = None
    for key in sorted(table):
        r = table[key]
        if (r.get("customer_id") == args["customer_id"]
                and r.get("purpose") == args["purpose"]
                and r.get("channel") == args["channel"]):
            rec = r
            break
    if rec is None:
        raise KeyError("no confirmation record provisioned")
    if rec.get("status") in (None, "requested"):
        rec["status"] = "sent"
    out = {
        "confirmation_id": rec["confirmation_id"],
        "status": rec["status"],
        "masked_destination": rec["masked_destination"],
    }
    if "expires_at" in rec:
        out["expires_at"] = rec["expires_at"]
    return out


def get_trusted_channel_confirmation(db, args):
    rec = db.get("trusted_channel_confirmations", {}).get(args["confirmation_id"])
    if rec is None or rec.get("customer_id") != args["customer_id"]:
        raise KeyError("unknown confirmation %s" % args["confirmation_id"])
    # The customer completes the challenge on the trusted device; the backend
    # records that completion. The spoken response is never a tool argument:
    # 'verified' comes only from the stored secure-response state.
    if rec.get("secure_response_received") and rec.get("status") in ("sent", "delivered"):
        rec["status"] = "verified"
    out = {"confirmation_id": rec["confirmation_id"], "status": rec["status"]}
    if rec["status"] == "verified" and "verified_at" in rec:
        out["verified_at"] = rec["verified_at"]
    if "expires_at" in rec:
        out["expires_at"] = rec["expires_at"]
    return out


def update_customer_email(db, args):
    rec = _get_customer(db, args["customer_id"])
    _require_verified(db, args["verification_id"])
    conf = db.get("trusted_channel_confirmations", {}).get(args["confirmation_id"])
    if not conf or conf.get("status") != "verified":
        raise ValueError("trusted-channel confirmation not verified")

    old_email = rec.get("primary_email")
    new_email = args["new_email"]
    rec["primary_email"] = new_email
    rec["notification_email"] = new_email
    rec["masked_email_destination"] = _mask_email(new_email)

    login_changed = bool(old_email) and rec.get("login_identifier") == old_email
    rec["login_identifier_changed"] = login_changed

    notices = []
    if old_email and old_email != new_email:
        notices.append("old_email")
    notices.append("new_email")
    rec["transition_security_notices"] = notices

    return {
        "status": "updated",
        "primary_email": new_email,
        "notification_email": new_email,
        "login_identifier_changed": login_changed,
        "transition_security_notices": list(notices),
    }


# ---------------------------------------------------------------- knowledge

def _decorated_products(items, fee_key, currency_key):
    out = []
    for item in items:
        c = dict(item)
        if fee_key in c:
            c[currency_key] = CURRENCY
        out.append(c)
    return out


def search_knowledge_base(db, args):
    kb = db.get("knowledge_base", {})
    query = args["query"]
    rec = None
    for rid in sorted(kb):
        if query in kb[rid].get("queries", []):
            rec = kb[rid]
            break
    if rec is None:  # best-effort deterministic retrieval for unseen phrasing
        qt = _tokens(query)
        best_score, best_rid = -1.0, None
        for rid in sorted(kb):
            for stored in kb[rid].get("queries", []):
                st = _tokens(stored)
                score = len(qt & st) / float(max(1, len(qt | st)))
                if score > best_score:
                    best_score, best_rid = score, rid
        if best_rid is None:
            raise KeyError("no knowledge record matches query")
        rec = kb[best_rid]

    out = {"record_id": rec["record_id"], "effective_at": rec["effective_at"]}
    for k, v in rec.items():
        if k in ("record_id", "effective_at") or k in _INTERNAL_KEYS or k.startswith("_"):
            continue
        if k == "matches":
            out[k] = _decorated_products(v, "annual_fee", "annual_fee_currency")
        elif k == "offers":
            out[k] = _decorated_products(v, "spend", "spend_currency")
        else:
            out[k] = v
    return out


# ---------------------------------------------------------------- card account

def get_card_account(db, args):
    card = _find_card(db, args["customer_id"], args.get("card_last4"))
    include = args.get("include") or []
    out = {"customer_id": card["customer_id"], "card_last4": card["card_last4"]}

    # Transactions the customer already confirmed under a resolved (no longer
    # open) restriction are archived out of the recent-activity view.
    archived = set()
    for r in card.get("restrictions", []):
        if r.get("status") != "open":
            archived.update(r.get("linked_transaction_ids", []))

    if "status" in include:
        out["status"] = card["status"]
        out["reported_lost"] = card["reported_lost"]
        out["payment_status"] = card["payment_status"]
    if "available_credit" in include:
        out["available_credit"] = card["available_credit"]
        out["available_credit_currency"] = CURRENCY

    if "authorizations" in include:
        items = []
        for a in card.get("authorizations", []):
            if a["transaction_id"] in archived:
                continue
            item = {"transaction_id": a["transaction_id"], "merchant": a["merchant"]}
            _copy_if(a, item, ("merchant_location",))
            item["amount"] = a["amount"]
            item["currency"] = CURRENCY
            _copy_if(a, item, ("status", "occurred_at"))
            items.append(item)
        out["authorizations"] = items

    if "declines" in include:
        # A single-section decline read is the summary view (state only); when
        # the restriction section is read alongside, declines are rendered in
        # review detail (location and reason) instead.
        detail = "restrictions" in include
        items = []
        for d in card.get("declines", []):
            if d["transaction_id"] in archived:
                continue
            item = {"transaction_id": d["transaction_id"], "merchant": d["merchant"]}
            if detail:
                _copy_if(d, item, ("merchant_location",))
            item["amount"] = d["amount"]
            item["currency"] = CURRENCY
            if detail:
                _copy_if(d, item, ("reason",))
            else:
                _copy_if(d, item, ("status",))
            items.append(item)
        out["declines"] = items

    if "restrictions" in include:
        items = []
        for r in card.get("restrictions", []):
            item = {"restriction_id": r["restriction_id"], "status": r["status"]}
            if "linked_transaction_ids" in r:
                item["linked_transaction_ids"] = list(r["linked_transaction_ids"])
            items.append(item)
        out["restrictions"] = items

    if "travel_notices" in include:
        items = []
        for n in card.get("travel_notices", []):
            item = {"notice_id": n["notice_id"]}
            _copy_if(n, item, ("destinations", "return_date", "authorization_guaranteed"))
            items.append(item)
        out["travel_notices"] = items

    return out


def resolve_card_restriction(db, args):
    card = _find_card(db, args["customer_id"], args.get("card_last4"))
    restriction = None
    for r in card.get("restrictions", []):
        if r.get("restriction_id") == args["restriction_id"]:
            restriction = r
            break
    if restriction is None:
        raise KeyError("unknown restriction %s" % args["restriction_id"])
    linked = set(restriction.get("linked_transaction_ids", []))
    if not linked.issubset(set(args["confirmed_transaction_ids"])):
        raise ValueError("all linked transactions must be confirmed")
    restriction["status"] = "removed"
    if all(r.get("status") != "open" for r in card.get("restrictions", [])):
        card["status"] = "active"
    return {"status": "removed", "card_status": card["status"]}


def create_travel_notice(db, args):
    card = _find_card(db, args["customer_id"], args.get("card_last4"))
    notice_id = card.get("next_travel_notice_id")
    if not notice_id:
        raise KeyError("no travel-notice identifier provisioned")
    notice = {
        "notice_id": notice_id,
        "status": "created",
        "destinations": list(args["destinations"]),
        "return_date": args["return_date"],
        "authorization_guaranteed": False,
    }
    card.setdefault("travel_notices", []).append(notice)
    del card["next_travel_notice_id"]
    return {
        "status": "created",
        "notice_id": notice_id,
        "authorization_guaranteed": False,
    }


# ---------------------------------------------------------------- referrals

def get_referrals(db, args):
    table = db.get("referrals", {})
    items = []
    for key in sorted(table):
        r = table[key]
        if r.get("referring_customer_id") != args["customer_id"]:
            continue
        if args.get("referral_id") and r.get("referral_id") != args["referral_id"]:
            continue
        item = {}
        _copy_if(r, item, ("referral_id", "invited_at"))
        if "invited_contact" in r:
            item["invited_contact"] = _copy_if(r["invited_contact"], {}, ("channel", "masked"))
        _copy_if(r, item, ("application_status", "qualification_status", "offer"))
        items.append(item)
    return {"referrals": items}


# ---------------------------------------------------------------- transactions

def get_credit_card_transactions(db, args):
    table = db.get("transactions", {})
    items = []
    for key in sorted(table):
        t = table[key]
        if t.get("customer_id") != args["customer_id"]:
            continue
        if args.get("card_last4") and t.get("card_last4") != args["card_last4"]:
            continue
        if "amount" in args and t.get("amount") != args["amount"]:
            continue
        if args.get("descriptor_contains") and \
                args["descriptor_contains"].lower() not in t.get("descriptor", "").lower():
            continue
        if args.get("posted_date") and t.get("posted_date") != args["posted_date"]:
            continue
        item = {"transaction_id": t["transaction_id"]}
        _copy_if(t, item, ("card_last4",))
        item["amount"] = t["amount"]
        item["currency"] = CURRENCY
        _copy_if(t, item, ("category", "preceded_by_authorization_amount"))
        items.append(item)
    return {"transactions": items}


# ------------------------------------------------------- self-service sessions

_SESSION_CREATE_OPTIONAL = (
    "submitted", "credit_pull_authorized", "save_and_continue", "visible_stages",
    "claim_id", "access_location", "display_label", "allowed_customer_actions",
)
_SESSION_GET_OPTIONAL = (
    "submitted", "resume_supported", "save_and_continue",
    "credit_pull_authorized", "claim_id", "expires_at",
)


def create_secure_self_service_session(db, args):
    table = db.get("secure_self_service_sessions", {})
    rec = None
    for key in sorted(table):
        s = table[key]
        if (s.get("customer_id") == args["customer_id"]
                and s.get("workflow") == args["workflow"]
                and s.get("resource_id") == args["resource_id"]):
            rec = s
            break
    if rec is None:
        raise KeyError("no self-service session provisioned")

    rec["status"] = "issued"
    rec["submitted"] = False

    deliveries = []
    for channel in args["delivery_channels"]:
        d = {"channel": channel, "status": "delivered"}
        if channel == "email_notification":
            d["masked_destination"] = _mask_email(
                _customer_email(_get_customer(db, args["customer_id"])))
        deliveries.append(d)
    rec["deliveries"] = deliveries

    out = {"session_id": rec["session_id"], "status": rec["status"]}
    _copy_if(rec, out, _SESSION_CREATE_OPTIONAL)
    out["deliveries"] = [dict(d) for d in deliveries]
    if "expires_at" in rec:
        out["expires_at"] = rec["expires_at"]
    return out


def get_secure_self_service_session(db, args):
    rec = db.get("secure_self_service_sessions", {}).get(args["session_id"])
    if rec is None or rec.get("customer_id") != args["customer_id"]:
        raise KeyError("unknown session %s" % args["session_id"])
    # An issued session the customer has opened (but not submitted) reads back
    # as open_not_submitted; the open action is customer state in the DB, not
    # anything a tool argument asserts.
    if rec.get("customer_opened") and not rec.get("submitted") \
            and rec.get("status") in ("issued", "open_not_submitted"):
        rec["status"] = "open_not_submitted"
    out = {"session_id": rec["session_id"], "status": rec["status"]}
    _copy_if(rec, out, _SESSION_GET_OPTIONAL)
    return out


# ---------------------------------------------------------------- notifications

def send_secure_notification(db, args):
    table = db.get("notifications", {})
    rec = None
    for key in sorted(table):
        n = table[key]
        if (n.get("customer_id") == args["customer_id"]
                and n.get("related_resource_id") == args["related_resource_id"]
                and n.get("channel") == args["channel"]
                and n.get("template") == args["template"]):
            rec = n
            break
    if rec is None:
        raise KeyError("no notification provisioned")
    rec["status"] = "sent"
    customer = _get_customer(db, args["customer_id"])
    if args["channel"] == "email":
        rec["masked_destination"] = _mask_email(_customer_email(customer))
    elif "masked_destination" not in rec:
        channels = customer.get("trusted_channels", [])
        if channels:
            rec["masked_destination"] = channels[0]["masked_destination"]
    rec["contains_working_secure_link"] = False
    out = {"notification_id": rec["notification_id"], "status": rec["status"]}
    if "masked_destination" in rec:
        out["masked_destination"] = rec["masked_destination"]
    out["contains_working_secure_link"] = False
    return out


# ---------------------------------------------------------------- transfer

def transfer_to_specialist(db, args):
    svc = db.setdefault("service_state", {}).setdefault("transfer_service", {})
    out = {"status": "transferred"}
    if "next_transfer_id" in svc:
        out["transfer_id"] = svc["next_transfer_id"]
        svc["last_transfer_id"] = svc.pop("next_transfer_id")
        svc["last_transfer_reason"] = args.get("reason")
    return out


TOOLS = {
    "lookup_customer": lookup_customer,
    "get_current_time": get_current_time,
    "verify_customer_identity": verify_customer_identity,
    "start_trusted_channel_confirmation": start_trusted_channel_confirmation,
    "get_trusted_channel_confirmation": get_trusted_channel_confirmation,
    "update_customer_email": update_customer_email,
    "search_knowledge_base": search_knowledge_base,
    "get_card_account": get_card_account,
    "resolve_card_restriction": resolve_card_restriction,
    "create_travel_notice": create_travel_notice,
    "get_referrals": get_referrals,
    "get_credit_card_transactions": get_credit_card_transactions,
    "create_secure_self_service_session": create_secure_self_service_session,
    "get_secure_self_service_session": get_secure_self_service_session,
    "send_secure_notification": send_secure_notification,
    "transfer_to_specialist": transfer_to_specialist,
}

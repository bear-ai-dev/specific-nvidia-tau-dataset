"""Executable mock tools for the retail domain (Westline customer-care desk).

Contract: every tool is `f(db, args) -> dict` where `db` is the seed database's
`tables` dict (mutated in place by write tools). Tools contain only generic
domain logic; every conversation-specific fact (ids, deadline strings, review
windows, notification outcomes) lives in the seed database.

Seed-database conventions used by these tools:

- `orders` table keyed by order reference. `get_order` resolves a requested
  reference by exact key, else by longest digit-suffix match.
- Progressive section views: an order record may carry
  `<section>__views` (a list consumed one view per read of that section; after
  exhaustion the last view repeats; a `null` view omits the section) or
  `<section>__view` (a static emission override). Otherwise the canonical
  `<section>` field is emitted. This models a source system that serves
  successively deeper read models on repeated queries.
- `pending_cases` table keyed `"delivery_trace:<order_ref>"` /
  `"refund_trace:<order_ref>"`: deterministic issuance templates holding the
  case id and every system-decided field for a trace opened on that order.
- `pending_replacements` table keyed by original order reference: the
  replacement order reference and fulfillment/notification plan.
- Notifications: an order's `notifications` list holds either notification ids
  (resolved against the `notifications` table and summarized) or inline
  notification objects (emitted verbatim).
"""
import re

TEMPLATE_INCLUDED_FIELDS = {
    'delivery_trace_confirmation': ['case_id', 'status', 'carrier_response_deadline', 'approval_link'],
    'refund_trace_confirmation': ['amount', 'masked_original_payment_reference', 'review_window', 'case_id'],
    'case_reference': ['case_id', 'status'],
}

# Field whitelists for the two case projections get_order serves.
_SAME_ORDER_CASE_FIELDS = ('case_id', 'type', 'status', 'carrier_response', 'deadline',
                           'carrier_may_contact_customer', 'replacement_created')
_CROSS_ORDER_CASE_FIELDS = ('case_id', 'order_reference', 'item', 'status', 'preferences')


def _digits(s):
    return ''.join(ch for ch in s if ch.isdigit())


def _resolve_order(db, reference):
    orders = db.setdefault('orders', {})
    if reference in orders:
        return orders[reference]
    ref_digits = _digits(reference)
    best_key, best_len = None, -1
    for key in orders:
        kd = _digits(key)
        if not ref_digits or not kd:
            continue
        if kd.endswith(ref_digits) or ref_digits.endswith(kd):
            score = min(len(kd), len(ref_digits))
            if score > best_len:
                best_key, best_len = key, score
    if best_key is None:
        raise KeyError('order %r not found' % reference)
    return orders[best_key]


def _section_view(order, section):
    views_key = section + '__views'
    if views_key in order:
        views = order[views_key]
        cursor = order.setdefault('_view_cursor', {})
        idx = cursor.get(section, 0)
        value = views[idx] if idx < len(views) else views[-1]
        cursor[section] = idx + 1
        return value
    if section + '__view' in order:
        return order[section + '__view']
    return order.get(section)


def _case_entry(case, queried_reference):
    same_order = case.get('order_reference') == queried_reference
    fields = _SAME_ORDER_CASE_FIELDS if same_order else _CROSS_ORDER_CASE_FIELDS
    entry = {}
    for f in fields:
        if f == 'deadline':
            value = case.get('deadline', case.get('carrier_response_deadline'))
            if value is not None:
                entry['deadline'] = value
        elif f in case:
            entry[f] = case[f]
    return entry


def _case_listing(db, order):
    """Cases attached to the order, then other open cases of the same customer."""
    cases = db.get('cases', {})
    case_ids = [c for c in order.get('cases', []) if c in cases]
    customer_id = order.get('customer_id')
    if customer_id:
        orders = db.get('orders', {})
        for cid, case in cases.items():
            if cid in case_ids:
                continue
            other_ref = case.get('order_reference')
            if not other_ref or other_ref == order['order_reference']:
                continue
            other = orders.get(other_ref)
            if other and other.get('customer_id') == customer_id and case.get('status') == 'open':
                case_ids.append(cid)
    return [_case_entry(cases[cid], order['order_reference']) for cid in case_ids]


def _notification_listing(db, order):
    entries = []
    table = db.get('notifications', {})
    for n in order.get('notifications', []):
        if isinstance(n, str):
            rec = table.get(n, {})
            entries.append({k: rec[k] for k in ('notification_id', 'status', 'type') if k in rec})
        else:
            entries.append(n)
    return entries


def lookup_customer(db, args):
    email = args.get('email')
    customer_id = args.get('customer_id')
    matches = []
    for key, rec in db.get('customers', {}).items():
        if customer_id and (key == customer_id or rec.get('customer_id') == customer_id):
            matches.append(rec)
        elif email and rec.get('email') == email:
            matches.append(rec)
    if not matches:
        return {'customer_id': '', 'match': 'none'}
    if len(matches) > 1:
        return {'customer_id': '', 'match': 'multiple'}
    rec = matches[0]
    out = {'customer_id': rec['customer_id'], 'match': 'unique'}
    if 'display_name' in rec:
        out['display_name'] = rec['display_name']
    recent = rec.get('recent_orders__view')
    if recent is not None:
        out['recent_orders'] = recent
    return out


def get_order(db, args):
    order = _resolve_order(db, args['order_reference'])
    include = args.get('include') or []
    out = {'order_reference': order['order_reference']}
    if 'items' in include:
        customer = order.get('customer')
        if customer is not None:
            out['customer'] = customer
        items = _section_view(order, 'items')
        if items is not None:
            out['items'] = items
    fulfillment = order.get('fulfillment') or {}
    block = {}
    if 'fulfillment' in include:
        # Summary view; the latest scan already condenses the carrier scans.
        for k in ('status', 'latest_scan'):
            if k in fulfillment:
                block[k] = fulfillment[k]
    elif 'carrier_scans' in include:
        # Carrier-evidence drill-down, served when requested on its own.
        if 'carrier_evidence' in fulfillment:
            block['carrier_evidence'] = fulfillment['carrier_evidence']
    if block:
        out['fulfillment'] = block
    if 'payments' in include:
        payments = _section_view(order, 'payments')
        if payments is not None:
            out['payments'] = payments
    if 'refunds' in include:
        refunds = _section_view(order, 'refunds')
        if refunds is not None:
            out['refunds'] = refunds
    if 'cases' in include:
        out['cases'] = _case_listing(db, order)
    if 'eligible_resolutions' in include:
        resolutions = _section_view(order, 'eligible_resolutions')
        if resolutions is not None:
            out['eligible_resolutions'] = resolutions
    if 'notifications' in include:
        out['notifications'] = _notification_listing(db, order)
    return out


def get_product(db, args):
    product = db.get('products', {})[args['product_reference']]
    out = {'product_reference': product['product_reference']}
    if 'variant' in product:
        out['variant'] = product['variant']
    if args.get('include_inventory') and 'inventory' in product:
        out['inventory'] = product['inventory']
    return out


def open_delivery_trace(db, args):
    order = _resolve_order(db, args['order_reference'])
    reference = order['order_reference']
    pending = db.setdefault('pending_cases', {}).pop('delivery_trace:' + reference)
    record = {
        'entity_type': 'delivery_trace_case',
        'order_reference': reference,
        'item_references': list(args['item_references']),
        'reason': args['reason'],
    }
    record.update(pending)
    if 'requested_resolution' in args:
        record['requested_resolution'] = args['requested_resolution']
    if 'needed_by' in args:
        record['needed_by'] = args['needed_by']
    db.setdefault('cases', {})[record['case_id']] = record
    order.setdefault('cases', []).append(record['case_id'])
    out = {}
    for k in ('case_id', 'status', 'carrier_response_deadline', 'replacement_created',
              'eligibility_triggers', 'next_action', 'approval_required',
              'approval_channel', 'notification_status'):
        if k in pending:
            out[k] = pending[k]
    return out


def open_refund_trace(db, args):
    order = _resolve_order(db, args['order_reference'])
    reference = order['order_reference']
    pending = db.setdefault('pending_cases', {}).pop('refund_trace:' + reference)
    record = {
        'entity_type': 'refund_trace_case',
        'order_reference': reference,
        'return_reference': args['return_reference'],
        'payment_reference': args['payment_reference'],
        'amount_under_review': args['amount'],
    }
    record.update(pending)
    db.setdefault('cases', {})[record['case_id']] = record
    order.setdefault('cases', []).append(record['case_id'])
    out = {}
    for k in ('case_id', 'status', 'review_window_business_days',
              'duplicate_refund_blocked', 'return_evidence_attached'):
        if k in pending:
            out[k] = pending[k]
    return out


def create_replacement_order(db, args):
    order = _resolve_order(db, args['order_reference'])
    reference = order['order_reference']
    pending = db.setdefault('pending_replacements', {}).pop(reference)
    new_reference = pending['replacement_order_reference']
    out = {
        'replacement_order_reference': new_reference,
        'status': pending.get('status', 'created'),
        'balance_due': pending.get('balance_due', 0),
    }
    if 'currency' in pending:
        out['currency'] = pending['currency']
    out['fulfillment'] = pending['fulfillment']
    out['return_disposition'] = pending['return_disposition']
    if 'notification' in pending:
        out['notification'] = pending['notification']
    record = {
        'entity_type': 'replacement_order',
        'replacement_order_reference': new_reference,
        'order_reference': new_reference,
        'original_order_reference': reference,
        'item_references': list(args['item_references']),
        'reason': args['reason'],
        'status': out['status'],
        'balance_due': out['balance_due'],
        'fulfillment': pending['fulfillment'],
        'return_disposition': pending['return_disposition'],
        'notifications': [pending['notification_record']] if 'notification_record' in pending else [],
    }
    if 'currency' in pending:
        record['currency'] = pending['currency']
    if order.get('customer_id'):
        record['customer_id'] = order['customer_id']
    if order.get('customer'):
        record['customer'] = order['customer']
    db['orders'][new_reference] = record
    order['replacement_order_reference'] = new_reference
    return out


def update_case(db, args):
    case = db.get('cases', {})[args['case_id']]
    note = args.get('note')
    has_preference = ('requested_resolution' in args) or ('preferred_pickup_location' in args)
    status = 'preference_added' if has_preference else 'note_added'
    out = {'status': status, 'visible_to_next_reviewer': True}
    if 'requested_resolution' in args:
        case['requested_resolution'] = args['requested_resolution']
    if 'preferred_pickup_location' in args:
        case['preferred_pickup_location'] = args['preferred_pickup_location']
        if 'review_instruction' in case:
            out['review_instruction'] = case['review_instruction']
        out['pickup_guaranteed'] = case.get('pickup_guaranteed', False)
    if note is not None:
        case['note'] = note
        entry = {}
        queue = case.get('note_source_ids')
        if queue:
            entry['source_call_id'] = queue.pop(0)
        entry['note'] = note
        entry['status'] = status
        entry['visible_to_next_reviewer'] = True
        case.setdefault('notes', []).append(entry)
        if status == 'note_added' and re.search(r'\bfees?\b', note, re.IGNORECASE):
            # The note asserts a fee claim; report the current approval state.
            out['fee_reimbursement_approved'] = case.get('fee_reimbursement_approved', False)
    case['visible_to_next_reviewer'] = True
    return out


def send_case_notification(db, args):
    case = db.get('cases', {})[args['case_id']]
    order = _resolve_order(db, case['order_reference'])
    masked = (order.get('customer') or {}).get('verified_email', '')
    notification_id = 'notification-' + args['case_id']
    template = args['template']
    included = list(TEMPLATE_INCLUDED_FIELDS.get(template, ['case_id', 'status']))
    send_status = case.get('notification_send_status', 'sent')
    out = {
        'notification_id': notification_id,
        'status': send_status,
        'masked_destination': masked,
        'case_id': args['case_id'],
        'included_fields': included,
    }
    db.setdefault('notifications', {})[notification_id] = {
        'entity_type': 'case_notification',
        'notification_id': notification_id,
        'case_id': args['case_id'],
        'order_reference': order['order_reference'],
        'channel': args['channel'],
        'template': template,
        'type': template,
        'masked_destination': masked,
        'status': case.get('notification_final_status', send_status),
        'included_fields': included,
    }
    case['notification_status'] = send_status
    order_notifications = order.setdefault('notifications', [])
    if notification_id not in order_notifications:
        order_notifications.append(notification_id)
    return out


def _bump(identifier):
    m = re.search(r'(\d+)$', identifier)
    if not m:
        return identifier + '-2'
    return identifier[:m.start()] + str(int(m.group(1)) + 1).zfill(len(m.group(1)))


def transfer_to_specialist(db, args):
    counters = db.setdefault('counters', {})
    transfer_id = counters.get('next_transfer_id', 'transfer-0001')
    counters['next_transfer_id'] = _bump(transfer_id)
    db.setdefault('transfers', {})[transfer_id] = {
        'entity_type': 'transfer',
        'transfer_id': transfer_id,
        'reason': args['reason'],
        'summary': args['summary'],
        'status': 'transferred',
    }
    return {'status': 'transferred', 'transfer_id': transfer_id}


TOOLS = {
    'lookup_customer': lookup_customer,
    'get_order': get_order,
    'get_product': get_product,
    'open_delivery_trace': open_delivery_trace,
    'open_refund_trace': open_refund_trace,
    'create_replacement_order': create_replacement_order,
    'update_case': update_case,
    'send_case_notification': send_case_notification,
    'transfer_to_specialist': transfer_to_specialist,
}

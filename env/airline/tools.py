"""Executable mock tools for the airline domain.

Contract: each tool is  f(db, args) -> output dict.  `db` is the seed
database's `tables` dict and is mutated in place by write tools.  All
behavior is generic domain logic driven by DB content; conversation-specific
facts (ids, prices, timestamps) live in the seed database, never in code.
Deterministic: no randomness, no wall clock.
"""


# ---------------------------------------------------------------- helpers

def _norm(s):
    return ' '.join(''.join(c if c.isalnum() else ' ' for c in s.lower()).split())


def _round2(x):
    return round(x + 0.0, 2)


def _issue(issuance, prefix, queue_key='queue'):
    """Pop the next pre-seeded id, or fall back to a counter-based id."""
    q = issuance.get(queue_key) or []
    if q:
        return q.pop(0)
    n = issuance.get('counter', 1)
    issuance['counter'] = n + 1
    return '%s-%04d' % (prefix, n)


def _flight_block(f):
    return {
        'flight_id': f['flight_id'],
        'origin': dict(f['origin']),
        'destination': dict(f['destination']),
        'departure_date': f['departure_date'],
        'departure_time': f['departure_time'],
        'arrival_time': f['arrival_time'],
        'duration_minutes': f['duration_minutes'],
        'stops': f['stops'],
    }


def _round_trip_fare(outbound, ret, fare_class):
    return _round2(outbound['fares_one_way_per_traveler'][fare_class]
                   + ret['fares_one_way_per_traveler'][fare_class])


def _device_rule(db, device_type):
    want = _norm(device_type)
    for rule in db['accessibility_rules'].values():
        if _norm(rule['device_type']) == want:
            return rule
    return None


def _traveler_id(full_name):
    parts = _norm(full_name).split()
    return 'traveler-' + '-'.join([parts[0], parts[-1]] if len(parts) > 1 else parts)


def _customer_by_email(db, email):
    for c in db['customers'].values():
        if c['email'].lower() == email.lower():
            return c
    return None


def _latest_quote(db):
    quotes = list(db['fare_quotes'].values())
    return quotes[-1] if quotes else None


# ------------------------------------------------------------------ tools

def list_supported_airports(db, args):
    want = _norm(args['destination_area'])
    area = None
    for rec in db['destination_areas'].values():
        names = [rec['destination_area']] + list(rec.get('aliases', []))
        if any(_norm(n) == want for n in names):
            area = rec
            break
    if area is None:  # best-effort fallback: first configured area
        area = sorted(db['destination_areas'].values(),
                      key=lambda r: r['destination_area'])[0]
    airports = [{'code': code, 'name': db['supported_airports'][code]['name']}
                for code in area['airport_codes']]
    return {
        'airports': airports,
        'recommended_airport_code': area['recommended_airport_code'],
        'recommendation_basis': area['recommendation_basis'],
        'retrieved_at': area['retrieved_at'],
    }


def search_flights(db, args):
    match = None
    for rec in db['flight_searches'].values():
        if rec['criteria'] == args:
            match = rec
            break
    if match is None:  # best-effort: loosest stored search on the same route/dates
        for rec in db['flight_searches'].values():
            c = rec['criteria']
            if (c['origin_airport'] == args['origin_airport']
                    and c['destination_airport'] == args['destination_airport']
                    and c['departure_date'] == args['departure_date']
                    and c['return_date'] == args['return_date']
                    and c['max_stops'] <= args['max_stops']):
                match = rec
                break
    if match is None:
        raise ValueError('no availability recorded for this search')

    out = {
        'search_id': match['search_id'],
        'availability_checked_at': match['availability_checked_at'],
        'expires_at': match['expires_at'],
    }
    if match['result_kind'] == 'direct':
        ob = db['flights'][match['outbound_flight_id']]
        rt = db['flights'][match['return_flight_id']]
        out['outbound'] = _flight_block(ob)
        out['return'] = _flight_block(rt)
        out['fare_options'] = [{
            'fare_class': fo['fare_class'],
            'price_per_traveler': _round_trip_fare(ob, rt, fo['fare_class']),
            'currency': ob['currency'],
            'relative_price_rank': fo['relative_price_rank'],
            'advance_seat_selection_allowed': fo['advance_seat_selection_allowed'],
        } for fo in ob['fare_options']]
    else:
        it = db['itineraries'][match['itinerary_id']]
        out['best_connection'] = {
            'itinerary_id': it['itinerary_id'],
            'total_savings': it['total_savings'],
            'currency': it['currency'],
            'additional_duration_each_way': it['additional_duration_each_way'],
            'additional_duration_minutes_each_way': it['additional_duration_minutes_each_way'],
        }
    return out


def check_mobility_device_requirements(db, args):
    rule = _device_rule(db, args['device_type'])
    if rule is None:
        raise ValueError('unknown mobility device type')
    return {
        'device_type': rule['device_type'],
        'counts_as_paid_bag': rule['counts_as_paid_bag'],
        'fee': rule['fee'],
        'currency': rule['currency'],
        'serial_number_required': rule['serial_number_required'],
        'labeling_guidance': rule['labeling_guidance'],
        'airport_notification_required': rule['airport_notification_required'],
        'effective_at': rule['effective_at'],
    }


def calculate_itinerary_price(db, args):
    cfg = db['system']['pricing_config']
    ob = db['flights'][args['outbound_flight_id']]
    rt = db['flights'][args['return_flight_id']]
    fare_rt = _round_trip_fare(ob, rt, args['fare_class'])
    fare_bags = _round2(args['traveler_count'] * fare_rt
                        + args['checked_bag_count'] * cfg['checked_bag_fee_round_trip'])
    mobility = _round2(args['mobility_device_count'] * cfg['mobility_device_fee'])

    issuance = db['system']['quote_issuance']
    q = issuance.get('queue') or []
    if q:
        nxt = q.pop(0)
        quote_id, expires_at = nxt['quote_id'], nxt['expires_at']
    else:
        n = issuance.get('counter', 1)
        issuance['counter'] = n + 1
        quote_id = 'quote-%04d' % n
        expires_at = db['_context']['scenario_time']

    quote = {
        'quote_id': quote_id,
        'outbound_flight_id': args['outbound_flight_id'],
        'return_flight_id': args['return_flight_id'],
        'traveler_count': args['traveler_count'],
        'fare_class': args['fare_class'],
        'checked_bag_count': args['checked_bag_count'],
        'mobility_device_count': args['mobility_device_count'],
        'fare_taxes_and_checked_bags': fare_bags,
        'mobility_device_charge': mobility,
        'currency': cfg['currency'],
        'expires_at': expires_at,
    }
    out = {
        'quote_id': quote_id,
        'fare_taxes_and_checked_bags': fare_bags,
        'mobility_device_charge': mobility,
        'currency': cfg['currency'],
        'expires_at': expires_at,
    }
    if args['include_insurance_quote']:
        insurance = _round2(args['traveler_count'] * cfg['trip_insurance_per_traveler'])
        total = _round2(fare_bags + mobility + insurance)
        quote['trip_insurance'] = insurance
        quote['insurance_plan_document'] = cfg['insurance_plan_document']
        quote['total_with_insurance'] = total
        out['trip_insurance'] = insurance
        out['insurance_plan_document'] = cfg['insurance_plan_document']
        out['total_with_insurance'] = total
    db['fare_quotes'][quote_id] = quote
    return out


def verify_customer_identity(db, args):
    best, best_matched = None, []
    for c in db['customers'].values():
        matched = []
        if _norm(c['full_name']) == _norm(args['full_name']):
            matched.append('full_name')
        if c['date_of_birth'] == args['date_of_birth']:
            matched.append('date_of_birth')
        if c['email'].lower() == args['email'].lower():
            matched.append('email')
        if len(matched) > len(best_matched):
            best, best_matched = c, matched
    if len(best_matched) == 3:
        status, customer_id = 'verified', best['customer_id']
    elif best_matched:
        status, customer_id = 'needs_more_factors', None
    else:
        status, customer_id = 'failed', None

    issuance = db['system']['verification_issuance']
    verification_id = _issue(issuance, 'verification')
    expires_at = issuance.get('expires_at', 'end_of_call')
    db['identity_verifications'][verification_id] = {
        'verification_id': verification_id,
        'customer_id': customer_id,
        'status': status,
        'matched_factors': best_matched,
        'expires_at': expires_at,
    }
    return {
        'verification_id': verification_id,
        'status': status,
        'customer_id': customer_id,
        'matched_factors': best_matched,
        'expires_at': expires_at,
    }


def _require_verification(db, verification_id):
    ver = db['identity_verifications'].get(verification_id)
    if ver is None or ver['status'] != 'verified':
        raise ValueError('identity verification required')
    return ver


def _duplicate_reservation(db, customer):
    """Whether an active reservation duplicates the itinerary being booked
    (the customer's latest quote, when one exists)."""
    quote = _latest_quote(db)
    for res_id in customer.get('reservations', []):
        res = db['reservations'].get(res_id)
        if res is None or res['status'] not in ('confirmed', 'ticketed'):
            continue
        if quote is None:
            return True
        itin = res['itinerary']
        if (itin.get('outbound_flight_id') == quote['outbound_flight_id']
                and itin.get('return_flight_id') == quote['return_flight_id']):
            return True
    return False


def get_customer_profile(db, args):
    _require_verification(db, args['verification_id'])
    customer = _customer_by_email(db, args['email'])
    if customer is None:
        raise ValueError('no customer profile for this email')
    out = {
        'customer_id': customer['customer_id'],
        'verification_id': args['verification_id'],
    }
    include = args['include']
    if 'reservations' in include:
        dup = _duplicate_reservation(db, customer)
        customer['duplicate_reservation'] = dup
        out['duplicate_reservation'] = dup
    if 'payment_methods' in include:
        out['payment_methods'] = [dict(pm) for pm in customer['payment_methods']]
    if 'travel_certificates' in include:
        out['travel_certificate_input_required'] = customer['travel_certificate_input_required']
    return out


def validate_travel_certificate(db, args):
    _require_verification(db, args['verification_id'])
    cert = None
    for c in db['travel_certificates'].values():
        if c['code'] == args['certificate_code']:
            cert = c
            break
    if cert is None:
        raise ValueError('unknown certificate code')
    quote = _latest_quote(db)
    if quote is None:
        applicable = cert['available_balance']
    else:
        total = quote.get('total_with_insurance',
                          _round2(quote['fare_taxes_and_checked_bags']
                                  + quote['mobility_device_charge']))
        applicable = _round2(min(cert['available_balance'], total))
    out = {
        'certificate_id': cert['certificate_id'],
        'masked_code': cert['masked_code'],
        'status': cert['status'],
        'available_balance': cert['available_balance'],
        'applicable_amount': applicable,
        'currency': cert['currency'],
    }
    if 'expires_at' in cert:
        out['expires_at'] = cert['expires_at']
    return out


def book_reservation(db, args):
    _require_verification(db, args['verification_id'])
    customer = db['customers'][args['customer_id']]
    ob = db['flights'][args['outbound_flight_id']]
    rt = db['flights'][args['return_flight_id']]
    cfg = db['system']['pricing_config']

    # Price the booking from the quote when present, else from stored prices.
    quote = db['fare_quotes'].get(args['quote_id']) if args['quote_id'] else None
    if quote is not None:
        fare_bags = quote['fare_taxes_and_checked_bags']
        mobility_charge = quote['mobility_device_charge']
        insurance = quote.get('trip_insurance')
    else:
        fare_rt = _round_trip_fare(ob, rt, args['fare_class'])
        fare_bags = _round2(len(args['travelers']) * fare_rt
                            + args['checked_bag_count'] * cfg['checked_bag_fee_round_trip'])
        mobility_charge = _round2(len(args['mobility_devices']) * cfg['mobility_device_fee'])
        insurance = None
    if args['include_trip_insurance'] and insurance is None:
        insurance = _round2(len(args['travelers']) * cfg['trip_insurance_per_traveler'])
    total = _round2(fare_bags + mobility_charge
                    + (insurance if args['include_trip_insurance'] else 0.0))

    if not args['customer_authorized']:
        raise ValueError('customer authorization required')
    if abs(args['confirmed_total'] - total) >= 0.01:
        raise ValueError('confirmed total does not match the priced itinerary')

    # Tender allocation, certificate first.
    allocation = []
    cert = db['travel_certificates'].get(args['certificate_id']) if args['certificate_id'] else None
    cert_amount = 0.0
    if cert is not None and cert['status'] == 'valid':
        cert_amount = _round2(min(cert['available_balance'], total))
        if cert_amount > 0:
            allocation.append({'tender': 'travel_certificate_' + cert['code'],
                               'amount': cert_amount})
    remainder = _round2(total - cert_amount)
    if remainder > 0:
        card = next((pm for pm in customer['payment_methods']
                     if pm['token'] == args['payment_method_token']), None)
        tender = (card['brand'].lower() + '_ending_' + card['last4']
                  if card else args['payment_method_token'])
        allocation.append({'tender': tender, 'amount': remainder})

    issuance = db['system']['reservation_issuance']
    code = _issue(issuance, 'CONF', queue_key='confirmation_codes')
    reservation_id = 'reservation-' + code

    travelers = [{'traveler_id': _traveler_id(t['full_name']),
                  'full_name': t['full_name'],
                  'date_of_birth': t['date_of_birth']}
                 for t in args['travelers']]
    seat_available = any(fo['fare_class'] == args['fare_class']
                         and fo['advance_seat_selection_allowed']
                         for fo in ob['fare_options'])
    devices = []
    for name in args['mobility_devices']:
        rule = _device_rule(db, name)
        devices.append({
            'device_type': rule['device_type'] if rule else name,
            'fee': rule['fee'] if rule else cfg['mobility_device_fee'],
            'serial_number_required': rule['serial_number_required'] if rule else False,
        })
    trip_insurance = {'included': bool(args['include_trip_insurance'])}
    if args['include_trip_insurance']:
        trip_insurance['price'] = insurance
        trip_insurance['covered_traveler_ids'] = [t['traveler_id'] for t in travelers]

    itinerary_out = {
        'origin': dict(ob['origin']),
        'destination': dict(ob['destination']),
        'departure_date': ob['departure_date'],
        'return_date': rt['departure_date'],
    }
    out = {
        'reservation_id': reservation_id,
        'confirmation_code': code,
        'status': 'confirmed',
        'ticketing_status': 'ticketed',
        'itinerary': itinerary_out,
        'travelers': travelers,
        'fare_class': args['fare_class'],
        'seat_selection': {'available': seat_available, 'confirmed_seats': []},
        'checked_bag_count': args['checked_bag_count'],
        'mobility_devices': devices,
        'trip_insurance': trip_insurance,
        'payment_allocation': allocation,
        'payment_status': 'captured',
        'currency': cfg['currency'],
    }

    # Persist state changes.
    stored_itin = dict(itinerary_out)
    stored_itin['outbound_flight_id'] = args['outbound_flight_id']
    stored_itin['return_flight_id'] = args['return_flight_id']
    record = dict(out)
    record['itinerary'] = stored_itin
    record['contact_email'] = args['contact_email']
    record['customer_id'] = args['customer_id']
    record['quote_id'] = args['quote_id']
    record['certificate_id'] = args['certificate_id']
    db['reservations'][reservation_id] = record
    customer.setdefault('reservations', []).append(reservation_id)
    if cert is not None and cert_amount > 0:
        cert['available_balance'] = _round2(cert['available_balance'] - cert_amount)
        cert['applied_amount'] = cert_amount
        cert['applied_to'] = reservation_id
    return out


def transfer_to_specialist(db, args):
    issuance = db['system']['transfer_issuance']
    transfer_id = _issue(issuance, 'transfer')
    db['transfers'][transfer_id] = {
        'transfer_id': transfer_id,
        'reason': args['reason'],
        'summary': args['summary'],
        'status': 'initiated',
    }
    return {'status': 'initiated', 'transfer_id': transfer_id}


TOOLS = {
    'list_supported_airports': list_supported_airports,
    'search_flights': search_flights,
    'calculate_itinerary_price': calculate_itinerary_price,
    'check_mobility_device_requirements': check_mobility_device_requirements,
    'get_customer_profile': get_customer_profile,
    'verify_customer_identity': verify_customer_identity,
    'book_reservation': book_reservation,
    'validate_travel_certificate': validate_travel_certificate,
    'transfer_to_specialist': transfer_to_specialist,
}

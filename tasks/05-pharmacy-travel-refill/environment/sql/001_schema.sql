-- Pharmacy backend schema.
--
-- Table shapes follow the result schemas in domains/pharmacy/tool_registry.json
-- and the lifecycle in domains/pharmacy/policy.md. Lifecycle vocabularies are
-- CHECK constraints, so an illegal status fails in the database rather than only
-- in the tool layer.

BEGIN;

-- Scenario clock and other per-conversation constants. Tools read scenario_time
-- from here, not from wall time, so a container started next year sees the same
-- world.
CREATE TABLE scenario (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL
);

-- Every id that appears in a tool result is issued from here, so ids are stable
-- across runs and a second allocation cannot repeat the first.
CREATE TABLE id_allocator (
    entity_type  TEXT NOT NULL,
    scope        TEXT NOT NULL DEFAULT '',
    next_value   INTEGER NOT NULL,
    template     TEXT NOT NULL,
    PRIMARY KEY (entity_type, scope)
);

CREATE TABLE medications (
    medication_id  TEXT PRIMARY KEY,
    display_name   TEXT NOT NULL,
    form           TEXT,
    strength       TEXT,
    controlled     BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE stores (
    store_id                 TEXT PRIMARY KEY,
    display_name             TEXT NOT NULL,
    address                  TEXT,
    counter_closes_at        TEXT NOT NULL
        CHECK (counter_closes_at ~ '^([01][0-9]|2[0-3]):[0-5][0-9]$'),
    front_store_closes_later BOOLEAN NOT NULL,
    front_store_closes_at    TEXT
        CHECK (front_store_closes_at ~ '^([01][0-9]|2[0-3]):[0-5][0-9]$'),
    timezone                 TEXT NOT NULL,
    services                 TEXT[],
    -- Next position the fill queue will hand out at this store, and the store's
    -- current turnaround estimate. Both are read when a claim activates a queue.
    queue_next_position      INTEGER NOT NULL DEFAULT 1,
    queue_estimated_minutes  INTEGER NOT NULL DEFAULT 30,
    -- Ordering key for "nearby" searches; lower sorts first.
    proximity_rank           INTEGER NOT NULL DEFAULT 100,
    -- Search scope: a nearby search from a fill store covers that store's
    -- district only, so the rest of the chain never surfaces as "nearby".
    district                 TEXT NOT NULL,
    CHECK (NOT front_store_closes_later OR front_store_closes_at IS NOT NULL)
);

CREATE INDEX stores_district ON stores (district, proximity_rank);

CREATE TABLE store_inventory (
    store_id       TEXT NOT NULL REFERENCES stores(store_id),
    medication_id  TEXT NOT NULL REFERENCES medications(medication_id),
    in_stock       BOOLEAN NOT NULL,
    reserved       BOOLEAN NOT NULL DEFAULT FALSE,
    on_hand_units  INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (store_id, medication_id)
);

CREATE TABLE insurance_plans (
    plan_id               TEXT PRIMARY KEY,
    display_name          TEXT NOT NULL,
    copay                 NUMERIC(10, 2) NOT NULL,
    currency              TEXT NOT NULL DEFAULT 'USD' CHECK (currency = 'USD'),
    -- Payment options the plan allows once a claim is paid, in emission order.
    paid_payment_options  TEXT[] NOT NULL,
    -- Payment options while no claim has been paid.
    unpaid_payment_options TEXT[] NOT NULL
);

-- Per-plan payer policy for each override reason. Held as data, so a reason the
-- conversation never raised still returns the payer's real answer.
CREATE TABLE plan_override_rules (
    plan_id       TEXT NOT NULL REFERENCES insurance_plans(plan_id),
    reason        TEXT NOT NULL
        CHECK (reason IN ('lost_medication', 'vacation_supply', 'dose_change', 'other')),
    override_id   TEXT NOT NULL,
    decision      TEXT NOT NULL
        CHECK (decision IN ('approved', 'approved_one_time',
                            'pending_patient_participation', 'denied')),
    PRIMARY KEY (plan_id, reason)
);

CREATE TABLE patients (
    patient_id         TEXT PRIMARY KEY,
    full_name          TEXT NOT NULL,
    date_of_birth      DATE NOT NULL,
    preferred_store_id TEXT REFERENCES stores(store_id),
    insurance_plan_id  TEXT REFERENCES insurance_plans(plan_id),
    allergies          TEXT[] NOT NULL DEFAULT '{}'
);

CREATE INDEX patients_name_dob ON patients (lower(full_name), date_of_birth);

CREATE TABLE notification_destinations (
    destination_id     TEXT PRIMARY KEY,
    patient_id         TEXT NOT NULL REFERENCES patients(patient_id),
    channel            TEXT NOT NULL CHECK (channel IN ('sms', 'phone', 'email')),
    masked_destination TEXT NOT NULL,
    verified           BOOLEAN NOT NULL
);

CREATE TABLE prescriptions (
    prescription_id           TEXT PRIMARY KEY,
    patient_id                TEXT NOT NULL REFERENCES patients(patient_id),
    medication_id             TEXT NOT NULL REFERENCES medications(medication_id),
    prescriber                TEXT,
    quantity                  TEXT,
    days_supply               INTEGER,
    refills_remaining         INTEGER,
    last_fill_date            DATE,
    -- Stored with the fill store's offset, and emitted verbatim. The registry
    -- documents received_at as a local date-time in the store's timezone.
    received_at               TEXT NOT NULL,
    prescription_valid        BOOLEAN NOT NULL,
    fill_store_id             TEXT NOT NULL REFERENCES stores(store_id),
    workflow_status           TEXT NOT NULL
        CHECK (workflow_status IN ('received', 'claim_pending', 'claim_rejected',
                                   'claim_paid', 'awaiting_pharmacist_verification',
                                   'ready_for_pickup', 'picked_up', 'transferred',
                                   'cancelled', 'expired')),
    customer_facing_status    TEXT NOT NULL
        CHECK (customer_facing_status IN ('processing', 'ready', 'picked_up')),
    priority_reason           TEXT,
    payment_options           TEXT[] NOT NULL,
    ready_alert_destination_id TEXT REFERENCES notification_destinations(destination_id),
    notification_channel      TEXT CHECK (notification_channel IN ('sms', 'phone', 'email')),
    ready_alert               TEXT CHECK (ready_alert IN ('enabled', 'disabled'))
);

CREATE INDEX prescriptions_patient ON prescriptions (patient_id, received_at DESC);

-- Claim submissions, newest last. get_prescription reads the latest row; a
-- resubmission appends rather than overwriting, so the payer history survives.
CREATE TABLE claims (
    claim_seq        BIGSERIAL PRIMARY KEY,
    prescription_id  TEXT NOT NULL REFERENCES prescriptions(prescription_id),
    status           TEXT NOT NULL
        CHECK (status IN ('not_submitted', 'pending', 'paid', 'rejected')),
    reason           TEXT
        CHECK (reason IN ('refill_too_soon', 'not_covered',
                          'prior_authorization_required', 'plan_inactive')),
    copay            NUMERIC(10, 2),
    currency         TEXT CHECK (currency = 'USD'),
    override_id      TEXT,
    submitted_at     TEXT,
    -- A rejection must name a reason; anything else must not.
    CHECK ((status = 'rejected') = (reason IS NOT NULL)),
    CHECK ((status = 'paid') = (copay IS NOT NULL))
);

CREATE INDEX claims_prescription ON claims (prescription_id, claim_seq DESC);

CREATE TABLE claim_overrides (
    override_id      TEXT PRIMARY KEY,
    prescription_id  TEXT NOT NULL REFERENCES prescriptions(prescription_id),
    reason           TEXT NOT NULL
        CHECK (reason IN ('lost_medication', 'vacation_supply', 'dose_change', 'other')),
    status           TEXT NOT NULL
        CHECK (status IN ('approved', 'approved_one_time',
                          'pending_patient_participation', 'denied')),
    urgency_context  TEXT,
    requested_at     TEXT,
    -- Set when an approved_one_time override is spent. Enforced by the claim
    -- handler, so the same one-time approval cannot pay a second claim.
    consumed_at      TEXT
);

CREATE TABLE fill_queue (
    prescription_id                 TEXT PRIMARY KEY
        REFERENCES prescriptions(prescription_id),
    status                          TEXT NOT NULL
        CHECK (status IN ('blocked_by_claim', 'active', 'completed')),
    position                        INTEGER CHECK (position >= 1),
    estimated_minutes               INTEGER CHECK (estimated_minutes >= 0),
    pharmacist_verification_required BOOLEAN,
    priority_note                   TEXT CHECK (priority_note IN ('present', 'absent'))
);

-- Current claim state keyed by prescription, so a read can address the payer's
-- position without knowing a claim_seq, which shifts as the population changes.
CREATE VIEW latest_claims AS
SELECT DISTINCT ON (prescription_id)
       prescription_id, status, reason, copay, currency, override_id, submitted_at
  FROM claims
 ORDER BY prescription_id, claim_seq DESC;

CREATE TABLE transfer_requests (
    transfer_id          TEXT PRIMARY KEY,
    prescription_id      TEXT NOT NULL REFERENCES prescriptions(prescription_id),
    source_store_id      TEXT NOT NULL REFERENCES stores(store_id),
    destination_store_id TEXT NOT NULL REFERENCES stores(store_id),
    status               TEXT NOT NULL
        CHECK (status IN ('requested', 'pending_pharmacist_review', 'accepted',
                          'completed', 'rejected')),
    reason               TEXT,
    patient_authorized   BOOLEAN NOT NULL,
    original_fill_active BOOLEAN NOT NULL,
    requested_at         TEXT
);

CREATE TABLE specialist_transfers (
    transfer_id  TEXT PRIMARY KEY,
    reason       TEXT NOT NULL,
    summary      TEXT NOT NULL,
    status       TEXT NOT NULL CHECK (status IN ('initiated', 'failed')),
    created_at   TEXT
);

-- Append-only record of every tool call served, reads included.
CREATE TABLE tool_call_log (
    call_seq    BIGSERIAL PRIMARY KEY,
    tool_name   TEXT NOT NULL,
    arguments   JSONB NOT NULL,
    result      JSONB,
    http_status INTEGER NOT NULL,
    called_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMIT;

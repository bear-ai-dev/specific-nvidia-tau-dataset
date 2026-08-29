-- The entities this conversation touches.
--
-- Every value here is either read back verbatim by a recorded tool result or is
-- a field the recorded results never revealed. The former are exact; the latter
-- are plausible and consistent with the call, and are marked as such.
--
-- Scenario clock: 2026-08-27T18:12:00-05:00. Miles Carter lost his albuterol
-- inhaler, leaves town the next morning, and the payer has already rejected the
-- refill as too soon.

BEGIN;

INSERT INTO patients
    (patient_id, full_name, date_of_birth, preferred_store_id,
     insurance_plan_id, allergies)
VALUES
    ('patient-miles-carter', 'Miles Carter', '1988-06-14', 'oak-street-current',
     'plan-midwest-choice-ppo', '{}');

-- Masked form is read aloud, so it is stored exactly as the recorded results
-- render it rather than derived from a number the results never disclosed.
INSERT INTO notification_destinations
    (destination_id, patient_id, channel, masked_destination, verified)
VALUES
    ('patient-miles-mobile', 'patient-miles-carter', 'sms',
     '***-***-on-file', TRUE);

-- prescriber, quantity, days_supply, refills_remaining and last_fill_date are
-- never returned by any recorded result; they are consistent filler so the row
-- is a complete record rather than a stub.
INSERT INTO prescriptions
    (prescription_id, patient_id, medication_id, prescriber, quantity,
     days_supply, refills_remaining, last_fill_date, received_at,
     prescription_valid, fill_store_id, workflow_status, customer_facing_status,
     priority_reason, payment_options, ready_alert_destination_id,
     notification_channel, ready_alert)
VALUES
    ('prescription-albuterol', 'patient-miles-carter', 'albuterol-inhaler',
     'Dr. Elena Vasquez', '1 inhaler (8.5 g)', 30, 3, '2026-08-05',
     '2026-08-27T10:42:00-05:00', TRUE, 'oak-street-current',
     'claim_rejected', 'processing', NULL,
     '{pay_at_pickup}', 'patient-miles-mobile', NULL, NULL);

-- The rejection the call opens on. Rerunning the claim appends a new row rather
-- than editing this one, so the payer history stays intact.
INSERT INTO claims
    (prescription_id, status, reason, copay, currency, override_id, submitted_at)
VALUES
    ('prescription-albuterol', 'rejected', 'refill_too_soon', NULL, NULL, NULL,
     '2026-08-27T10:48:00-05:00');

INSERT INTO fill_queue
    (prescription_id, status, position, estimated_minutes,
     pharmacist_verification_required, priority_note)
VALUES
    ('prescription-albuterol', 'blocked_by_claim', NULL, NULL, NULL, 'absent');

COMMIT;

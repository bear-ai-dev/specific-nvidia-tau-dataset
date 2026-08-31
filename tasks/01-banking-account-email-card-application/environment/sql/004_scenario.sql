-- The entities this conversation touches.
--
-- Hand-written and loaded after the generated population so a regenerated seed
-- cannot move them. Every value the recorded tool results revealed is marked
-- REVEALED; everything else is plausible filler that the recording never
-- observed and that the results therefore do not depend on. Where filler was
-- chosen to make a derived value fall out correctly, the comment says so.

BEGIN;

-- REVEALED: account id SF204771 resolves uniquely, the profile's name is
-- 'Johnny Monroe', and the two factors the profile requires are the billing ZIP
-- and the mobile last four.
--
-- account_id is the reference the caller quotes; every later call carries the
-- internal id the lookup hands back. verification_key names the records the
-- verification and confirmation calls compose.
--
-- The login identifier is a username rather than the address, which is what
-- makes login_identifier_changed false after the change. The pre-change address
-- is filler, and deliberately not at outlook.com: the session delivery masks
-- the address the profile holds at the time of the call, so an address that
-- masks to something other than 'j***@outlook.com' is what proves the masked
-- destination is read after the update rather than seeded to match.
INSERT INTO customers (
    customer_id, account_id, full_name, family_name, verification_key,
    notice_slug,
    primary_email, notification_email, billing_zip, birth_month, birth_day,
    mobile_last4, caller_channel_match, required_verification_methods,
    login_identifier_kind
) VALUES (
    '4d6679ca-bcef-4893-81bf-488f66c8c666', 'SF204771', 'Johnny Monroe',
    'Monroe', 'SF204771', 'johnny',
    'johnny.monroe@relaymail.example', 'johnny.monroe@relaymail.example',
    '19447', 4, 16, '1251', NULL, ARRAY['billing_zip', 'mobile_last4'],
    'username'
);

-- A second Johnny Monroe. The recording resolves on the account id, so the name
-- collision changes nothing there; it exists so that resolving this profile by
-- name alone is refused as ambiguous rather than silently landing on one row.
INSERT INTO customers (
    customer_id, account_id, full_name, family_name, verification_key,
    notice_slug,
    primary_email, notification_email, billing_zip, birth_month, birth_day,
    mobile_last4, caller_channel_match, required_verification_methods,
    login_identifier_kind
) VALUES (
    '22a29542-c52c-5c19-9d39-7e08acb6106c', 'SF319088', 'Johnny Monroe',
    'Monroe', 'SF319088', 'johnnym',
    'j.monroe.pa@fastmail.example', 'j.monroe.pa@fastmail.example', '19081',
    11, 3, '7734', NULL, ARRAY['billing_zip', 'card_last4'], 'email'
);

-- REVEALED: one enrolled SMS channel, id '279561c9-f2ce-4402-a23a-2e19316678b3', masked
-- '***-***-1251'; the confirmation sent to it reads back verified at
-- 2026-08-27T10:48:39-04:00.
--
-- confirmation_completes and confirmation_verified_at carry that outcome as
-- data. The customer completes the challenge on the handset, which no tool can
-- watch happen, so the channel records that its owner does complete it and when
-- the completion is stamped; the poll reads those columns instead of assuming
-- success.
INSERT INTO trusted_channels (
    channel_id, customer_id, type, masked_destination, enrolled,
    confirmation_completes, confirmation_verified_at
) VALUES (
    '279561c9-f2ce-4402-a23a-2e19316678b3',
    '4d6679ca-bcef-4893-81bf-488f66c8c666', 'sms', '***-***-1251', TRUE, TRUE,
    '2026-08-27T10:48:39-04:00'
);

-- A retired handset still on file but no longer enrolled. The recorded lookup
-- reports exactly one channel, so this row is what the enrolment filter has to
-- exclude, and a confirmation aimed at it is refused rather than sent.
INSERT INTO trusted_channels (
    channel_id, customer_id, type, masked_destination, enrolled,
    confirmation_completes, confirmation_verified_at
) VALUES (
    'b60f5538-ab2d-51cd-a39b-9082dee804eb',
    '4d6679ca-bcef-4893-81bf-488f66c8c666', 'sms', '***-***-4407', FALSE,
    FALSE, NULL
);

INSERT INTO trusted_channels (
    channel_id, customer_id, type, masked_destination, enrolled,
    confirmation_completes, confirmation_verified_at
) VALUES (
    'd509ed27-5866-5486-bac7-519a9cb96090',
    '22a29542-c52c-5c19-9d39-7e08acb6106c', 'sms', '***-***-7734', TRUE, FALSE,
    NULL
);

-- REVEALED, indirectly: the verification record is named
-- 'verification-SF204771-email-change' and the confirmation
-- 'confirmation-email-change-SF204771'. The verification is named after the open
-- reason the profile is in contact, so that reason is a row: an email change.
-- Re-verifying during this call returns the same record rather than a second
-- one, which is why the identifier can be stated in a later argument at all.
INSERT INTO service_cases (case_id, customer_id, case_kind, case_slug, status, opened_at)
VALUES ('case-SF204771-email', '4d6679ca-bcef-4893-81bf-488f66c8c666',
        'email_change', 'email-change', 'open', '2026-08-27T10:45:00-04:00');

-- Filler. The profile holds one card, so an off-path card read resolves without
-- a card_last4 and the account is not an empty shell.
INSERT INTO card_accounts (
    card_id, customer_id, card_last4, product_id, status, reported_lost,
    payment_status, credit_limit, available_credit
) VALUES (
    'card-SF204771-4419', '4d6679ca-bcef-4893-81bf-488f66c8c666', '4419',
    'f2b0f735-a08d-58bf-81b7-0ce8a7daeab5', 'active', FALSE, 'current',
    9000.00, 7412.55
);

INSERT INTO card_accounts (
    card_id, customer_id, card_last4, product_id, status, reported_lost,
    payment_status, credit_limit, available_credit
) VALUES (
    'card-SF319088-2260', '22a29542-c52c-5c19-9d39-7e08acb6106c', '2260',
    '7df58cd6-c896-59cc-bb3d-f4f90f9bf6e1', 'active', FALSE, 'current',
    6000.00, 5180.00
);

-- Filler activity, so a posted-transaction search or a card read during this
-- conversation answers from real rows.
INSERT INTO transactions (
    transaction_id, card_id, kind, merchant_key, merchant, merchant_location,
    descriptor, category, amount, status, settlement_state, occurred_at,
    posted_date, resource_label, short_ref
) VALUES
    ('1547278e-cfdb-58c0-8cec-2c9635386804', 'card-SF204771-4419', 'posted',
     'grocery', 'Riverside Market', 'Norristown, Pennsylvania',
     'RIVERSIDE MKT', 'grocery', 84.22, 'posted', 'settled',
     '2026-08-24T18:02:00-04:00', '2026-08-25', 'transaction ending 6621',
     '6621'),
    ('8b743d52-f772-54d4-9854-7c6bc7e1b1c7', 'card-SF204771-4419', 'posted',
     'streaming',
     'Lumen Streaming', NULL, 'LUMEN STREAM', 'digital goods',
     17.99, 'posted', 'settled', '2026-08-25T06:14:00-04:00', '2026-08-25',
     'transaction ending 6704', '6704'),
    ('e0ca18b3-8a32-5f14-9bfb-8d5d8496c203', 'card-SF204771-4419',
     'authorization', 'fuel',
     'Northgate Fuel', 'Norristown, Pennsylvania', 'NORTHGATE FUEL', 'fuel',
     52.10, 'approved', 'pending', '2026-08-27T08:31:00-04:00', NULL,
     'transaction ending 6890', '6890');

COMMIT;

# Data quality: conventions, audit, and known limitations

This document states what "good" means for this dataset, what was checked,
and what a researcher should still expect to find. It exists so that both
sides can agree up front on acceptance criteria before any larger order.

## Quality conventions

1. **Verbatim speech.** Message content is the verbatim transcription of the
   audio, disfluencies included. Speech is never edited to make behavior look
   cleaner; defects in what was said are annotated, not rewritten.
2. **Grounding.** Every fact an agent speaks must be traceable to a prior
   tool result, the customer's own speech, or the domain policy. Spoken
   content that fails this rule carries a `grounding_review` record
   (`text_anchor`, `category`, `reason`, `remediation`) on its speech event.
   There are 86 such records across the 10 conversations. Categories include
   `pre_echoed_tool_result` (a backend fact spoken before the call that
   grounds it), `fabricated_disposition_guarantee`, `unsupported_tool_duration`,
   `missing_delivery_authorization`, `source_conflation`, and
   `unsafe_authentication_script`.
3. **Call placement.** For every `function_call` event:
   `placement_seconds` lies after the end of the speech that supplies any
   argument value and before the start of the speech that reports any result
   fact; `audio_reference` start/end are null (a call has no audio) and
   `inferred_window_seconds` starts at the placement. Where the recorded call
   order cannot honestly satisfy this (the agent spoke a result before any
   plausible call slot), the trajectory keeps reality and the speech carries a
   `pre_echoed_tool_result` flag instead of a silently relocated call.
4. **Scenario clock.** Each conversation declares `scenario_time` (wall clock
   at audio t=0), repeated in the system message. All timestamps in tool
   results are concrete and consistent with it; relative expressions in tool
   arguments ("Sunday night") are resolved to typed values and flagged
   `relative_time_resolved_from_scenario_clock`.
5. **Closed schemas.** Registry result schemas are fully typed
   (`additionalProperties: false` at every level), with policy-defined
   lifecycles as enums, `format: date`/`date-time` on temporal fields, and
   explicit currency fields on money. A deterministic mock environment can be
   implemented from the registry alone. Where recorded values are genuinely
   human-relative strings (e.g. a deadline spoken as "18:00 tomorrow" inside
   a result the agent must read back verbatim), the schema documents that
   representation instead of mislabeling it as ISO.
6. **Training exports.** A turn flagged by `grounding_review` is excluded
   from `nemotron_message_actions.jsonl` (72 turns excluded, 256 kept). All
   85 tool calls are exported; their arguments are schema-valid and the flags
   that concern them live on the surrounding speech.

### Note on spoken values in voice transcripts

Canonical values from tool results (IDs, amounts, deadlines) appear in voice
transcripts spelled out ("WST four eight one- six six two" for WST481662;
"six tomorrow evening" for 18:00 tomorrow). Any checker that matches required
facts against voice transcripts must normalize spoken forms before matching.

## Machine checks (run on every revision)

- JSON-Schema validation of all 85 call argument sets against registry
  parameter schemas, and all 85 result payloads against registry result
  schemas (closed).
- Call/output pairing, unique call ids, chronological input order,
  event-index alignment between `input` and `event_metadata`.
- Placement invariants from convention 3, with a 1 s tolerance against
  diarized segment tails (segment ends include trailing silence).
- transcript.txt marker sync: exactly one `[tool]` line per trajectory call,
  no phantom markers, no legacy inline markers.
- Placeholder scan: no `scenario_*`, `*_in_source_recording`, or
  `earlier_today`-style values anywhere in a trajectory.
- Policy sync: the `<policy>` block in every system message is byte-identical
  to its domain's `policy.md`.
- Export consistency: every JSONL row's `input` is an exact prefix of its
  conversation trajectory and its `expected_action` equals the next item;
  trajectory_ids unique.
- Audio: sample rate, bit depth, duration, and high-band energy per file
  (`exports/audio_manifest.json`).

## Provenance of the annotation layers

- Audio, speech content, and speaker turns: recorded enactments,
  diarized and transcribed with word-level timestamps (ElevenLabs Scribe v2),
  then human-corrected. Two audio-verified corrections were applied against
  channel-isolated tracks and are marked with `correction` notes in
  `event_metadata` (a mis-attributed overlapped phrase; a leaked stage
  direction).
- Tool calls and results: human gold annotations of the enacted CSR's backend
  interactions. Calls that the source recording never narrates are
  annotator-inferred insertions and carry `annotation_confidence: "medium"`
  with inferred windows.
- State snapshots: reconstructed strictly from tool results; fields the
  outputs never reveal are null with an explanatory note, not invented.
- Verifier fields in the exports (`pass_rate*`, `qwen_235b_info`,
  `num_unique_actions`): intentionally unpopulated placeholders — see the
  README's export-format notes.

## Known limitations

- **Turn-taking coverage**: word-level timestamps and turn-taking files exist
  for 8 of 10 conversations; the airline and telecom recordings were produced
  in a later batch without Scribe output. Backchannel/overlap fields are
  automatic candidates, not human-accepted gold. Accent and environment are
  marked `not_human_annotated`.
- **Behavioral exceptions are retained by design**: several conversations
  contain policy violations by the enacted agent (an OTP read-back request, a
  booking without spoken total authorization, a session issued without channel
  consent). Each is flagged. Do not train on flagged turns as positive
  examples.
- **Tools are contracts, not code**: the registries define schemas and
  lifecycles but no executable simulator; the state snapshots are
  reconstructed from tool results rather than a seeded database.
- **Two conversations share a customer story** (retail missing-package and
  damaged-item are consecutive days for the same customer); their tool
  outputs intentionally cross-reference.

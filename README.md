# NVIDIA voice-agent pilot

This public, data-only sample contains structured voice-agent conversations for
custom banking-card, pharmacy, and retail workflows. It is intentionally
described as **Tau-style custom-domain data**, not as an exact export of Tau's
public registries.

The snapshot contains 8 conversations, 24 synchronized audio tracks, 3 domain
registries, 49 structured agent tool calls, and 49 Nemotron-style next-action
rows. Every conversation includes mixed audio and isolated speaker tracks as
48 kHz, 24-bit, mono PCM WAV files.

## Grounded-state status

The calls were enacted without an instrumented CRM. Accordingly, any state
records in this package are scenario-author annotations, not observed backend
snapshots. They must be labeled `scenario_reconstruction` until a real stateful
backend or CRM event log exists. This is still useful for a pilot, but it is not
equivalent to Tau's executable before/after database state.

## Package map

- `domains/<domain>/tool_registry.json`: versioned tool definitions and
  JSON-Schema arguments.
- `domains/<domain>/policy.md`: operational policy used for the annotations.
- `conversations/<id>/conversation.json`: goal, outcome, structured calls and
  results, required facts, state reconstruction, speaker mapping, and source
  references.
- `conversations/<id>/scribe/`: fresh ElevenLabs Scribe v2 JSON, readable text,
  and API provenance.
- `conversations/<id>/turn_taking.json`: derived turns, pauses, backchannels,
  audio events, and overlap/barge-in candidates.
- `exports/nemotron_tool_calls.jsonl`: one training row per agent tool call.
- `exports/conversation_manifest.json`: compact index of the conversation
  annotations.

## Publication scope

This public repository is a data-only snapshot. Internal reports, build and
source-retrieval tooling, dependency files, and source/integrity manifests are
not included.

## Compatibility statement

This package follows the useful structural ideas from Tau (domain policy,
typed tools, goal/outcome/state grounding) and NVIDIA Nemotron (policy + tools +
conversation context -> expected next function call). It does not claim that
custom banking-card, pharmacy, delivery-trace, or refund-trace functions are
literal Tau tools.

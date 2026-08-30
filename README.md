# NVIDIA voice-agent pilot

This public, data-only sample contains structured voice-agent conversations for
custom airline, banking, pharmacy, retail, and telecom workflows. It is
intentionally described as **Tau-style custom-domain data**, not as an exact
export of Tau's public registries.

The snapshot contains 10 conversations, 30 synchronized audio tracks, 5 domain
registries, 85 structured agent tool calls, and 10 annotated conversation
transcripts. Every conversation includes full-call audio and isolated speaker
tracks as 48 kHz, 24-bit, mono PCM WAV files; measured per-file bandwidth is
published in `audio_manifest.json` (all 30 files carry genuine wideband content
— they are not upsampled telephony audio).

Every tool has JSON-Schema contracts for both arguments and results, closed
with `additionalProperties: false` at every level, with policy-defined status
lifecycles expressed as enums so the registries can back a deterministic mock
environment. Each conversation carries a scenario clock (`scenario_time`, also
stated in the system message), and every tool-result value is concrete against
it — no placeholder or relative values remain in tool payloads.

Internal backend identifiers are opaque UUIDs and are declared with
`format: uuid` in the registries. Human-facing business references remain
separate readable values: for example, `account_id`, `reference_code`,
`case_number`, and `confirmation_code`. A lookup may accept one of those
references, but later tool calls use the UUID returned for the resolved entity.

The trajectories include 86 explicit `grounding_review` records marking spoken
behavior that is unsupported, contradictory, unsafe, or otherwise not clean
training behavior (fabricated guarantees, results spoken before the grounding
call, consent gaps, source conflation). This snapshot is suitable for schema
and pilot-fit review; it must not be represented as 10 exception-free
behavioral trajectories — the exception layer is the point.

## Package map

- `domains/<domain>/tool_registry.json`: versioned tool definitions with closed
  JSON-Schema argument/result contracts (registry_version 0.4.0).
- `domains/<domain>/policy.md`: operational policy used for the annotations;
  byte-identical to the `<policy>` block embedded in each conversation's
  system message.
- `conversations/<id>/audio/full.wav`: synchronized full-call audio.
- `conversations/<id>/audio/speaker-1.wav` / `speaker-2.wav`: synchronized
  isolated speaker tracks.
- `conversations/<id>/transcripts/annotated-transcript.json`: the full
  chronological trajectory — system policy message, speech, function calls,
  function outputs, per-event audio timestamps, call-placement windows, and
  `grounding_review` records. Call placement obeys two invariants: a call is
  placed after the speech that supplies its arguments and before the speech
  that reports its results.
- `conversations/<id>/transcripts/transcript.txt`: the timestamped mixed-call
  transcript; each tool call appears as one standalone
  `[HH:MM:SS.mmm] [tool] <name>: <label>` line at its placement time.
- `conversations/<id>/transcripts/words.json`: word-level timestamps with
  speaker labels and confidence (ElevenLabs Scribe v2), for 8 of 10
  conversations (absent for airline and telecom, which were recorded in a
  later batch).
- `conversations/<id>/turn_taking.json`: turn segmentation, pause boundaries,
  backchannel and overlap candidates, per-speaker metadata (same 8 of 10;
  accent/environment fields are marked `not_human_annotated` rather than
  guessed).
- `conversations/<id>/state/initial_state.json` / `final_state.json`:
  before/after backend state reconstructed strictly from tool results (no
  invented fields; derivation is stated in the file).
- `conversation_manifest.json`: index — goal, outcome, scenario time, and
  pointers to transcript, state, and turn-taking files.
- `audio_manifest.json`: per-file sample rate, bit depth, duration,
  and measured spectral energy above 10/16/20 kHz.

## Publication scope

Each conversation intentionally excludes internal reports, source scripts,
and build tooling. Word-level timestamps and turn-taking annotations are
included where they exist (8 of 10 conversations); per-speaker accent and
environment labels have not been human-annotated and are marked as such.

## Compatibility statement

This package follows the useful structural ideas from Tau (domain policy and
typed tools) and NVIDIA Nemotron (policy + tools + conversation context ->
expected next action). It does not claim that these custom-domain functions
are literal Tau tools — the registries are declarative contracts, not
executable implementations.

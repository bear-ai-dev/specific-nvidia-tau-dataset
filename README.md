# NVIDIA voice-agent pilot

This public, data-only sample contains structured voice-agent conversations for
custom airline, banking, pharmacy, retail, and telecom workflows. It is
intentionally described as **Tau-style custom-domain data**, not as an exact
export of Tau's public registries.

The snapshot contains 10 conversations, 30 synchronized audio tracks, 5 domain
registries, 85 structured agent tool calls, 10 annotated conversation
transcripts, and 341 NVIDIA-schema next-action rows
(85 tool-call targets plus 256 clean assistant-message targets). Every
conversation includes full-call audio and isolated speaker tracks as 48 kHz,
24-bit, mono PCM WAV files; measured per-file bandwidth is published in
`exports/audio_manifest.json` (all 30 files carry genuine wideband content —
they are not upsampled telephony audio).

Every tool has JSON-Schema contracts for both arguments and results, closed
with `additionalProperties: false` at every level, with policy-defined status
lifecycles expressed as enums so the registries can back a deterministic mock
environment. Each conversation carries a scenario clock (`scenario_time`, also
stated in the system message), and every tool-result value is concrete against
it — no placeholder or relative values remain in tool payloads.

The trajectories include 86 explicit `grounding_review` records marking spoken
behavior that is unsupported, contradictory, unsafe, or otherwise not clean
training behavior (fabricated guarantees, results spoken before the grounding
call, consent gaps, source conflation). Assistant turns carrying a
`grounding_review` flag are excluded from the message-action training export.
This snapshot is suitable for schema and pilot-fit review; it must not be
represented as 10 exception-free behavioral trajectories — the exception layer
is the point.

## Package map

- `domains/<domain>/tool_registry.json`: versioned tool definitions with closed
  JSON-Schema argument/result contracts (registry_version 0.3.0).
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
- `conversations/<id>/state/seed_database.json`: the complete backend records
  at call start — every field observed in tool results verbatim, plus
  synthetic-but-consistent values for unobserved fields — with a minimal
  `external_events` list for mid-call world changes no tool caused.
- `env/<domain>/tools.py`: executable, deterministic mock implementations of
  every registry tool, operating on the seed database. `env/replay.py`
  replays each conversation's recorded gold calls against its seed and
  verifies every tool output byte-for-byte plus the final state:
  `python3 env/replay.py` passes on all 10 conversations.
- `exports/nemotron_tool_calls.jsonl`: the NVIDIA training view — one
  prefix/expected-action row per agent tool call (85 rows).
- `exports/nemotron_message_actions.jsonl`: same row schema with
  `expected_action.type: "message"` for every assistant speech turn that is
  free of grounding_review flags (256 rows; 72 flagged turns excluded).
- `exports/conversation_manifest.json`: index — goal, outcome, scenario_time,
  per-conversation row counts, and pointers to state/turn-taking files.
- `exports/audio_manifest.json`: per-file sample rate, bit depth, duration,
  and measured spectral energy above 10/16/20 kHz.

## Export-format notes (Nemotron compatibility)

Rows follow the schema of
`nvidia/Nemotron-RL-Agentic-Conversational-Tool-Use-Pivot-v1`: identical
top-level field set, policy carried as the first `input` item (a system
message), `parallel_tool_calls: false`, `expected_action` as
`function_call` (JSON-string arguments) or `message`. Honest divergences,
rather than fabricated values:

- `pass_rate*`, `qwen_235b_info`, and `num_unique_actions` are placeholders
  (0 / empty / 1). The reference dataset fills these from verifier rollouts;
  no rollouts were run against this human-gold data, and we will not invent
  reward statistics. Filter or re-score before mixing with the reference set.
- `agent_ref` is `{"type": "human_annotations", "name": "voice_tool_call_gold"}`
  — these rows are human gold labels, not verifier-generated trajectories.
- `trajectory_id` is unique per row (as in the reference set);
  `meta_info.conversation_id` and `meta_info.source_event_index` link each row
  back to its conversation and position — two extra keys the reference set
  does not carry.

## Publication scope

Each conversation intentionally excludes internal reports, source scripts,
and build tooling. Word-level timestamps and turn-taking annotations are
included where they exist (8 of 10 conversations); per-speaker accent and
environment labels have not been human-annotated and are marked as such.

## Compatibility statement

This package follows the useful structural ideas from Tau (domain policy and
typed tools) and NVIDIA Nemotron (policy + tools + conversation context ->
expected next action). It does not claim that these custom-domain functions
are literal Tau tools, but each domain's tools are executable: `env/` holds
deterministic reference implementations over per-conversation seed databases,
verified by replaying every recorded call.

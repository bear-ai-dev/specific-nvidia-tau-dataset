# NVIDIA voice-agent pilot

This public, data-only sample contains structured voice-agent conversations for
custom banking, pharmacy, and retail workflows. It is intentionally
described as **Tau-style custom-domain data**, not as an exact export of Tau's
public registries.

The snapshot contains 8 conversations, 24 synchronized audio tracks, 3 domain
registries, 52 structured agent tool calls, 8 annotated conversation
transcripts, and 52 NVIDIA-schema next-action rows. Every conversation includes
full-call audio and isolated speaker tracks as 48 kHz, 24-bit, mono PCM WAV
files.

## Package map

- `domains/<domain>/tool_registry.json`: versioned tool definitions and
  JSON-Schema arguments.
- `domains/<domain>/policy.md`: operational policy used for the annotations.
- `conversations/<id>/audio/full.wav`: synchronized full-call audio.
- `conversations/<id>/audio/speaker-1.wav` and `speaker-2.wav`: synchronized
  isolated speaker tracks.
- `conversations/<id>/transcripts/annotated-transcript.json`: the full
  chronological transcript with speech, function calls, function outputs,
  policy, tool definitions, timestamps, and audio references.
- `conversations/<id>/transcripts/transcript.txt`: the unchanged baseline
  transcript supplied in the source Google Drive folder.
- `exports/nemotron_tool_calls.jsonl`: the derived NVIDIA training view, with
  one prefix/expected-action row per agent tool call.
- `exports/conversation_manifest.json`: compact index of the public structured
  transcripts.

## Publication scope

Each conversation intentionally contains only two folders: `audio/` and
`transcripts/`. Internal reports, source files, Scribe artifacts, turn-taking
files, build tooling, dependency files, and source/integrity manifests are not
included.

## Compatibility statement

This package follows the useful structural ideas from Tau (domain policy and
typed tools) and NVIDIA Nemotron (policy + tools + conversation context ->
expected next function call). It does not claim that custom banking, pharmacy,
delivery-trace, or refund-trace functions are literal Tau tools.

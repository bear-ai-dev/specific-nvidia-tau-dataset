# Customer Service Dataset

This repository contains 10 annotated customer-service conversations covering
airline, banking, pharmacy, retail, and telecom support.

## 1. Tool-call annotations

The function-calling deliverable is the
`conversations/<conversation-id>/transcripts/annotated-transcript.json` file
inside each conversation. These files carry the function-call annotations in
the core trajectory structure from the
[Hugging Face NVIDIA Nemotron conversational tool-use dataset](https://huggingface.co/datasets/nvidia/Nemotron-RL-Agentic-Conversational-Tool-Use-Pivot-v1):

- `responses_create_params.input` contains the chronological system message,
  customer and agent messages, structured function calls, and function outputs.
- Each function call has a tool name and JSON-string arguments.
- Each function output is stored under the same `call_id` as the call.
- `event_metadata` records call placement in seconds against `audio/full.wav`,
  the inferred call window, annotation confidence, and state effect.
- `responses_create_params.tools` contains the JSON-Schema tool definitions
  used for that conversation.

Here is an exact annotation excerpt from the
[retail missing-package transcript](conversations/retail-missing-package/transcripts/annotated-transcript.json).
The call and result appear consecutively in `responses_create_params.input`:

```json
[
  {
    "arguments": "{\"product_reference\":\"blue-noise-canceling-headphones\",\"include_inventory\":true}",
    "call_id": "rm-003",
    "name": "get_product",
    "type": "function_call",
    "id": "rm-003",
    "status": "completed"
  },
  {
    "type": "function_call_output",
    "call_id": "rm-003",
    "output": "\n\n{\"product_reference\":\"blue-noise-canceling-headphones\",\"variant\":{\"color\":\"blue\"},\"inventory\":{\"same_variant_in_stock\":true}}"
  }
]
```

The matching timing annotation in `event_metadata` is:

```json
{
  "event_index": 26,
  "kind": "function_call",
  "call_id": "rm-003",
  "source": "transcripts/transcript.txt",
  "source_label": "check replacement inventory",
  "annotation_confidence": "high",
  "state_effect": "read_only",
  "placement_seconds": 211.65,
  "placement_after_text": null,
  "placement_before_text": null,
  "audio_reference": {
    "path": "audio/full.wav",
    "start_seconds": null,
    "end_seconds": null,
    "inferred_window_seconds": [
      211.65,
      219.65
    ]
  }
}
```

This sample includes the full function-result payload and call-placement
timing.

All annotated transcripts are under [conversations/](conversations/):

- Airline: [family reservation](conversations/airline-family-reservation/transcripts/annotated-transcript.json)
- Banking: [account email and card application](conversations/banking-account-email-card-application/transcripts/annotated-transcript.json), [declined card while traveling](conversations/banking-declined-card-travel/transcripts/annotated-transcript.json), [missing referral reward](conversations/banking-referral-missing-reward/transcripts/annotated-transcript.json), and [transaction dispute session](conversations/banking-transaction-dispute-session/transcripts/annotated-transcript.json)
- Pharmacy: [travel refill](conversations/pharmacy-travel-refill/transcripts/annotated-transcript.json)
- Retail: [damaged-item replacement](conversations/retail-damaged-item-replacement/transcripts/annotated-transcript.json), [missing package](conversations/retail-missing-package/transcripts/annotated-transcript.json), and [refund bank fee](conversations/retail-refund-bank-fee/transcripts/annotated-transcript.json)
- Telecom: [data-usage cleanup](conversations/telecom-data-usage-cleanup/transcripts/annotated-transcript.json)

## 2. Per-domain tool registries

The tool registry for each domain is located at
`domains/<domain>/tool_registry.json`. Each registry defines tool names,
descriptions, JSON-Schema argument contracts, and typed result contracts.

- [Airline tool registry](domains/airline/tool_registry.json)
- [Banking tool registry](domains/banking/tool_registry.json)
- [Pharmacy tool registry](domains/pharmacy/tool_registry.json)
- [Retail tool registry](domains/retail/tool_registry.json)
- [Telecom tool registry](domains/telecom/tool_registry.json)

## 3. CSR policies and reconstructed state

The policy used by each CSR is located at `domains/<domain>/policy.md` and is
also embedded in the system message of each annotated transcript.

- [Airline policy](domains/airline/policy.md)
- [Banking policy](domains/banking/policy.md)
- [Pharmacy policy](domains/pharmacy/policy.md)
- [Retail policy](domains/retail/policy.md)
- [Telecom policy](domains/telecom/policy.md)

Each conversation also has `state/initial_state.json` and
`state/final_state.json`. These are reconstructed from the annotated tool
results. They are not presented as exports from a source CRM or production
database. The [conversation manifest](conversation_manifest.json) links to
both state files for every conversation.

## 4. Required information, goals, and outcomes

Collected and read-back facts appear verbatim in the chronological speech
events in each annotated transcript. The matching `event_metadata` entries
provide start and end timestamps against the audio. The timestamped baseline
speech transcript is stored at
`conversations/<conversation-id>/transcripts/transcript.txt`.

The [conversation manifest](conversation_manifest.json) provides a one-line
goal, outcome label, outcome summary, scenario time, and file pointers for all
10 conversations. This sample does not yet include a separate normalized list
of required facts.

## 5. Turn-taking

Eight conversations include:

- `transcripts/words.json` with word-level timestamps, speaker labels, and
  confidence.
- `turn_taking.json` with turn segments, pause boundaries, backchannel and
  overlap candidates, and speaker metadata.

Airline and telecom do not include those two annotation files. Their available
paths are recorded as `null` in the
[conversation manifest](conversation_manifest.json). Accent and environment
fields are marked `not_human_annotated` rather than inferred.

## 6. Audio

All 30 delivered audio files are 48 kHz, 24-bit, mono PCM WAV files. Each
conversation includes synchronized `audio/full.wav`, `audio/speaker-1.wav`,
and `audio/speaker-2.wav` tracks.

The [audio manifest](audio_manifest.json) contains the exact audited sample
rate, bit depth, duration, channel count, and spectral measurements for every
file.

## 7. Quality review

The [data-quality document](docs/DATA_QUALITY.md) defines transcription,
speaker attribution, tool-placement, schema, policy-sync, and audio checks. It
also lists the known limitations and identifies speech that should not be
treated as a clean positive training example.

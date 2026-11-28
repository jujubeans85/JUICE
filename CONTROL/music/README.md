# JUICE Music

One music page inside JC, with the same page usable from an iPhone or iPad once the private connection is configured. The computer running ComfyUI does the generation; the phone is the controller and player.

## What this version does

- **Create:** describe a sound, optionally add lyrics, choose a maximum length, and submit one song.
- **Cover:** upload a reference recording and describe a new style. SheetSage2 transcribes the reference; YuE2 generates a new performance from that score.
- **Keep the result:** retain a lossless FLAC master, an MP3 for convenient playback, the generated or transcribed ABC score when planning is enabled, and the generation request.
- **Keep the history together:** jobs and outputs live in the existing JUICE data root, so JC and the phone see the same jobs.
- **Check the engine first:** inspect the installed ComfyUI nodes, input schemas and model names before submitting GPU work.

The interface is served by the existing `CONTROL/server.py` process at `/music/`. It adds no Python package dependencies to JC. ComfyUI and its GPU dependencies run in their own environment.

## Current delivery status

This is a reviewable source change against the repository's `main` base. It is not a statement that a pull request has been merged or that the live Mac has been changed. The active Mac checkout and process still need to be identified: earlier work used ports **8765** and **8780**. Apply the already agreed installation to that actual instance; do not create another permanent JC server to hide a port mismatch.

Keep the pending work on PRs **#3, #7 and #12** intact. Integrate this module into the selected checkout and resolve any navigation, upload or startup overlap there. Do not replace the current server or data directory wholesale with a downloaded copy.

## First use

1. Follow [SETUP_ENGINE.md](SETUP_ENGINE.md) to prepare one ComfyUI engine and connect JC to it.
2. Start the reviewed JC checkout using its existing launcher or `python3 CONTROL/server.py` from the repository root, with the correct control/data-root environment settings.
3. Open the existing JC address with `/music/` appended. With the default port, that is `http://127.0.0.1:8765/music/` on the Mac itself.
4. Check that the engine is ready. For a first run, use Create, a 60-second maximum and a short style description. Add a verse and chorus if you want specific words sung.
5. Play the resulting MP3. Keep the FLAC for editing or archiving. A score is a composition aid, not a collection of isolated instrument stems.

Phone access requires the [private HTTPS setup](SETUP_IOS.md). `127.0.0.1` on an iPhone refers to the iPhone, not the Mac. The engine does not need to be exposed directly to the phone.

## The controls mean exactly this

| Control | Meaning |
|---|---|
| Style | Genre, feel, instruments, vocal character, language and approximate tempo. Required. |
| Lyrics | Words intended to be sung; `[Verse]`, `[Chorus]` and similar section tags are useful. Optional. |
| Maximum length | A cap from 30 to 360 seconds. A song may finish earlier. |
| Full planning | Generate melody and chord information before the audio. Default for a new song. |
| Melody planning | Generate or transcribe melody while leaving more freedom to the accompaniment. A useful cover setting. |
| Direct generation | Generate without an ABC plan. Available for Create, not Cover. |
| Seed | A saved random-generation setting. Reusing it does not guarantee identical audio across different models, software versions or hardware. |

The upstream generation guide explains the distinction between score conditioning and hard waveform constraints: [YuE2 generation guide](https://github.com/multimodal-art-projection/YuE/blob/main/docs/generation.md).

### What is intentionally absent

There is no instrument-stem button, exact singer cloning control, or guaranteed instrumental switch. Empty lyrics are accepted by YuE2, but voice-like material can still appear. The official instrumental recipe also moves generated Vocal score events into the Ins part before rendering; that multi-stage transformation is not implemented here. A cover creates a fresh performance rather than preserving portions of the original recording sample for sample. These limits follow the [upstream controls and instrumental guidance](https://github.com/multimodal-art-projection/YuE/blob/main/docs/generation.md).

## One source of truth

The default `JUICE_DATA_ROOT` is `~/JUICE_DATA`. Within that root:

| Location | Purpose |
|---|---|
| `CREATIVE/MUSIC/jobs` | Durable music-job records, saved requests and returned outputs. |
| `CAPTURE/music-source` | Uploaded reference recordings. Originals stay separate from generated performances. |

The browser is not the canonical song archive. Keep the existing JUICE data backup plan covering both locations. Model checkpoints stay in ComfyUI's model directories and are not copied into each job or into the repository.

## Queue and recovery behavior

JC has one durable music queue and one worker thread in its existing server process. The browser can be closed while the server and engine keep working. A client-generated request UUID prevents a repeated submission of that same request from quietly creating a second job.

A connection can fail after ComfyUI accepted a job but before JC received the confirmation. Such ambiguous submissions are marked **`needs_attention`**, and JC does not automatically submit them again. Check the engine queue/history and the saved job record before deciding to create another generation. This prevents a network retry from becoming duplicate GPU work.

Readiness is a capability check, not a successful music-generation benchmark. The source and graph contract tests do not replace an actual generation on the chosen machine. Keep the first short run and verify playback, download, score retention, and a second consecutive job before calling the live setup validated.

## Supplied sources and provenance

| Supplied resource | How it is used |
|---|---|
| [multimodal-art-projection/YuE](https://github.com/multimodal-art-projection/YuE) | The current main branch documents YuE2. Its generation/hardware documentation defines the supported behavior and limits. Original YuE remains on the `YuE-v1` branch. |
| [Comfy-Org/YuE2](https://huggingface.co/Comfy-Org/YuE2/tree/main) | Source of the ComfyUI checkpoint and SheetSage2 encoder filenames and model placement. |
| [User-supplied yue2_full.json](https://github.com/user-attachments/files/32133499/yue2_full.json) | Retrieval was blocked with HTTP 403/DisabledError during this build. Its exact graph was not inspected or imported. |
| [Luma AI Search page](https://lumalabs.ai/aisearch-sep2) | Supplied research reference. The YuE2 adapter does not treat this web page as a callable music-generation API. |

The executable API graphs were newly authored against the official [native YuE2 node definitions](https://github.com/Comfy-Org/ComfyUI/blob/master/comfy_extras/nodes_yue2.py), [SheetSage2 nodes](https://github.com/Comfy-Org/ComfyUI/blob/master/comfy_extras/nodes_audio_encoder.py), and the official [text-to-music](https://github.com/Comfy-Org/workflow_templates/blob/main/templates/audio_yue2_text2music.json) and [cover](https://github.com/Comfy-Org/workflow_templates/blob/main/templates/audio_yue2_music_cover.json) templates. They are ComfyUI **API prompts**, not a claim to reproduce the inaccessible attachment's canvas layout or settings.

## Licenses

YuE2 repository code is Apache-2.0. Its weights use CC-BY-NC-4.0 with additional permission for personal users, musicians and content creators acting individually to generate and monetize outputs. Commercial use of the model weights by companies requires discussing a separate license with the maintainers. The additional permission does not grant rights to third-party input material. See the actual [YuE2 model license](https://github.com/multimodal-art-projection/YuE/blob/main/MODEL_LICENSE) and [Comfy model card](https://huggingface.co/Comfy-Org/YuE2).

No model weights are bundled or automatically downloaded, and no cloud GPU subscription or credits are purchased by the interface. Hardware cost, remote hosting cost and generation speed have not been measured for this installation.

## Developer checks

From the repository root:

```sh
python3 -m unittest discover -s CONTROL/tests -p 'test_music*.py' -v
```

The workflow contract tests cover invalid input, actual-duration wiring, score-conditioned covers, persistent audio outputs, safe filenames and acyclic graph structure. Validate the complete server/queue implementation with its companion tests and record a real engine run separately.

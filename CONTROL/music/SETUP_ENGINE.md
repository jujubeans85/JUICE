# Connect JUICE Music to a YuE2 engine

This guide prepares **one ComfyUI engine** for the music page already served by JC. JC remains a standard-library Python application. Install GPU libraries only in ComfyUI's own environment.

Sources and filenames were checked on **16 November 2026**. Start with a short generation; a successful connection check is not a performance or audio-quality result.

## 1. Pick where generation runs

**Recommended reference path:** a Linux machine with a BF16-capable NVIDIA GPU and 24 GB VRAM. That is the supported starting point stated by the original YuE2 Python project. ComfyUI's quantized model is a different packaging and runtime, so this is a conservative reference machine, not a measured minimum for this adapter. See [YuE2 hardware scope](https://github.com/multimodal-art-projection/YuE/blob/main/docs/hardware.md).

**Mac mini M2:** it can host JC and control a separate engine. YuE2's upstream Apple Silicon route is experimental, and the project's current hardware notes say native Mac generation acceptance remains pending. ComfyUI supporting macOS generally does not establish YuE2 speed or stability on this particular Mac. Treat local M2 generation as a trial to measure, not a promised capability.

**iPhone/iPad:** use the JC music page. They do not load the YuE2 model in this implementation.

No GPU rental price, completion time or memory ceiling is assumed here. A 3.96 GB checkpoint file does not imply that a whole generation fits in 3.96 GB of memory.

## 2. Install or update ComfyUI

### If ComfyUI already exists

Use that installation's normal update procedure. Check its location, Python environment and any local changes first. Follow the [official update guide](https://docs.comfy.org/installation/update_comfyui) for Desktop, Portable or a manual clone. Updating code without its dependencies can leave required nodes unavailable.

This integration uses built-in YuE2 nodes; it does not need a third-party YuE2 custom-node pack. The app's live schema check will identify missing nodes. Use a ComfyUI release that actually exposes those nodes rather than guessing compatibility from the app's name or age.

### New manual engine on a GPU host

Use the [official manual installation guide](https://docs.comfy.org/installation/manual_install) for your GPU and driver combination. A minimal isolated layout is:

```sh
git clone https://github.com/Comfy-Org/ComfyUI.git
cd ComfyUI
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
```

Install the **GPU-appropriate PyTorch build from the official guide** in this environment, then:

```sh
python -m pip install -r requirements.txt
python main.py --listen 127.0.0.1 --port 8188
```

Do not substitute a CUDA install command on Apple Silicon, AMD or Intel. Keep the model server on loopback; private remote connection options are below. Record the ComfyUI commit and installed packages after the first successful run so the working combination can be reproduced.

## 3. Download the model files deliberately

Open the [official Comfy-Org checkpoint directory](https://huggingface.co/Comfy-Org/YuE2/tree/main/checkpoints) and select **one** YuE2 checkpoint:

| File | Approximate download size | Place in |
|---|---:|---|
| `yue2_3b_int8_convrot.safetensors` | 3.96 GB | `ComfyUI/models/checkpoints/` |
| `yue2_3b_bf16.safetensors` | 7.8 GB | `ComfyUI/models/checkpoints/` |

The exact current BF16 filename is **`yue2_3b_bf16.safetensors`**. Do not rename it to `yue2_3b.safetensors` or confuse it with the original Python pipeline's model directory. The adapter prefers the int8 checkpoint when available, then the BF16 filename; you can select one explicitly using the environment setting below.

For covers, also download the [official audio encoder](https://huggingface.co/Comfy-Org/YuE2/tree/main/audio_encoders):

| File | Approximate download size | Place in |
|---|---:|---|
| `sheetsage2_bf16.safetensors` | 1.39 GB | `ComfyUI/models/audio_encoders/` |

Create the model directories if needed. Keep original filenames. When using ComfyUI Desktop or a shared model store, use its configured model directories; the [official extra-model-path instructions](https://docs.comfy.org/installation/manual_install#adding-extra-model-paths) explain how to reuse existing files. Do not download duplicate copies simply because JC lives in another directory.

Restart ComfyUI after adding the files. The generation checkpoint supplies model, text encoder and audio VAE through `CheckpointLoaderSimple`. There is no separate MERT2 download in this adapter. SheetSage2 is required only for the cover path.

JUICE Music never downloads these weights automatically. The first app startup will report a missing checkpoint rather than initiating a multi-gigabyte transfer.

## 4. Point the existing JC process at the engine

The implementation reads these server-side environment variables:

| Variable | Default / effect |
|---|---|
| `JUICE_MUSIC_COMFY_URL` | `http://127.0.0.1:8188`; ComfyUI's base URL. |
| `JUICE_MUSIC_CHECKPOINT` | Auto-select installed `yue2_3b_int8_convrot.safetensors`, then `yue2_3b_bf16.safetensors`. Set an exact relative model filename to override. |
| `JUICE_MUSIC_AUDIO_ENCODER` | `sheetsage2_bf16.safetensors`. |
| `JUICE_MUSIC_COMFY_TOKEN` | Optional bearer token for a private authenticated engine or gateway. |
| `JUICE_CONTROL_PORT` | Existing JC port; default 8765. Confirm whether the active setup instead uses 8780. |
| `JUICE_CONTROL_ROOT` | Existing control-code location; default `~/JUICE/CONTROL`. |
| `JUICE_DATA_ROOT` | Existing data location; default `~/JUICE_DATA`. |

Set the variables in the environment used by the actual JC launcher or service. A Finder-launched `.command` file does not automatically inherit exports made in another Terminal session.

For an explicitly chosen manual run, after changing into the **reviewed JUICE repository root**:

```sh
export JUICE_CONTROL_ROOT="$PWD/CONTROL"
export JUICE_MUSIC_COMFY_URL='http://127.0.0.1:8188'
export JUICE_MUSIC_CHECKPOINT='yue2_3b_int8_convrot.safetensors'
python3 CONTROL/server.py
```

Use the existing `JUICE_DATA_ROOT`; do not point the reviewed checkout at a new empty data folder unintentionally. If JC is already running, apply the environment change to that process's launcher and restart it through its normal method. Starting a second process with new environment variables does not reconfigure an already running instance.

### Engine on a separate machine

The adapter accepts HTTPS for a remote engine. Plain HTTP is accepted only on `localhost`, `127.0.0.1` or `::1`. Configure the final URL: redirects are rejected instead of forwarding the engine token to an unexpected destination.

One practical private option is an SSH tunnel from the JC machine to the GPU host:

```sh
ssh -N -L 18188:127.0.0.1:8188 gpu-user@gpu-host
```

Replace the example account and host with the actual GPU machine. Leave ComfyUI listening on that machine's loopback address, then set JC's engine URL to:

```sh
export JUICE_MUSIC_COMFY_URL='http://127.0.0.1:18188'
```

Alternatively, use the final HTTPS address of an authenticated private gateway. Inject its token into JC's server environment if required. Keep tokens out of committed files, browser storage, URLs, screenshots and generated project exports. Setting a bearer token in JC does not itself add authentication to an otherwise open ComfyUI server; the gateway must enforce it.

Phone-to-JC access is a separate private connection covered by the iOS deployment instructions. The phone never needs the ComfyUI token.

## 5. Run the readiness check

Open `/music/` on the selected JC instance and check the engine state. The adapter queries `/object_info` and checks the exact inputs/options of the graph it will send.

| Path | Required capabilities |
|---|---|
| Create with planning | `CheckpointLoaderSimple`, `YuE2GenerateABC`, `YuE2GenerateMusic`, `ConditioningZeroOut`, `EmptyYuE2LatentAudio`, `KSampler`, `VAEDecodeAudio`, `SaveAudio`, `SaveAudioMP3`, `PreviewAny`. |
| Create without planning | Same audio chain, without `YuE2GenerateABC` or `PreviewAny`. |
| Cover | Audio chain plus `LoadAudio`, `AudioEncoderLoader`, `SheetSage2AudioToABC`, and score text output. |

The `SaveAudio` and `SaveAudioMP3` classes are currently deprecated but remain registered in ComfyUI. Their exact schemas are verified and preflighted. If a later ComfyUI version removes or changes them, update the adapter deliberately; do not suppress the failing schema check.

Expected model names must also appear in the engine's loader options. This catches a missing file, wrong directory or renamed checkpoint before submission. Source: [ComfyUI routes](https://docs.comfy.org/development/comfyui-server/comms_routes) and the [official audio nodes](https://github.com/Comfy-Org/ComfyUI/blob/master/comfy_extras/nodes_audio.py).

## 6. Make one small proof

Use Create with a **60-second maximum**, Full planning and a short request such as:

> Soulful funk, warm expressive vocal, 104 BPM, syncopated electric bass, dry drums, Rhodes, playful brass responses, a spacious verse and a memorable chorus.

If you want specific words, provide your own short verse and chorus in the lyrics box. Avoid a long reference recording for the first cover trial. The transport limits an uploaded reference to 100 MiB; a shorter file also makes the first transcription easier to assess.

Verify the actual result:

1. The job reaches its completed state and the returned MP3 plays.
2. The FLAC downloads and decodes in an audio player.
3. Planned generation retains an ABC score and the same request/seed used for the job.
4. A second consecutive job works without restarting the engine.
5. A reference cover retains the intended melody well enough to be useful when you listen to it.

Generated seconds can be shorter than the requested maximum. BPM, meter and a score condition the performance; they are not sample-accurate timing guarantees. A full score describes vocal/instrumental melody and harmony, not an independently rendered stem for every instrument. See [YuE2 generation semantics](https://github.com/multimodal-art-projection/YuE/blob/main/docs/generation.md).

## When a job needs attention

If JC cannot establish whether ComfyUI accepted a submission, it records **`needs_attention`** and does not automatically resubmit. Inspect ComfyUI's queue and history before manually making a new job. If an accepted job is still running, let it finish and reconcile the saved output rather than spending GPU time on a duplicate.

If the engine is out of memory, use a shorter first request or a machine with adequate capacity. The presence of quantized weights is not proof that every duration fits a smaller GPU. Preserve the failed job record when comparing configurations.

## Provenance and license

This adapter is based on the official native node definitions and current official workflows, not on the user attachment that returned a retrieval error. The inaccessible attachment URL is recorded in [README.md](README.md).

The YuE2 code license and model-weight permissions differ. Personal creators have an additional grant for generating and monetizing outputs; a company commercially deploying the weights must check the separate terms. Read the [model license](https://github.com/multimodal-art-projection/YuE/blob/main/MODEL_LICENSE) before turning a personal installation into a commercial hosted service.

Installation on the live Mac remains a deployment step after identifying the actual active checkout and runtime. Nothing in this guide claims that merge, deployment or a successful GPU run has already happened.

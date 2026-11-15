"""Small, explicit ComfyUI API graphs for the native YuE2 nodes.

Schema and defaults were checked against Comfy-Org/ComfyUI on 2026-11-16.
These are API prompts, not ComfyUI canvas/workflow JSON.  The caller must
check the live /object_info response before submitting a prompt, since an
older ComfyUI install may not have these nodes or all of their inputs.

There is deliberately no fake instrumental, stem, or voice-cloning switch.
Empty lyrics are accepted by YuE2 but do not guarantee voice-free audio.
"""

from __future__ import annotations

import math
import re
import secrets
from typing import Any


DEFAULT_CHECKPOINT = "yue2_3b_int8_convrot.safetensors"
DEFAULT_AUDIO_ENCODER = "sheetsage2_bf16.safetensors"
MAX_SEED = 2**31 - 1
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z")
_REQUEST_FIELDS = {
    "task", "title", "style", "lyrics", "duration", "seed",
    "composition", "source_id",
}


def _text(raw: dict[str, Any], key: str, default: str, maximum: int) -> str:
    value = raw.get(key, default)
    if not isinstance(value, str):
        raise ValueError(f"{key} must be text.")
    if len(value) > maximum:
        raise ValueError(f"{key} must be at most {maximum} characters.")
    if "\x00" in value:
        raise ValueError(f"{key} cannot contain a null character.")
    return value.strip()


def validate_request(raw: Any) -> dict[str, Any]:
    """Validate a user request and return a new, normalized dictionary.

    The server persists this result before submitting a job.  In particular,
    a missing seed is chosen once here, then travels with the saved request.
    Numeric strings, booleans, non-finite numbers and unsupported fields are
    rejected instead of silently being coerced into a different request.
    """
    if not isinstance(raw, dict):
        raise ValueError("The music request must be a JSON object.")
    if any(not isinstance(key, str) for key in raw):
        raise ValueError("Music request field names must be text.")
    unknown = sorted(set(raw) - _REQUEST_FIELDS)
    if unknown:
        raise ValueError("Unsupported music request field: " + ", ".join(unknown))

    task = raw.get("task", "create")
    if not isinstance(task, str) or task not in {"create", "cover"}:
        raise ValueError("task must be create or cover.")
    title = _text(raw, "title", "New cover" if task == "cover" else "New song", 120)
    if not title:
        title = "New cover" if task == "cover" else "New song"
    style = _text(raw, "style", "", 4000)
    if not style:
        raise ValueError("Describe the style of music you want to make.")
    lyrics = _text(raw, "lyrics", "", 12000)

    duration = raw.get("duration", 60)
    if (
        isinstance(duration, bool)
        or not isinstance(duration, (int, float))
        or not 30 <= duration <= 360
        or not math.isfinite(duration)
    ):
        raise ValueError("duration must be a finite number from 30 to 360 seconds.")

    seed = raw.get("seed")
    if seed is None and "seed" not in raw:
        seed = secrets.randbelow(MAX_SEED + 1)
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed <= MAX_SEED:
        raise ValueError(f"seed must be an integer from 0 to {MAX_SEED}.")

    composition = raw.get("composition", "full")
    if not isinstance(composition, str) or composition not in {"full", "melody", "off"}:
        raise ValueError("composition must be full, melody or off.")
    if task == "cover" and composition == "off":
        raise ValueError("A cover needs full or melody planning to use its reference recording.")

    source_id = raw.get("source_id")
    if source_id is not None:
        if not isinstance(source_id, str) or not _IDENTIFIER.fullmatch(source_id):
            raise ValueError("source_id must be a valid uploaded-audio identifier.")
    if task == "cover" and source_id is None:
        raise ValueError("Choose a reference recording before making a cover.")
    if task == "create" and source_id is not None:
        raise ValueError("Reference recordings are used by the cover task.")

    return {
        "task": task,
        "title": title,
        "style": style,
        "lyrics": lyrics,
        "duration": duration,
        "seed": seed,
        "composition": composition,
        "source_id": source_id,
    }


def _relative_name(value: Any, label: str) -> str:
    """Keep model/upload names relative to ComfyUI's configured directories."""
    if not isinstance(value, str) or not value or len(value) > 512:
        raise ValueError(f"{label} must be a non-empty relative filename.")
    if (
        value.startswith("/")
        or "\\" in value
        or ":" in value
        or any(ord(char) < 32 for char in value)
        or any(part in {"", ".", ".."} for part in value.split("/"))
    ):
        raise ValueError(f"{label} must be a relative filename without traversal.")
    return value


def _node(class_type: str, **inputs: Any) -> dict[str, Any]:
    return {"class_type": class_type, "inputs": inputs}


def build_workflow(
    request: dict[str, Any],
    job_id: str,
    checkpoint: str,
    reference_name: str | None = None,
    audio_encoder: str = DEFAULT_AUDIO_ENCODER,
) -> dict[str, dict[str, Any]]:
    """Build a native YuE2 graph with durable FLAC, MP3 and score outputs.

    Covers transcribe the uploaded recording with SheetSage2 and generate a
    new performance conditioned on that score; they do not edit the source
    waveform in place.  Output node 8 is the FLAC master, node 10 the MP3
    preview, and node 9 the ABC score text when planning is enabled.
    """
    req = validate_request(request)
    if not isinstance(job_id, str) or not _IDENTIFIER.fullmatch(job_id):
        raise ValueError("job_id must be a safe job identifier.")
    checkpoint = _relative_name(checkpoint, "checkpoint")
    if req["task"] == "cover":
        reference_name = _relative_name(reference_name, "reference_name")
        audio_encoder = _relative_name(audio_encoder, "audio_encoder")
    elif reference_name is not None:
        raise ValueError("A reference filename is only valid for a cover.")

    seed = req["seed"]
    composition = req["composition"]
    # YuE2GenerateMusic accepts full|melody, and an empty ABC automatically
    # selects off internally.  Do not send the non-existent mode option off.
    music_mode = "full" if composition == "off" else composition
    graph = {
        "1": _node("CheckpointLoaderSimple", ckpt_name=checkpoint),
        "3": _node(
            "YuE2GenerateMusic",
            clip=["1", 1],
            style=req["style"],
            lyrics=req["lyrics"],
            abc="",
            seed=seed,
            mode=music_mode,
            max_duration=req["duration"],
            temperature=1.0,
            top_p=0.95,
            top_k=100,
            repetition_penalty=1.2,
        ),
        "4": _node("ConditioningZeroOut", conditioning=["3", 0]),
        "5": _node("EmptyYuE2LatentAudio", seconds=["3", 1], batch_size=1),
        "6": _node(
            "KSampler",
            model=["1", 0],
            positive=["3", 0],
            negative=["4", 0],
            latent_image=["5", 0],
            seed=seed,
            steps=32,
            cfg=1.0,
            sampler_name="dpm_2",
            scheduler="sgm_uniform",
            denoise=1.0,
        ),
        "7": _node("VAEDecodeAudio", samples=["6", 0], vae=["1", 2]),
        "8": _node(
            "SaveAudio", audio=["7", 0], filename_prefix=f"JUICE_Music/{job_id}/master"
        ),
        "10": _node(
            "SaveAudioMP3",
            audio=["7", 0],
            filename_prefix=f"JUICE_Music/{job_id}/preview",
            quality="320k",
        ),
    }

    if req["task"] == "cover":
        graph["11"] = _node("LoadAudio", audio=reference_name)
        graph["12"] = _node("AudioEncoderLoader", audio_encoder_name=audio_encoder)
        graph["13"] = _node(
            "SheetSage2AudioToABC", audio_encoder=["12", 0], audio=["11", 0], mode=composition
        )
        abc_link = ["13", 0]
    elif composition != "off":
        graph["2"] = _node(
            "YuE2GenerateABC",
            clip=["1", 1],
            style=req["style"],
            lyrics=req["lyrics"],
            seed=seed,
            mode=composition,
            max_abc_tokens=8192,
            temperature=0.7,
            top_p=0.9,
            top_k=30,
            repetition_penalty=1.005,
            penalty_window=100,
        )
        abc_link = ["2", 0]
    else:
        abc_link = None

    if abc_link is not None:
        graph["3"]["inputs"]["abc"] = abc_link
        graph["9"] = _node("PreviewAny", source=abc_link)
    return graph


def required_nodes(request: dict[str, Any]) -> list[str]:
    """Return the exact node classes needed for this request, derived from its graph."""
    req = validate_request(request)
    graph = build_workflow(
        req,
        "capability-check",
        DEFAULT_CHECKPOINT,
        reference_name="reference.wav" if req["task"] == "cover" else None,
    )
    return sorted({node["class_type"] for node in graph.values()})

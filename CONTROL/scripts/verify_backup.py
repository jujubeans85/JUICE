#!/usr/bin/env python3
"""Create and independently verify JUICE external-backup manifests.

Standard-library only. The manifest records relative paths, sizes, types and
SHA-256 digests; it never records source absolute paths.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import stat
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

FORMAT = "juice-backup-manifest-v1"
VOLATILE_EXACT = {
    "ADMIN/backup.lock",
    "ADMIN/last-backup.json",
    "ADMIN/last-verify.json",
}
VOLATILE_TOP_LEVEL = {"LOGS"}


@dataclass(frozen=True)
class Source:
    label: str
    path: Path


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def should_exclude(relative: Path) -> bool:
    posix = relative.as_posix()
    parts = relative.parts
    if not parts:
        return False
    if relative.name == ".DS_Store":
        return True
    if "__pycache__" in parts or relative.suffix in {".pyc", ".pyo"}:
        return True
    if parts[0] in VOLATILE_TOP_LEVEL:
        return True
    if posix in VOLATILE_EXACT:
        return True
    return False


def parse_source(raw: str) -> Source:
    if "=" not in raw:
        raise argparse.ArgumentTypeError("source must be LABEL=/absolute/path")
    label, raw_path = raw.split("=", 1)
    label = label.strip()
    if not label or "/" in label or "\\" in label or label in {".", ".."}:
        raise argparse.ArgumentTypeError(f"invalid source label: {label!r}")
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        raise argparse.ArgumentTypeError(f"source path must be absolute: {raw_path!r}")
    return Source(label=label, path=path)


def scan_tree(label: str, root: Path) -> dict[str, dict[str, Any]]:
    if not root.is_dir():
        raise FileNotFoundError(f"missing source directory: {root}")

    entries: dict[str, dict[str, Any]] = {}
    stack = [Path(".")]
    while stack:
        relative_dir = stack.pop()
        directory = root / relative_dir
        with os.scandir(directory) as iterator:
            children = sorted(iterator, key=lambda item: item.name)
        for child in children:
            relative = relative_dir / child.name
            if relative.parts and relative.parts[0] == ".":
                relative = Path(*relative.parts[1:])
            if should_exclude(relative):
                continue

            key = f"{label}/{relative.as_posix()}"
            info = child.stat(follow_symlinks=False)
            mode = stat.S_IMODE(info.st_mode)

            if child.is_symlink():
                entries[key] = {
                    "path": key,
                    "type": "symlink",
                    "target": os.readlink(child.path),
                    "mode": mode,
                }
            elif child.is_dir(follow_symlinks=False):
                entries[key] = {
                    "path": key,
                    "type": "dir",
                    "mode": mode,
                }
                stack.append(relative)
            elif child.is_file(follow_symlinks=False):
                file_path = Path(child.path)
                entries[key] = {
                    "path": key,
                    "type": "file",
                    "size": info.st_size,
                    "sha256": sha256_file(file_path),
                    "mode": mode,
                }
            else:
                entries[key] = {
                    "path": key,
                    "type": "other",
                    "mode": mode,
                }
    return entries


def scan_sources(sources: Iterable[Source]) -> dict[str, dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    seen_labels: set[str] = set()
    for source in sources:
        if source.label in seen_labels:
            raise ValueError(f"duplicate source label: {source.label}")
        seen_labels.add(source.label)
        merged.update(scan_tree(source.label, source.path))
    return merged


def scan_backup(labels: Iterable[str], backup_root: Path) -> dict[str, dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for label in labels:
        merged.update(scan_tree(label, backup_root / label))
    return merged


def compare_entries(
    expected: dict[str, dict[str, Any]],
    actual: dict[str, dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    expected_keys = set(expected)
    actual_keys = set(actual)

    for missing in sorted(expected_keys - actual_keys):
        errors.append(f"missing: {missing}")
    for extra in sorted(actual_keys - expected_keys):
        errors.append(f"unexpected: {extra}")

    for key in sorted(expected_keys & actual_keys):
        want = expected[key]
        got = actual[key]
        if want.get("type") != got.get("type"):
            errors.append(
                f"type mismatch: {key}: expected {want.get('type')}, got {got.get('type')}"
            )
            continue
        entry_type = want.get("type")
        if entry_type == "file":
            if want.get("size") != got.get("size"):
                errors.append(
                    f"size mismatch: {key}: expected {want.get('size')}, got {got.get('size')}"
                )
            if want.get("sha256") != got.get("sha256"):
                errors.append(f"hash mismatch: {key}")
        elif entry_type == "symlink":
            if want.get("target") != got.get("target"):
                errors.append(
                    f"symlink mismatch: {key}: expected {want.get('target')!r}, "
                    f"got {got.get('target')!r}"
                )
    return errors


def summary(entries: dict[str, dict[str, Any]]) -> dict[str, int]:
    files = [entry for entry in entries.values() if entry["type"] == "file"]
    return {
        "entries": len(entries),
        "files": len(files),
        "bytes": sum(int(entry.get("size", 0)) for entry in files),
    }


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    with temp.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


def load_manifest(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if payload.get("format") != FORMAT:
        raise ValueError(f"unsupported manifest format in {path}")
    entries = payload.get("entries")
    if not isinstance(entries, list):
        raise ValueError(f"manifest entries are invalid in {path}")
    return payload


def entries_from_manifest(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    labels = payload.get("labels")
    if not isinstance(labels, list) or not all(isinstance(item, str) for item in labels):
        raise ValueError("manifest labels are invalid")
    allowed_labels = set(labels)

    result: dict[str, dict[str, Any]] = {}
    for entry in payload["entries"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise ValueError("manifest contains an invalid entry")
        key = entry["path"]
        relative = Path(key)
        if (
            relative.is_absolute()
            or not relative.parts
            or relative.parts[0] not in allowed_labels
            or any(part in {"", ".", ".."} for part in relative.parts)
        ):
            raise ValueError(f"manifest contains an unsafe path: {key!r}")
        if key in result:
            raise ValueError(f"manifest contains duplicate path: {key}")
        result[key] = entry
    return result


def print_errors(errors: list[str], limit: int = 100) -> None:
    for error in errors[:limit]:
        print(f"ERROR: {error}", file=sys.stderr)
    if len(errors) > limit:
        print(f"ERROR: {len(errors) - limit} additional mismatch(es) omitted", file=sys.stderr)


def command_compare(args: argparse.Namespace) -> int:
    sources: list[Source] = args.source
    source_entries = scan_sources(sources)
    unsupported = [
        key for key, entry in source_entries.items() if entry.get("type") == "other"
    ]
    if unsupported:
        print_errors([f"unsupported special file: {key}" for key in unsupported])
        return 1
    labels = [source.label for source in sources]
    backup_entries = scan_backup(labels, args.backup_root)
    errors = compare_entries(source_entries, backup_entries)
    if errors:
        print_errors(errors)
        return 1

    manifest = {
        "format": FORMAT,
        "created_at": utc_now(),
        "labels": labels,
        "summary": summary(source_entries),
        "entries": [source_entries[key] for key in sorted(source_entries)],
    }
    write_json_atomic(args.manifest_out, manifest)
    stats = manifest["summary"]
    print(
        f"PASS compare: {stats['files']} file(s), {stats['entries']} total entries, "
        f"{stats['bytes']} byte(s)"
    )
    print(f"Manifest: {args.manifest_out}")
    return 0


def command_verify(args: argparse.Namespace) -> int:
    manifest_bytes = args.manifest.read_bytes()
    completion_path = args.manifest.parent / "COMPLETED.json"
    if completion_path.is_file():
        try:
            completion = json.loads(completion_path.read_text(encoding="utf-8"))
            expected_manifest_hash = completion.get("manifest_sha256")
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid completion marker: {completion_path}") from exc
        if expected_manifest_hash != hashlib.sha256(manifest_bytes).hexdigest():
            print("ERROR: manifest hash does not match COMPLETED.json", file=sys.stderr)
            return 1
    manifest = json.loads(manifest_bytes)
    if manifest.get("format") != FORMAT:
        raise ValueError(f"unsupported manifest format in {args.manifest}")
    expected = entries_from_manifest(manifest)
    labels = manifest.get("labels")
    if not isinstance(labels, list) or not all(isinstance(item, str) for item in labels):
        raise ValueError("manifest labels are invalid")
    actual = scan_backup(labels, args.backup_root)
    errors = compare_entries(expected, actual)
    if errors:
        print_errors(errors)
        return 1
    stats = summary(actual)
    print(
        f"PASS verify: {stats['files']} file(s), {stats['entries']} total entries, "
        f"{stats['bytes']} byte(s)"
    )
    return 0


def evenly_spaced(items: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    if count <= 0 or not items:
        return []
    if len(items) <= count:
        return items
    if count == 1:
        return [items[0]]
    indexes = {
        round(index * (len(items) - 1) / (count - 1))
        for index in range(count)
    }
    return [items[index] for index in sorted(indexes)]


def command_restore_drill(args: argparse.Namespace) -> int:
    manifest = load_manifest(args.manifest)
    entries = entries_from_manifest(manifest)
    file_entries = [entries[key] for key in sorted(entries) if entries[key]["type"] == "file"]
    samples = evenly_spaced(file_entries, args.sample_count)
    if not samples:
        print("PASS restore drill: no regular files to sample")
        return 0

    with tempfile.TemporaryDirectory(prefix="juice-restore-drill-") as temp_dir:
        restore_root = Path(temp_dir)
        for entry in samples:
            relative = Path(entry["path"])
            source = args.backup_root / relative
            destination = restore_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            restored_hash = sha256_file(destination)
            if restored_hash != entry["sha256"]:
                print(f"ERROR: restore drill hash mismatch: {entry['path']}", file=sys.stderr)
                return 1
    print(f"PASS restore drill: restored and re-hashed {len(samples)} file(s)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    compare_parser = subparsers.add_parser(
        "compare", help="compare live sources with a copied backup and create a manifest"
    )
    compare_parser.add_argument(
        "--source",
        action="append",
        required=True,
        type=parse_source,
        help="repeatable LABEL=/absolute/path source",
    )
    compare_parser.add_argument("--backup-root", required=True, type=Path)
    compare_parser.add_argument("--manifest-out", required=True, type=Path)
    compare_parser.set_defaults(func=command_compare)

    verify_parser = subparsers.add_parser(
        "verify", help="verify a backup against an existing manifest"
    )
    verify_parser.add_argument("--manifest", required=True, type=Path)
    verify_parser.add_argument("--backup-root", required=True, type=Path)
    verify_parser.set_defaults(func=command_verify)

    restore_parser = subparsers.add_parser(
        "restore-drill", help="copy a deterministic sample out and re-hash it"
    )
    restore_parser.add_argument("--manifest", required=True, type=Path)
    restore_parser.add_argument("--backup-root", required=True, type=Path)
    restore_parser.add_argument("--sample-count", type=int, default=25)
    restore_parser.set_defaults(func=command_restore_drill)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

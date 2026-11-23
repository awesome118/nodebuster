#!/usr/bin/env python3
"""Validate the files required by the Nodebuster Godot web export."""

from __future__ import annotations

import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACK_PATH = ROOT / "Nodebuster.pck"
WASM_PATH = ROOT / "Nodebuster.wasm"
HTML_PATH = ROOT / "index.html"


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def read_u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def validate_pack(data: bytes) -> None:
    # Godot 4.2.x writes PCK format v2. Its standalone header is 96 bytes,
    # followed by a 32-bit directory-entry count.
    if len(data) < 100:
        fail(f"{PACK_PATH.name} is only {len(data)} bytes; the PCK header is incomplete")
    if data[:4] != b"GDPC":
        fail(f"{PACK_PATH.name} does not start with the Godot PCK signature (GDPC)")

    version = read_u32(data, 4)
    engine_major = read_u32(data, 8)
    engine_minor = read_u32(data, 12)
    engine_patch = read_u32(data, 16)
    flags = read_u32(data, 20)
    file_base = struct.unpack_from("<Q", data, 24)[0]

    if version != 2:
        fail(f"{PACK_PATH.name} uses PCK format {version}; this bundled Godot 4.2 loader expects format 2")
    if engine_major != 4 or engine_minor > 2:
        fail(
            f"{PACK_PATH.name} was exported by Godot {engine_major}.{engine_minor}.{engine_patch}; "
            "this repository bundles the Godot 4.2 web loader"
        )
    if flags & ~0x7:
        fail(f"{PACK_PATH.name} contains unsupported PCK flags 0x{flags:08x}")

    if file_base > len(data):
        fail(
            f"{PACK_PATH.name} has an invalid file-base offset ({file_base:,}), "
            f"past the end of the {len(data):,}-byte pack. The binary is corrupted or was text-encoded."
        )

    directory_offset = 96
    file_count = read_u32(data, directory_offset)
    directory_bytes = len(data) - directory_offset - 4
    # A v2 directory entry needs at least a four-byte path length, a minimally
    # padded path, two uint64 values, a 16-byte MD5, and a uint32 flags field.
    minimum_entry_bytes = 40
    maximum_entries = min(1_000_000, directory_bytes // minimum_entry_bytes)
    if file_count == 0 or file_count > maximum_entries:
        fail(
            f"{PACK_PATH.name} declares {file_count:,} directory entries, but its "
            f"{directory_bytes:,}-byte directory can hold at most {maximum_entries:,}. "
            "The PCK is incomplete or corrupted."
        )


def validate_size_declaration(html: str, filename: str, actual_size: int) -> None:
    match = re.search(rf'["\\']{re.escape(filename)}["\\']\\s*:\\s*(\\d+)', html)
    if not match:
        fail(f"index.html does not declare the download size for {filename}")
    declared_size = int(match.group(1))
    if declared_size != actual_size:
        fail(
            f"index.html declares {filename} as {declared_size:,} bytes, "
            f"but the file is {actual_size:,} bytes"
        )


def main() -> None:
    required_files = (
        PACK_PATH,
        WASM_PATH,
        HTML_PATH,
        ROOT / "Nodebuster.js",
        ROOT / "Nodebuster.worker.js",
        ROOT / "Nodebuster.audio.worklet.js",
    )
    for path in required_files:
        if not path.is_file() or path.stat().st_size == 0:
            fail(f"required export file is missing or empty: {path.name}")

    pack = PACK_PATH.read_bytes()
    wasm = WASM_PATH.read_bytes()
    html = HTML_PATH.read_text(encoding="utf-8")

    validate_pack(pack)
    if not wasm.startswith(b"\\x00asm"):
        fail(f"{WASM_PATH.name} does not have the WebAssembly binary signature")

    validate_size_declaration(html, PACK_PATH.name, len(pack))
    validate_size_declaration(html, WASM_PATH.name, len(wasm))

    print(
        f"Validated Godot {read_u32(pack, 8)}.{read_u32(pack, 12)}.{read_u32(pack, 16)} "
        f"PCK ({len(pack):,} bytes) and WebAssembly module ({len(wasm):,} bytes)."
    )


if __name__ == "__main__":
    main()

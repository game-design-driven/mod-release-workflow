#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Validate and optionally export mods.toml [mc-publish] metadata."""

from __future__ import annotations

import argparse
import os
import sys
import tomllib
from pathlib import Path
from typing import NoReturn, cast

REQUIRED_KEYS = [
    "modrinth",
    "curseforge",
    "loader",
    "mc_version",
    "modrinth_slug",
    "curseforge_slug",
]
ALLOWED_LOADERS = {"forge"}


def fail(message: str) -> NoReturn:
    print(f"ERROR: {message}", file=sys.stderr)
    sys.exit(1)


def find_mods_toml(root: Path) -> Path:
    paths = [path for path in root.rglob("mods.toml") if path.is_file() and "build" not in path.parts]
    if not paths:
        fail("No mods.toml found. Expected a single mods.toml with a [mc-publish] table containing required keys.")
    if len(paths) > 1:
        listed = "\n".join(str(path) for path in paths)
        fail(f"Multiple mods.toml files found; expected exactly one:\n{listed}")
    return paths[0]


def normalize_value(value: object | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped if stripped else None
    return str(value)


def read_metadata(mods_toml: Path) -> dict[str, str]:
    try:
        data = tomllib.loads(mods_toml.read_text())
    except tomllib.TOMLDecodeError as exc:
        fail(f"Invalid TOML in {mods_toml}: {exc}")

    metadata = data.get("mc-publish")
    if metadata is None:
        fail(f"Missing [mc-publish] table in {mods_toml}")
    if not isinstance(metadata, dict):
        fail(f"Missing [mc-publish] table in {mods_toml}")

    metadata_dict = cast(dict[str, object], metadata)

    missing: list[str] = []
    values: dict[str, str] = {}
    for key in REQUIRED_KEYS:
        value = normalize_value(metadata_dict.get(key))
        if value is None:
            missing.append(key)
            continue
        values[key] = value

    if missing:
        missing_list = ", ".join(f"[mc-publish].{key}" for key in missing)
        fail(f"Missing required keys in {mods_toml}: {missing_list}")

    loader = values["loader"]
    if loader not in ALLOWED_LOADERS:
        allowed_list = ", ".join(sorted(ALLOWED_LOADERS))
        fail(f"[mc-publish].loader must be one of: {allowed_list}. Found: {loader}")

    return values


def write_outputs(values: dict[str, str]) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        fail("GITHUB_OUTPUT is not set; cannot write outputs.")
    with Path(output_path).open("a") as output:
        output.write(f"modrinth_id={values['modrinth']}\n")
        output.write(f"curseforge_id={values['curseforge']}\n")
        output.write(f"loader={values['loader']}\n")
        output.write(f"mc_version={values['mc_version']}\n")
        output.write(f"modrinth_slug={values['modrinth_slug']}\n")
        output.write(f"curseforge_slug={values['curseforge_slug']}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write-outputs",
        action="store_true",
        help="Write parsed values to GITHUB_OUTPUT.",
    )
    args = parser.parse_args()

    mods_toml = find_mods_toml(Path("."))
    values = read_metadata(mods_toml)
    print(f"Validated mods.toml at {mods_toml}")

    if args.write_outputs:
        write_outputs(values)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

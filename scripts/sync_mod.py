#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx"]
# ///
"""Sync a mod to a packwiz modpack - add or update with version polling."""

import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

MAX_RETRIES = 20
RETRY_INTERVAL = 60


def log(msg: str) -> None:
    print(f"[sync] {msg}", flush=True)


def run_packwiz(cmd: list[str], cwd: Path) -> tuple[bool, str]:
    """Run packwiz command, return (success, output)."""
    try:
        result = subprocess.run(
            ["packwiz"] + cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        output = result.stdout + result.stderr
        return result.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, "Command timed out"
    except Exception as e:
        return False, str(e)


def has_git_changes(cwd: Path) -> bool:
    """Check if there are uncommitted changes."""
    result = subprocess.run(
        ["git", "diff", "--quiet", "."],
        cwd=cwd,
        capture_output=True,
    )
    return result.returncode != 0


def mod_exists_in_pack(mod_slug: str, pack_dir: Path) -> bool:
    """Check if mod exists in pack by looking for its .pw.toml file."""
    mods_dir = pack_dir / "mods"
    if not mods_dir.exists():
        return False
    for toml_file in mods_dir.glob("*.pw.toml"):
        content = toml_file.read_text()
        # packwiz format: slug = "mod-slug"
        if f'slug = "{mod_slug}"' in content:
            return True
    return False


def check_modrinth_version(slug: str, version: str, mc_version: str, loader: str) -> bool:
    """Check if version exists on Modrinth."""
    try:
        resp = httpx.get(
            f"https://api.modrinth.com/v2/project/{slug}/version",
            params={"loaders": f'["{loader}"]', "game_versions": f'["{mc_version}"]'},
            timeout=10,
        )
        if resp.status_code == 200:
            versions = resp.json()
            return any(version in v.get("version_number", "") for v in versions)
    except Exception:
        pass
    return False


def sync_mod(
    pack_dir: Path,
    mod_slug: str,
    platform: str,
    version: str,
    mc_version: str,
    loader: str,
) -> bool:
    """Sync mod to pack. Returns True on success."""
    exists = mod_exists_in_pack(mod_slug, pack_dir)
    action = "update" if exists else "add"

    log(f"{'Updating' if exists else 'Adding'} {mod_slug} via {platform}")

    # Write action for PR title
    github_output = Path(os.environ.get("GITHUB_OUTPUT", "/dev/null"))
    with open(github_output, "a") as f:
        f.write(f"action={action}\n")

    for attempt in range(1, MAX_RETRIES + 1):
        # For modrinth, check API first to avoid unnecessary packwiz calls
        if platform == "mr" and attempt > 1 and not check_modrinth_version(mod_slug, version, mc_version, loader):
            log(f"Attempt {attempt}/{MAX_RETRIES}: Version not on Modrinth yet, waiting {RETRY_INTERVAL}s...")
            time.sleep(RETRY_INTERVAL)
            continue

        # Run packwiz
        cmd = [platform, "add", mod_slug, "-y"] if action == "add" else ["update", mod_slug]

        success, output = run_packwiz(cmd, pack_dir)

        if not success:
            # Check if it's a "not found" error vs other error
            if "could not find" in output.lower() or "no results" in output.lower():
                log(f"Attempt {attempt}/{MAX_RETRIES}: Mod/version not found yet, waiting {RETRY_INTERVAL}s...")
                time.sleep(RETRY_INTERVAL)
                continue
            else:
                log(f"Packwiz error: {output}")
                # Still retry - might be transient
                time.sleep(RETRY_INTERVAL)
                continue

        # Check if changes were made
        if has_git_changes(pack_dir):
            log(f"Success: {action} completed for {mod_slug}")
            return True

        log(f"Attempt {attempt}/{MAX_RETRIES}: No changes detected, waiting {RETRY_INTERVAL}s...")
        time.sleep(RETRY_INTERVAL)

    log(f"Error: Timed out after {MAX_RETRIES * RETRY_INTERVAL // 60} minutes")
    return False


def main() -> int:
    if len(sys.argv) < 7:
        print("Usage: sync_mod.py <pack_dir> <mod_slug> <platform> <version> <mc_version> <loader>")
        return 1

    pack_dir = Path(sys.argv[1])
    mod_slug = sys.argv[2]
    platform = sys.argv[3]  # "mr" or "cf"
    version = sys.argv[4]
    mc_version = sys.argv[5]
    loader = sys.argv[6]

    if not pack_dir.exists():
        log(f"Error: Pack directory {pack_dir} does not exist")
        return 1

    success = sync_mod(pack_dir, mod_slug, platform, version, mc_version, loader)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())

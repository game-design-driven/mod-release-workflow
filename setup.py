#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pyfzf>=0.3.1",
# ]
# ///
"""
Setup script for mod-release-workflow.
Configures repository variables and secrets for the reusable workflow.

Usage:
    cd /path/to/your-mod-repo
    uv run /path/to/mod-release-workflow/setup.py
"""

import json
import os
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

from pyfzf.pyfzf import FzfPrompt


@dataclass
class ConfigItem:
    name: str
    description: str
    is_secret: bool = False
    required: bool = False
    default: str = ""


ALLOWED_LOADERS = {"forge"}


class SetupCancelled(Exception):
    pass


VARIABLES: list[ConfigItem] = [
    ConfigItem("TARGET_MODPACK_REPO", "Downstream modpack repo (org/repo format)"),
    ConfigItem("ENABLE_MODRINTH_SYNC", "Enable Modrinth modpack sync (true/false)", default="false"),
    ConfigItem("ENABLE_CURSEFORGE_SYNC", "Enable CurseForge modpack sync (true/false)", default="false"),
]

SECRETS: list[ConfigItem] = [
    ConfigItem("GH_TOKEN", "GitHub PAT with repo access", is_secret=True, required=True),
    ConfigItem("MODRINTH_TOKEN", "Modrinth API token", is_secret=True, required=True),
    ConfigItem("CURSEFORGE_TOKEN", "CurseForge API token", is_secret=True, required=True),
]


def build_file_items(repo_name: str) -> list[ConfigItem]:
    default_slug = repo_name.lower()
    return [
        ConfigItem("modrinth", "Modrinth project ID", required=True),
        ConfigItem("curseforge", "CurseForge project ID", required=True),
        ConfigItem("loader", "Mod loader (forge only)", required=True, default="forge"),
        ConfigItem("mc_version", "Minecraft version", required=True),
        ConfigItem(
            "modrinth_slug",
            "Modrinth slug for packwiz add/update (defaults to repo name lowercase)",
            required=True,
            default=default_slug,
        ),
        ConfigItem(
            "curseforge_slug",
            "CurseForge slug for packwiz add/update (defaults to repo name lowercase)",
            required=True,
            default=default_slug,
        ),
    ]


def run_cmd(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k != "GITHUB_TOKEN"}
    return subprocess.run(cmd, capture_output=True, text=True, check=check, env=env)


def find_mods_toml() -> Path:
    paths = [path for path in Path(".").rglob("mods.toml") if path.is_file() and "build" not in path.parts]
    if not paths:
        sys.exit("ERROR: No mods.toml found. Expected a single mods.toml with a [mc-publish] table.")
    if len(paths) > 1:
        listed = "\n".join(str(path) for path in paths)
        sys.exit(f"ERROR: Multiple mods.toml files found; expected exactly one:\n{listed}")
    return paths[0]


def read_mc_publish_table(mods_toml: Path) -> dict[str, str]:
    try:
        block_text = extract_mc_publish_block(mods_toml.read_text())
        if block_text is None:
            return {}
        data = tomllib.loads(block_text)
    except tomllib.TOMLDecodeError as exc:
        sys.exit(f"ERROR: Invalid TOML in {mods_toml}: {exc}")
    table = data.get("mc-publish")
    if table is None:
        return {}
    if not isinstance(table, dict):
        sys.exit(f"ERROR: [mc-publish] table is not a table in {mods_toml}")
    return {key: str(value) for key, value in table.items()}


def validate_file_value(name: str, value: str) -> tuple[bool, str]:
    if not value.strip():
        return False, "value cannot be empty"
    if "${" in value:
        return False, "value contains a template placeholder"
    if name == "loader" and value not in ALLOWED_LOADERS:
        allowed_list = ", ".join(sorted(ALLOWED_LOADERS))
        return False, f"loader must be one of: {allowed_list}"
    return True, ""


def format_toml_value(name: str, value: str) -> str:
    if name == "curseforge" and value.isdigit():
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def strip_inline_comment(line: str) -> str:
    return line.split("#", 1)[0].strip()


def is_table_header(line: str) -> bool:
    stripped = strip_inline_comment(line)
    return stripped.startswith("[") and stripped.endswith("]")


def is_mc_publish_header(line: str) -> bool:
    stripped = strip_inline_comment(line)
    return stripped.startswith("[mc-publish") or stripped.startswith("[[mc-publish")


def extract_mc_publish_block(text: str) -> str | None:
    lines = text.splitlines()
    header_indices = [index for index, line in enumerate(lines) if strip_inline_comment(line) == "[mc-publish]"]
    if not header_indices:
        return None
    if len(header_indices) > 1:
        sys.exit("ERROR: Multiple [mc-publish] tables found in mods.toml")

    start_index = header_indices[0]
    end_index = len(lines)
    for index in range(start_index + 1, len(lines)):
        if is_table_header(lines[index]) and not is_mc_publish_header(lines[index]):
            end_index = index
            break

    block_lines = lines[start_index:end_index]
    return "\n".join(block_lines) + "\n"


def build_mc_publish_block(values: dict[str, str], ordered_keys: list[str]) -> list[str]:
    lines = ["[mc-publish]"]
    for key in ordered_keys:
        lines.append(f"{key} = {format_toml_value(key, values[key])}")
    return lines


def update_mc_publish_block(mods_toml: Path, values: dict[str, str], ordered_keys: list[str]) -> bool:
    text = mods_toml.read_text()
    lines = text.splitlines()
    start_index: int | None = None
    for index, line in enumerate(lines):
        if strip_inline_comment(line) == "[mc-publish]":
            start_index = index
            break

    if start_index is not None:
        end_index = len(lines)
        for index in range(start_index + 1, len(lines)):
            if is_table_header(lines[index]) and not is_mc_publish_header(lines[index]):
                end_index = index
                break
        block_lines = lines[start_index + 1 : end_index]
        key_indices: dict[str, int] = {}
        for index, line in enumerate(block_lines):
            stripped = strip_inline_comment(line)
            if "=" not in stripped:
                continue
            key = stripped.split("=", 1)[0].strip()
            if key in values and key not in key_indices:
                key_indices[key] = index

        for key in ordered_keys:
            new_line = f"{key} = {format_toml_value(key, values[key])}"
            if key in key_indices:
                block_lines[key_indices[key]] = new_line
            else:
                block_lines.append(new_line)

        new_lines = lines[: start_index + 1] + block_lines + lines[end_index:]
    else:
        new_block = build_mc_publish_block(values, ordered_keys)
        new_lines = lines[:]
        if new_lines and new_lines[-1].strip():
            new_lines.append("")
        new_lines.extend(new_block)

    new_text = "\n".join(new_lines) + "\n"
    if new_text != text:
        mods_toml.write_text(new_text)
        return True
    return False


def require_tools() -> None:
    """Crash if required tools are missing."""
    try:
        run_cmd(["gh", "--version"])
    except (subprocess.CalledProcessError, FileNotFoundError):
        sys.exit("ERROR: gh CLI required. Install from https://cli.github.com/")

    try:
        run_cmd(["fzf", "--version"])
    except (subprocess.CalledProcessError, FileNotFoundError):
        sys.exit("ERROR: fzf required. Install with: brew install fzf")


def get_repo_info() -> tuple[str, str]:
    """Get current repo's org/repo from git remote."""
    result = run_cmd(["gh", "repo", "view", "--json", "owner,name"], check=False)
    if result.returncode != 0:
        sys.exit("ERROR: Not in a GitHub repository or gh not authenticated.\nRun 'gh auth login' first.")
    data = json.loads(result.stdout)
    return data["owner"]["login"], data["name"]


class ExistingValues:
    """Cache of existing secrets/variables fetched once at startup."""

    def __init__(self, org: str, repo: str):
        self.repo_secrets: set[str] = set()
        self.org_secrets: set[str] = set()
        self.repo_vars: dict[str, str] = {}
        self.org_vars: dict[str, str] = {}
        self._fetch_all(org, repo)

    def _fetch_all(self, org: str, repo: str) -> None:
        def safe_json(result: subprocess.CompletedProcess[str], key: str | None = None) -> list:
            if result.returncode != 0:
                return []
            try:
                data = json.loads(result.stdout)
                return data[key] if key else data
            except (json.JSONDecodeError, KeyError):
                return []

        self.repo_secrets = {
            s["name"] for s in safe_json(run_cmd(["gh", "secret", "list", "--json", "name"], check=False))
        }
        self.repo_vars = {
            v["name"]: v["value"]
            for v in safe_json(run_cmd(["gh", "variable", "list", "--json", "name,value"], check=False))
        }

        # Org secrets/vars available to this repo (doesn't require admin:org scope)
        self.org_secrets = {
            s["name"]
            for s in safe_json(
                run_cmd(["gh", "api", f"repos/{org}/{repo}/actions/organization-secrets"], check=False), "secrets"
            )
        }
        self.org_vars = {
            v["name"]: v["value"]
            for v in safe_json(
                run_cmd(["gh", "api", f"repos/{org}/{repo}/actions/organization-variables"], check=False), "variables"
            )
        }

    def get(self, name: str, is_secret: bool) -> tuple[str | None, str | None]:
        """Returns (repo_value, org_value)."""
        if is_secret:
            repo = "***" if name in self.repo_secrets else None
            org = "***" if name in self.org_secrets else None
        else:
            repo = self.repo_vars.get(name)
            org = self.org_vars.get(name)
        return repo, org


def set_value(name: str, value: str, is_secret: bool, at_org: bool, org: str) -> bool:
    """Set a variable or secret."""
    try:
        if is_secret:
            cmd = ["gh", "secret", "set", name, "--body", value]
            if at_org:
                cmd.extend(["--org", org])
        else:
            cmd = ["gh", "variable", "set", name, "--body", value]
            if at_org:
                cmd.extend(["--org", org])
        run_cmd(cmd)
        return True
    except subprocess.CalledProcessError:
        return False


def fzf_select(prompt: str, options: list[str]) -> str | None:
    """Use fzf for selection."""
    fzf = FzfPrompt()
    args = f"--prompt='{prompt}: ' --height=40% --reverse"
    try:
        result = fzf.prompt(options, args)
    except KeyboardInterrupt as exc:
        raise SetupCancelled from exc
    if not result:
        raise SetupCancelled
    return result[0]


def configure_file_item(item: ConfigItem, existing_values: dict[str, str], actions: list[str]) -> str | None:
    """Configure a single mods.toml [mc-publish] entry."""
    existing_value = existing_values.get(item.name)
    if existing_value is not None:
        is_valid, reason = validate_file_value(item.name, existing_value)
        if not is_valid:
            print(f"WARNING: [mc-publish].{item.name} is invalid ({reason}); it will be replaced.")
            existing_value = None

    while True:
        options: list[str] = []
        options.append("Set value")
        if existing_value is not None:
            options.append(f"Use existing (file: {existing_value})")
        elif not item.required:
            options.append("Skip")

        choice = fzf_select(item.name, options)

        if not choice or choice == "Skip":
            if item.required:
                print(f"ERROR: {item.name} is required")
                continue
            actions.append(f"{item.name}: skipped")
            return None

        if choice.startswith("Use existing"):
            actions.append(f"{item.name}: using existing (mods.toml)")
            return existing_value

        prompt = f"Enter value [{item.default}]: " if item.default else "Enter value: "
        value = input(prompt).strip() or item.default

        if not value:
            if item.required:
                print(f"ERROR: {item.name} is required")
                continue
            actions.append(f"{item.name}: skipped")
            return None

        is_valid, reason = validate_file_value(item.name, value)
        if not is_valid:
            print(f"ERROR: {reason}")
            continue

        actions.append(f"{item.name}: set in mods.toml")
        return value


def configure_item(item: ConfigItem, org: str, cache: ExistingValues, actions: list[str]) -> None:
    """Configure a single variable or secret."""
    print(f"\n{'=' * 50}")
    print(f"{item.name}: {item.description}")
    if item.required:
        print("(REQUIRED)")

    repo_value, org_value = cache.get(item.name, item.is_secret)
    existing_scope = "repo" if repo_value else "org" if org_value else None
    existing_display = repo_value or org_value

    while True:
        # Build options
        options: list[str] = []
        options.append("Set repo value")
        options.append("Set org value")

        if existing_display:
            options.append(f"Use existing ({existing_scope}: {existing_display})")
        elif not item.required:
            options.append("Skip")

        choice = fzf_select(item.name, options)

        if not choice or choice == "Skip":
            if item.required:
                print(f"ERROR: {item.name} is required")
                continue
            print("Skipped")
            return

        if choice.startswith("Use existing"):
            print("Using existing value")
            actions.append(f"{item.name}: using existing ({existing_scope})")
            return

        at_org = "org" in choice

        # Get new value
        prompt = f"Enter value [{item.default}]: " if item.default else "Enter value: "

        if item.is_secret:
            import getpass

            value = getpass.getpass(prompt)
        else:
            value = input(prompt)

        value = value.strip() or item.default

        if not value:
            if item.required:
                print(f"ERROR: {item.name} is required")
                continue
            print("Skipped (no value)")
            return

        if set_value(item.name, value, item.is_secret, at_org, org):
            scope = "org" if at_org else "repo"
            print(f"Set {item.name} at {scope} level")
            actions.append(f"{item.name}: set at {scope} level")
            return

        print(f"ERROR: Failed to set {item.name}")
        if not item.required:
            return


def check_workflow_file() -> None:
    """Check if the caller workflow exists."""
    workflows_dir = Path(".github/workflows")
    if workflows_dir.exists():
        for ext in ("*.yaml", "*.yml"):
            for wf in workflows_dir.glob(ext):
                if "mod-release-workflow" in wf.read_text():
                    print(f"Found workflow: {wf}")
                    return

    print("\nWARNING: No mod-release-workflow found in .github/workflows/")
    print("Copy caller-template.yaml first")


def main() -> int:
    try:
        print("=" * 50)
        print("Mod Release Workflow Setup")
        print("=" * 50)

        require_tools()

        org, repo = get_repo_info()
        print(f"\nRepository: {org}/{repo}")

        check_workflow_file()

        mods_toml = find_mods_toml()
        existing_mc_publish = read_mc_publish_table(mods_toml)
        file_items = build_file_items(repo)

        print(f"\nFound mods.toml: {mods_toml}")
        print("\nConfiguring mods.toml [mc-publish] metadata...")

        actions: list[str] = []
        file_values: dict[str, str] = {}
        for item in file_items:
            value = configure_file_item(item, existing_mc_publish, actions)
            if value is not None:
                file_values[item.name] = value

        missing_required = [item.name for item in file_items if item.required and item.name not in file_values]
        if missing_required:
            missing_list = ", ".join(missing_required)
            sys.exit(f"ERROR: Missing required mods.toml values: {missing_list}")

        ordered_keys = [item.name for item in file_items]
        updated = update_mc_publish_block(mods_toml, file_values, ordered_keys)
        if updated:
            actions.append(f"mods.toml: updated [mc-publish] ({mods_toml})")

        print("\nFetching existing values...")
        cache = ExistingValues(org, repo)
        for item in VARIABLES + SECRETS:
            configure_item(item, org, cache, actions)

        print("\n" + "=" * 50)
        print("Setup complete!")
        print("=" * 50)

        if actions:
            print("\nSummary:")
            for action in actions:
                print(f"  - {action}")
        else:
            print("\nNo changes made.")

        return 0
    except (SetupCancelled, KeyboardInterrupt, EOFError):
        print("\nCancelled.")
        return 130


if __name__ == "__main__":
    sys.exit(main())

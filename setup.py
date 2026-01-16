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


VARIABLES: list[ConfigItem] = [
    ConfigItem("MODRINTH_ID", "Modrinth project ID"),
    ConfigItem("CF_ID", "CurseForge project ID"),
    ConfigItem("ENABLE_MODRINTH_SYNC", "Enable Modrinth modpack sync (true/false)", default="false"),
    ConfigItem("ENABLE_CURSEFORGE_SYNC", "Enable CurseForge modpack sync (true/false)", default="false"),
]

SECRETS: list[ConfigItem] = [
    ConfigItem("GH_TOKEN", "GitHub PAT with repo access", is_secret=True, required=True),
    ConfigItem("MODRINTH_TOKEN", "Modrinth API token", is_secret=True),
    ConfigItem("CURSEFORGE_TOKEN", "CurseForge API token", is_secret=True),
]


def run_cmd(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k != "GITHUB_TOKEN"}
    return subprocess.run(cmd, capture_output=True, text=True, check=check, env=env)


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
    result = fzf.prompt(options, args)
    return result[0] if result else None


def configure_item(item: ConfigItem, org: str, cache: ExistingValues, actions: list[str]) -> None:
    """Configure a single variable or secret."""
    print(f"\n{'=' * 50}")
    print(f"{item.name}: {item.description}")
    if item.required:
        print("(REQUIRED)")

    repo_value, org_value = cache.get(item.name, item.is_secret)
    existing_scope = "repo" if repo_value else "org" if org_value else None
    existing_display = repo_value or org_value

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
        else:
            print("Skipped (no value)")
        return

    if set_value(item.name, value, item.is_secret, at_org, org):
        scope = "org" if at_org else "repo"
        print(f"Set {item.name} at {scope} level")
        actions.append(f"{item.name}: set at {scope} level")
    else:
        print(f"ERROR: Failed to set {item.name}")


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
    print("=" * 50)
    print("Mod Release Workflow Setup")
    print("=" * 50)

    require_tools()

    org, repo = get_repo_info()
    print(f"\nRepository: {org}/{repo}")

    check_workflow_file()

    print("\nFetching existing values...")
    cache = ExistingValues(org, repo)

    actions: list[str] = []
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


if __name__ == "__main__":
    sys.exit(main())

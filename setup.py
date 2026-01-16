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
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from pyfzf.pyfzf import FzfPrompt


class Scope(Enum):
    REPO = "repo"
    ORG = "org"


@dataclass
class ConfigItem:
    name: str
    description: str
    is_secret: bool = False
    required: bool = False
    default: str = ""


VARIABLES: list[ConfigItem] = [
    ConfigItem("MODRINTH_ID", "Modrinth project ID", required=False),
    ConfigItem("CF_ID", "CurseForge project ID", required=False),
    ConfigItem("ENABLE_MODRINTH_SYNC", "Enable Modrinth modpack sync (true/false)", default="false"),
    ConfigItem("ENABLE_CURSEFORGE_SYNC", "Enable CurseForge modpack sync (true/false)", default="false"),
]

SECRETS: list[ConfigItem] = [
    ConfigItem("GH_TOKEN", "GitHub PAT with repo access", is_secret=True, required=True),
    ConfigItem("MODRINTH_TOKEN", "Modrinth API token", is_secret=True),
    ConfigItem("CURSEFORGE_TOKEN", "CurseForge API token", is_secret=True),
]


def run_cmd(cmd: list[str], capture: bool = True, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=capture, text=True, check=check)


def gh_available() -> bool:
    try:
        run_cmd(["gh", "--version"])
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def fzf_available() -> bool:
    try:
        run_cmd(["fzf", "--version"])
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def get_repo_info() -> tuple[str, str] | None:
    """Get current repo's org/repo from git remote."""
    try:
        result = run_cmd(["gh", "repo", "view", "--json", "owner,name"])
        data = json.loads(result.stdout)
        return data["owner"]["login"], data["name"]
    except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError):
        return None


def get_org_name() -> str | None:
    """Get org name from repo info."""
    info = get_repo_info()
    return info[0] if info else None


def get_existing_value(name: str, is_secret: bool, scope: Scope, org: str | None) -> str | None:
    """Check if a variable/secret already exists at the given scope."""
    try:
        if is_secret:
            if scope == Scope.ORG and org:
                result = run_cmd(["gh", "secret", "list", "--org", org, "--json", "name"], check=False)
            else:
                result = run_cmd(["gh", "secret", "list", "--json", "name"], check=False)

            if result.returncode != 0:
                return None
            secrets = json.loads(result.stdout)
            return "[SET]" if any(s["name"] == name for s in secrets) else None
        else:
            if scope == Scope.ORG and org:
                result = run_cmd(["gh", "variable", "list", "--org", org, "--json", "name,value"], check=False)
            else:
                result = run_cmd(["gh", "variable", "list", "--json", "name,value"], check=False)

            if result.returncode != 0:
                return None
            variables = json.loads(result.stdout)
            for v in variables:
                if v["name"] == name:
                    return v["value"]
            return None
    except (json.JSONDecodeError, KeyError):
        return None


def set_value(name: str, value: str, is_secret: bool, scope: Scope, org: str | None) -> bool:
    """Set a variable or secret at the given scope."""
    try:
        if is_secret:
            if scope == Scope.ORG and org:
                cmd = ["gh", "secret", "set", name, "--org", org, "--body", value]
            else:
                cmd = ["gh", "secret", "set", name, "--body", value]
        else:
            if scope == Scope.ORG and org:
                cmd = ["gh", "variable", "set", name, "--org", org, "--body", value]
            else:
                cmd = ["gh", "variable", "set", name, "--body", value]

        run_cmd(cmd)
        return True
    except subprocess.CalledProcessError:
        return False


def fzf_select(prompt: str, options: list[str]) -> str | None:
    """Use fzf for single selection."""
    fzf = FzfPrompt()
    try:
        args = ["--prompt", f"{prompt}: ", "--height", "40%", "--reverse"]
        result = fzf.prompt(options, " ".join(args))
        return result[0] if result else None
    except Exception:
        return None


def input_value(prompt: str, default: str = "", secret: bool = False) -> str:
    """Get input from user, with optional default."""
    if default:
        display = f"{prompt} [{default}]: "
    else:
        display = f"{prompt}: "

    if secret:
        import getpass
        value = getpass.getpass(display)
    else:
        value = input(display)

    return value.strip() if value.strip() else default


def configure_item(item: ConfigItem, org: str | None, fzf: FzfPrompt | None) -> None:
    """Configure a single variable or secret."""
    print(f"\n{'=' * 50}")
    print(f"Configuring: {item.name}")
    print(f"Description: {item.description}")
    if item.required:
        print("Status: REQUIRED")

    # Check existing values at both scopes
    repo_value = get_existing_value(item.name, item.is_secret, Scope.REPO, org)
    org_value = get_existing_value(item.name, item.is_secret, Scope.ORG, org) if org else None

    # Build options
    options: list[str] = []

    if repo_value:
        display = "[SET]" if item.is_secret else repo_value
        options.append(f"Use repo value: {display}")
    if org_value:
        display = "[SET]" if item.is_secret else org_value
        options.append(f"Use org value: {display}")
    options.append("Set new repo value")
    if org:
        options.append("Set new org value")
    if not item.required:
        options.append("Skip (leave unset)")

    # Get user choice
    if fzf:
        choice = fzf_select(f"Action for {item.name}", options)
    else:
        print("\nOptions:")
        for i, opt in enumerate(options, 1):
            print(f"  {i}. {opt}")
        try:
            idx = int(input("Select option: ")) - 1
            choice = options[idx] if 0 <= idx < len(options) else None
        except (ValueError, IndexError):
            choice = None

    if not choice:
        print("Skipped")
        return

    if choice.startswith("Use repo value") or choice.startswith("Use org value"):
        print(f"Keeping existing value")
        return

    if choice == "Skip (leave unset)":
        print("Skipped")
        return

    # Determine scope for new value
    scope = Scope.ORG if "org value" in choice else Scope.REPO

    # Get new value
    value = input_value(f"Enter value for {item.name}", item.default, item.is_secret)

    if not value and item.required:
        print(f"ERROR: {item.name} is required but no value provided")
        return

    if value:
        if set_value(item.name, value, item.is_secret, scope, org):
            print(f"Set {item.name} at {scope.value} level")
        else:
            print(f"ERROR: Failed to set {item.name}")


def check_workflow_file() -> bool:
    """Check if the caller workflow exists in the current repo."""
    workflow_path = Path(".github/workflows/release.yaml")
    if not workflow_path.exists():
        # Also check .yml extension
        workflow_path = Path(".github/workflows/release.yml")

    if workflow_path.exists():
        content = workflow_path.read_text()
        if "mod-release-workflow" in content or "mod-release.yaml" in content:
            return True

    print("\n" + "=" * 50)
    print("WARNING: No release workflow found in .github/workflows/")
    print("Copy caller-template.yaml to .github/workflows/release.yaml first")
    print("=" * 50)
    return False


def main() -> int:
    print("=" * 50)
    print("Mod Release Workflow Setup")
    print("=" * 50)

    # Check prerequisites
    if not gh_available():
        print("ERROR: gh CLI not found. Install from https://cli.github.com/")
        return 1

    has_fzf = fzf_available()
    if not has_fzf:
        print("WARNING: fzf not found - falling back to numbered selection")
        print("Install fzf for better experience: brew install fzf")

    fzf = FzfPrompt() if has_fzf else None

    # Get repo context
    repo_info = get_repo_info()
    if not repo_info:
        print("ERROR: Not in a GitHub repository or gh not authenticated")
        print("Run 'gh auth login' first")
        return 1

    org, repo = repo_info
    print(f"\nRepository: {org}/{repo}")

    # Check for workflow file
    check_workflow_file()

    # Ask what to configure
    config_options = [
        "Configure variables only",
        "Configure secrets only",
        "Configure both variables and secrets",
    ]

    if fzf:
        config_choice = fzf_select("What to configure", config_options)
    else:
        print("\nWhat to configure:")
        for i, opt in enumerate(config_options, 1):
            print(f"  {i}. {opt}")
        try:
            idx = int(input("Select option: ")) - 1
            config_choice = config_options[idx] if 0 <= idx < len(config_options) else config_options[2]
        except (ValueError, IndexError):
            config_choice = config_options[2]

    items_to_configure: list[ConfigItem] = []

    if config_choice and "variables" in config_choice.lower():
        items_to_configure.extend(VARIABLES)
    if config_choice and "secrets" in config_choice.lower():
        items_to_configure.extend(SECRETS)
    if config_choice and "both" in config_choice.lower():
        items_to_configure = VARIABLES + SECRETS

    if not items_to_configure:
        items_to_configure = VARIABLES + SECRETS

    # Configure each item
    for item in items_to_configure:
        configure_item(item, org, fzf)

    print("\n" + "=" * 50)
    print("Setup complete!")
    print("=" * 50)
    print("\nNext steps:")
    print("1. Ensure .github/workflows/release.yaml exists (copy from caller-template.yaml)")
    print("2. Update the workflow inputs (mod_name, mod_id, etc.)")
    print("3. Push to main branch to trigger the workflow")

    return 0


if __name__ == "__main__":
    sys.exit(main())

# mod-release-workflow

Reusable GitHub Actions workflow for Minecraft mod releases. Handles versioning, building, publishing, and downstream modpack PRs.

## Features

- Semantic versioning via commit messages
- Gradle build with caching
- GitHub Release creation with artifacts
- Publish to Modrinth and CurseForge via mc-publish
- Auto-update mod descriptions on platforms
- Downstream modpack PR via packwiz

## Quick Start

### 1. Copy the caller workflow

Copy `caller-template.yaml` to your mod repo as `.github/workflows/release.yaml`:

```bash
mkdir -p .github/workflows
cp /path/to/mod-release-workflow/caller-template.yaml .github/workflows/release.yaml
```

### 2. Configure the workflow

Edit `.github/workflows/release.yaml` and update the inputs:

```yaml
jobs:
  release:
    uses: game-design-driven/mod-release-workflow/.github/workflows/mod-release.yaml@main
    with:
      mod_name: "Your Mod Name"
      mod_id: "YourModId"
      mod_slug: "your-mod-slug"
      loader: "forge"
      mc_version: "1.20.1"
      # ... other inputs
```

### 3. Run the setup script

From your mod repo directory:

```bash
cd /path/to/your-mod-repo
uv run /path/to/mod-release-workflow/setup.py
```

The script will:
- Detect existing org/repo variables and secrets
- Let you choose to use existing values or set new ones
- Configure variables and secrets at repo or org level

### 4. Push to main

The workflow triggers on push to `main` branch.

## Inputs

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `mod_name` | Yes | - | Display name for the mod |
| `mod_id` | Yes | - | Mod identifier (usually matches jar name) |
| `mod_slug` | Yes | - | URL slug for platforms |
| `loader` | Yes | - | Mod loader (forge, fabric, neoforge, quilt) |
| `mc_version` | Yes | - | Minecraft version |
| `java_version` | No | `17` | Java version for build |
| `modrinth_id` | No | - | Modrinth project ID |
| `curseforge_id` | No | - | CurseForge project ID |
| `dependencies` | No | - | mc-publish dependencies block |
| `target_modpack_repo` | No | - | Downstream modpack repo (org/repo) |
| `enable_modrinth_sync` | No | `false` | Enable Modrinth modpack sync |
| `enable_curseforge_sync` | No | `false` | Enable CurseForge modpack sync |
| `curseforge_modpack_path` | No | `./curseforge` | Path to CF pack.toml in modpack |
| `manual_bump` | No | `patch` | Version bump type override |

## Secrets

| Secret | Required | Description |
|--------|----------|-------------|
| `GH_TOKEN` | Yes | GitHub PAT with repo access |
| `MODRINTH_TOKEN` | No | Modrinth API token |
| `CURSEFORGE_TOKEN` | No | CurseForge API token |

## Repository Variables

Set these via GitHub UI or the setup script:

| Variable | Description |
|----------|-------------|
| `MODRINTH_ID` | Modrinth project ID (alternative to input) |
| `CF_ID` | CurseForge project ID (alternative to input) |
| `ENABLE_MODRINTH_SYNC` | `true`/`false` |
| `ENABLE_CURSEFORGE_SYNC` | `true`/`false` |

## Commit Message Conventions

The workflow uses conventional commits for automatic versioning:

| Prefix | Bump | Example |
|--------|------|---------|
| `feat:` | minor | `feat: add new crafting recipe` |
| `overhaul:` | minor | `overhaul: redesign UI` |
| `fix:` | patch | `fix: correct item texture` |
| `refactor:` | patch | `refactor: clean up event handlers` |
| `chore:` | patch | `chore: update dependencies` |
| `docs:` | patch | `docs: update readme` |

## Workflow Jobs

1. **tests** - Validates JSON/YAML files
2. **tag_and_release** - Bumps version, creates git tag
3. **build** - Builds with Gradle, uploads artifacts
4. **github_release** - Creates GitHub Release with jars
5. **publish** - Publishes to Modrinth/CurseForge
6. **update_descriptions** - Syncs README.md to platform descriptions (non-fatal)
7. **make_pr_for_modpack** - Creates PR to update downstream modpack

## Optional: Version Update Script

If your mod repo has an `update_version.sh` script, it will be called during build:

```bash
#!/bin/bash
VERSION=$1
# Update gradle.properties, mods.toml, etc.
sed -i "s/^mod_version=.*/mod_version=$VERSION/" gradle.properties
```

## Setup Script Requirements

- [uv](https://docs.astral.sh/uv/) - Python package manager
- [gh](https://cli.github.com/) - GitHub CLI (authenticated)
- [fzf](https://github.com/junegunn/fzf) - Fuzzy finder (optional, improves UX)

## Directory Structure

```
mod-release-workflow/
├── .github/
│   └── workflows/
│       └── mod-release.yaml    # Reusable workflow
├── caller-template.yaml        # Template for mod repos
├── setup.py                    # Interactive setup script
└── README.md
```

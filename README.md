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
curl -o .github/workflows/release.yaml https://raw.githubusercontent.com/game-design-driven/mod-release-workflow/main/caller-template.yaml
```

### 2. Create dependencies.txt (if needed)

If your mod has dependencies, create `dependencies.txt` in your repo root with one dependency per line:

```
tooltips-reforged(required)
cloth-config(required)
modmenu(optional)
```

Format: `mod-slug(type)` where type is `required`, `optional`, `incompatible`, `embedded`, or version constraints. See [mc-publish docs](https://github.com/Kir-Antipov/mc-publish#dependencies) for full syntax.

### 3. Run the setup script

From your mod repo directory:

```bash
uv run /path/to/mod-release-workflow/setup.py
```
It requires `uv`, `gh`, and `fzf` installed.

The script will configure:
- Platform IDs (Modrinth, CurseForge)
- Modpack sync settings
- API tokens

### 4. Push to main

The workflow triggers on push to `main` branch.

## Inputs

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `loader` | Yes | - | Mod loader (forge, fabric, neoforge, quilt) |
| `mc_version` | Yes | - | Minecraft version |
| `java_version` | No | `17` | Java version for build |
| `modrinth_id` | No | - | Modrinth project ID |
| `curseforge_id` | No | - | CurseForge project ID |
| `modrinth_slug` | No | repo name | Modrinth slug for packwiz |
| `curseforge_slug` | No | repo name | CurseForge slug for packwiz |
| `target_modpack_repo` | No | - | Downstream modpack repo (org/repo) |
| `enable_modrinth_sync` | No | `false` | Enable Modrinth modpack sync |
| `enable_curseforge_sync` | No | `false` | Enable CurseForge modpack sync |
| `curseforge_modpack_path` | No | `./curseforge` | Path to CF pack.toml in modpack |
| `enable_github_release` | No | `true` | Enable GitHub Release creation |
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
| `MODRINTH_ID` | Modrinth project ID |
| `CF_ID` | CurseForge project ID |
| `TARGET_MODPACK_REPO` | Downstream modpack repo (org/repo format) |
| `MODRINTH_SLUG` | Modrinth slug for packwiz add/update |
| `CF_SLUG` | CurseForge slug for packwiz add/update |
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
6. **update_descriptions** - Syncs README.md to platform descriptions
7. **make_pr_for_modpack** - Creates PR to update downstream modpack

## Version Handling

The workflow automatically:
1. Passes `-Pmod_version=<tag>` to Gradle
2. Updates `mod_version` in `gradle.properties` (if present)
3. Commits the version change back to the repo

Your `build.gradle` should use:
```groovy
version = findProperty('mod_version') ?: mod_version
```

This prefers the CLI argument but falls back to `gradle.properties`.

## Setup Script Requirements

- [uv](https://docs.astral.sh/uv/) - Python package manager
- [gh](https://cli.github.com/) - GitHub CLI (authenticated)
- [fzf](https://github.com/junegunn/fzf) - Fuzzy finder

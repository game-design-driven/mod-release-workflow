<img width="1138" height="267" alt="Screenshot 2026-01-16 at 13 34 55" src="https://github.com/user-attachments/assets/8eebb722-b20b-4aff-95ca-c7ec07ecead9" />


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

### 2. Add required `[mc-publish]` metadata to mods.toml

This workflow requires a single `mods.toml` with a strict `[mc-publish]` table:

```toml
[mc-publish]
modrinth = "AANobbMI"
curseforge = 394468
loader = "forge"
mc_version = "1.20.1"
modrinth_slug = "your-mod-slug"
curseforge_slug = "your-mod-slug"
```

`loader` must be `forge`.
Template placeholders like `${...}` are not allowed in `[mc-publish]` values.

Dependencies are read directly from `mods.toml` by mc-publish. No `dependencies.txt` is used.
Only Forge is supported; `mods.toml` is required and is the single source of metadata.

### 3. Run the setup script

From your mod repo directory:

```bash
uv run /path/to/mod-release-workflow/setup.py
```
It requires `uv`, `gh`, and `fzf` installed.

The script will configure:
- `mods.toml` [mc-publish] metadata
- Modpack sync settings
- API tokens

### 4. Push to main

The workflow triggers on push to `main` branch.

## Inputs

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `java_version` | No | `17` | Java version for build |
| `target_modpack_repo` | No | - | Downstream modpack repo (org/repo) |
| `enable_modrinth_sync` | No | `false` | Enable Modrinth modpack sync |
| `enable_curseforge_sync` | No | `false` | Enable CurseForge modpack sync |
| `curseforge_modpack_path` | No | `./curseforge` | Path to CF pack.toml in modpack |
| `enable_github_release` | No | `true` | Enable GitHub Release creation |
| `manual_bump` | No | `patch` | Version bump type override |

Required metadata (Modrinth ID, CurseForge ID, loader, MC version, slugs) must be defined in `mods.toml` under `[mc-publish]`. Both platforms are required; the workflow fails if either is missing.

## Secrets

| Secret | Required | Description |
|--------|----------|-------------|
| `GH_TOKEN` | Yes | GitHub PAT with repo access |
| `MODRINTH_TOKEN` | Yes | Modrinth API token |
| `CURSEFORGE_TOKEN` | Yes | CurseForge API token |

## Repository Variables

Set these via GitHub UI or the setup script:

| Variable | Description |
|----------|-------------|
| `TARGET_MODPACK_REPO` | Downstream modpack repo (org/repo format) |
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

The workflow creates a git tag, then builds. Use the [palantir git-version](https://github.com/palantir/gradle-git-version) plugin to automatically derive the version from the tag:

**Groovy DSL (`build.gradle`):**
```groovy
plugins {
    id 'com.palantir.git-version' version '3.1.0'
}

version = gitVersion()
```

**Kotlin DSL (`build.gradle.kts`):**
```kotlin
plugins {
    id("com.palantir.git-version") version "3.1.0"
}

val gitVersion: groovy.lang.Closure<String> by extra
version = gitVersion()
```

No manual version management needed - the plugin reads directly from git tags.

## Setup Script Requirements

- [uv](https://docs.astral.sh/uv/) - Python package manager
- [gh](https://cli.github.com/) - GitHub CLI (authenticated)
- [fzf](https://github.com/junegunn/fzf) - Fuzzy finder

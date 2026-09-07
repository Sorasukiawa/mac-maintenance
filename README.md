# mac-maintenance

[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md)

[![Tests](https://github.com/Sorasukiawa/mac-maintenance/actions/workflows/tests.yml/badge.svg)](https://github.com/Sorasukiawa/mac-maintenance/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

A Mac maintenance skill for Codex: inspect hardware and software, review updates, assess obsolete applications, and keep evidence that can be checked before and after cleanup.

The helper scripts use only the Python standard library to gather evidence. The agent carries out authorized updates and cleanup through the appropriate maintenance tools. The scripts themselves do not install, delete, restart, or start services.

**Language scope:** This introduction is available in four languages. Skill instructions, detailed references, and script-generated Markdown reports are currently in Simplified Chinese. CLI flags and JSON field names use English.

## What it does

| Capability | Output and scope |
|---|---|
| Read-only audit | System, hardware, battery, applications, Homebrew metadata, and directory usage, with JSON and Chinese Markdown reports |
| Update review | Guides the agent to check official sources, platform, architecture, versions, and project compatibility; unmatched items remain unconfirmed |
| Cleanup preview | Captures metadata for exact targets and checks links, protected-path intersections, overlapping targets, nested cross-volume mounts, and owner processes |
| Revalidation | Detects file, path, or preference changes after a preview; unchanged metadata is not permission to delete |
| Result logs | Separates reported actions from observations, including source-path reduction, recorded removal, and volume free-space changes |
| Personal preferences | Specifies update exclusions, vendor update managers, and protected paths; the user's current explicit instructions take priority |

Use it for maintenance that needs an agent to assess each item, act within the user's scope, and document results. It has no command to erase all caches at once. Official updaters, uninstallers, project backups, and necessary functional checks remain part of the maintenance workflow.

## Install in Codex

Give Codex this request:

```text
Use $skill-installer to install the mac-maintenance skill from the root of https://github.com/Sorasukiawa/mac-maintenance. If a skill with the same name is already installed, inspect the differences and preserve my personal configuration.
```

For a manual installation, use the user directory described in the current [Codex local skill documentation](https://learn.chatgpt.com/docs/build-skills#where-codex-loads-local-skills):

```sh
mkdir -p "$HOME/.agents/skills"
git clone https://github.com/Sorasukiawa/mac-maintenance.git "$HOME/.agents/skills/mac-maintenance"
```

`git clone` stops if the destination is not empty. Update an existing installation instead of keeping duplicate skills with the same name. Codex normally detects changes automatically; restart it if the skill does not appear.

Example requests:

```text
Use $mac-maintenance to perform a read-only check of this Mac and list potential updates and cleanup items.
```

```text
Use $mac-maintenance to complete updates, organization, and cleanup within the authorized scope, excluding the apps I specify. You may remove an old version after verifying that its replacement works and applicable dependencies are unaffected.
```

## Run the scripts directly

You need macOS and a working Python 3.10+ runtime. No Python packages are required. Check that `python3 --version` runs successfully; if the system runtime is blocked by a license or permission requirement, use another available runtime.

From the repository directory:

```sh
mkdir -p work/maintenance
python3 scripts/audit.py --quick \
  --output work/maintenance/audit.json \
  --report work/maintenance/audit.md
```

Add `--online` to query available system updates. Omit `--quick` for peripheral, extension, backup, and service details. Existing output files are never overwritten; use new paths for each run. Partial failures are recorded in `coverage_gaps`, so a successful exit code does not mean every check succeeded.

Workflow for exact cleanup targets:

```sh
python3 scripts/cleanup.py preview --targets work/maintenance/targets.json \
  --output work/maintenance/plan.json
python3 scripts/cleanup.py verify --plan work/maintenance/plan.json
# Perform the authorized maintenance using verified purpose and activity evidence.
python3 scripts/cleanup.py record --plan work/maintenance/plan.json \
  --results work/maintenance/results.json --log work/maintenance/actions.jsonl
```

See the [script guide](references/script-usage.md) for the `targets.json` and `results.json` formats and status meanings. `review` still requires maintenance judgment, `unchanged` is not a writer lock, and a move within the same volume does not free disk space. Available tools and permissions determine which actions the agent can perform.

## Configure your preferences

Public defaults contain no application exclusions or personal paths. Copy the example to a Git-ignored local configuration, then customize it:

```sh
cp -n config/preferences.example.json config/preferences.local.json
python3 scripts/audit.py --quick --preferences config/preferences.local.json
```

The `com.example.*` bundle IDs are fictional; replace them with identifiers read from the actual apps. Use the same configuration for a task's `preview` and `verify` calls. Keep personal settings in a local file or task directory so repository updates do not overwrite them. Do not commit personal audit reports or operation logs.

## Validation and limitations

```sh
python3 -m unittest discover -v -s tests
```

Tests create, move, and delete files only in temporary fixtures. They cover plist formats, permission errors, timeouts, links and case aliases, changed targets, old-version replacements, log integrity, and space accounting. Platform- and filesystem-specific tests explicitly skip when inapplicable. Linux CI checks shared helper logic; it does not establish support for Linux host maintenance.

The first public version was developed with a read-only run on a Mac and independent scenario reviews. Hardware and software coverage is still limited: full hardware diagnostics, vendor firmware matching, professional-app licensing, and project compatibility need targeted evidence. Snapshots capture metadata, not content hashes or transactions, and do not guarantee recovery after deletion. Logs contain local paths and application details; remove personal information as appropriate before sharing.

## Contributing and license

Reproducible issues and pull requests are welcome. Include macOS/Python versions, expected behavior, and a minimal fixture with personal data removed. Describe the concrete trigger for workflow changes and add relevant tests for script changes. Never use real project libraries or user caches as deletion targets in tests.

Code and documentation are released under the [MIT License](LICENSE).

Design references include the preview/log/test organization in [mac-storage-cleaner](https://github.com/JubaKitiashvili/mac-storage-cleaner) and the layered audits and coverage gaps in [mac-performance-maintenance](https://github.com/rioriost/skills/tree/main/plugins/mac-performance-maintenance). This repository's scripts were implemented independently; they do not incorporate those projects' cleanup code or deletion rules.

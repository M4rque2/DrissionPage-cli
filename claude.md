# Claude Code Configuration

## Project Overview

This project is for developing **DrissionPage-cli** packages to be published on PyPI for `pip install`.

## Local Repository Structure

| Folder | Purpose |
|--------|---------|
| `ref_repos/DrissionPage-cli/` | Git repo for CLI tool package development |
| `ref_repos/DrissionPage/` | Reference: original DrissionPage source code |
| `ref_repos/playwright/` | Reference: Playwright source code for MCP/CLI patterns |
| `ref_repos/playwright-cli/` | Reference: Playwright-cli source code for MCP/CLI patterns |

## Documentation Sync Rule

Whenever you add a new CLI command or public function to any file in `drissionpage_cli/`:

1. Update `README.md` — add the command to the appropriate section with a usage example
2. Update `skills/drissionpage-cli/SKILL.md` — add to the matching Commands section
3. If it's a specialized topic (storage, network, screenshots, etc.), update or create the relevant file in `skills/drissionpage-cli/references/`

The README, SKILL.md, and source code must always be kept in sync.

## Preference: Read source before web_search

When answering questions about DrissionPage (or any repository), always:

1. **First**: Read the local source code in the `DrissionPage/` folder
2. **Then**: Use web_search MCP only if the local source code doesn't contain the answer

This ensures more accurate answers based on actual source code rather than potentially outdated or incorrect web search results.

## Repository-Specific Notes

- DrissionPage has a custom proprietary license (not MIT/BSD)
- The LICENSE file contains the full terms in both Chinese and English
- Our packages should use MIT License and clearly reference DrissionPage's proprietary license in README
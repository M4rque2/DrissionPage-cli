# Browser Session Management

## Persistent Profile (default)

All sessions share a single persistent Chrome profile at `~/.drissionpage-cli/profile`.

This means:
- **Login once, always logged in.** Cookies and tokens accumulate across runs. Once the human logs in to a site, the agent never needs to ask again.
- The profile persists across different working directories and across restarts.
- Both headed and headless mode use the same profile.

```bash
# Default: headed browser, persistent profile
drissionpage-cli open https://example.com

# Headless with the same persistent profile
drissionpage-cli open https://example.com --headless

# Reset all login state (wipes ~/.drissionpage-cli/profile)
drissionpage-cli delete-data --reset-profile
```

## Human-in-the-loop: handling login, CAPTCHA, 2FA

Because the default mode opens a visible browser, the human can always step in when the agent encounters something it cannot handle autonomously:

```
Agent:  drissionpage-cli open https://app.example.com/dashboard
         → redirected to login page
         → "Please log in in the browser window, then tell me when done"
Human: [completes login, 2FA, CAPTCHA in the browser]
Human: "done"
Agent:  drissionpage-cli snapshot
         → now on the dashboard; continues autonomously
         → next run: already authenticated, skips login entirely
```

**Triggers for asking the human:**
- Login / sign-in pages
- CAPTCHA or reCAPTCHA challenges
- Two-factor authentication (TOTP, SMS, push notifications)
- OAuth / SSO flows
- Cookie consent dialogs that block content

## Sandbox mode (isolated, no persistence)

For throwaway sessions where login state must not be retained:

```bash
drissionpage-cli open --sandbox
```

Sandbox sessions use a random port and a temporary profile that is cleaned up when Chrome exits.

## Named Browser Sessions

Use `-s` to run multiple browser instances concurrently, each with its own port and tab state. They all share the same persistent profile unless `--sandbox` is used.

```bash
# Two concurrent sessions
drissionpage-cli -s=auth open https://app.example.com/login
drissionpage-cli -s=scrape open https://data.example.com

# Commands are routed by session name
drissionpage-cli -s=auth fill "css:input[name=email]" "user@example.com"
drissionpage-cli -s=scrape snapshot
```

## Session Commands

```bash
# List all active sessions
drissionpage-cli list

# Close a session
drissionpage-cli close                    # close default session
drissionpage-cli -s=mysession close       # close named session

# Close all sessions
drissionpage-cli close-all

# Kill all browser processes (for stale/zombie processes)
drissionpage-cli kill-all

# Close session; profile is retained (login state survives)
drissionpage-cli delete-data

# Close session AND wipe the persistent profile (resets all logins)
drissionpage-cli delete-data --reset-profile
```

## Environment Variable

Set a default session name:

```bash
export DRISSIONPAGE_CLI_SESSION="mysession"
drissionpage-cli open https://example.com  # uses "mysession"
```

## Common Patterns

### Agent task requiring authentication

```bash
# Agent opens the target site
drissionpage-cli open https://dashboard.example.com

# If login is required, agent reports to human and waits
# Human logs in via the browser window
# Agent continues after confirmation
drissionpage-cli snapshot
drissionpage-cli goto https://dashboard.example.com/data
```

### Concurrent Scraping

```bash
#!/bin/bash
drissionpage-cli -s=site1 open https://site1.com &
drissionpage-cli -s=site2 open https://site2.com &
drissionpage-cli -s=site3 open https://site3.com &
wait

drissionpage-cli -s=site1 snapshot
drissionpage-cli -s=site2 snapshot
drissionpage-cli -s=site3 snapshot

drissionpage-cli close-all
```

### Headless CI (no human, site doesn't require login)

```bash
drissionpage-cli open --headless https://public-site.com
drissionpage-cli snapshot
drissionpage-cli close
```

## Default Session

When `-s` is omitted, the `default` session is used:

```bash
drissionpage-cli open https://example.com
drissionpage-cli snapshot
drissionpage-cli close
```

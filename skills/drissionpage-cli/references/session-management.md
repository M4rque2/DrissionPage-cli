# Browser Session Management

Run multiple isolated browser sessions concurrently.

## Named Browser Sessions

Use `-s` flag to isolate browser contexts:

```bash
# Browser 1: Authentication flow
drissionpage-cli -s=auth open https://app.example.com/login

# Browser 2: Public browsing (separate cookies, storage)
drissionpage-cli -s=public open https://example.com

# Commands are isolated by session
drissionpage-cli -s=auth fill "css:input[name=email]" "user@example.com"
drissionpage-cli -s=public snapshot
```

## Session Isolation Properties

Each session has independent:
- Cookies
- LocalStorage / SessionStorage
- Cache
- Browsing history
- Open tabs
- CDP debugging port

## Session Commands

```bash
# List all sessions
drissionpage-cli list

# Close a session
drissionpage-cli close                    # close default session
drissionpage-cli -s=mysession close       # close named session

# Close all sessions
drissionpage-cli close-all

# Kill all browser processes (for stale/zombie processes)
drissionpage-cli kill-all

# Delete session user data
drissionpage-cli delete-data                  # default session
drissionpage-cli -s=mysession delete-data     # named session
```

## Environment Variable

Set a default session name:

```bash
export DRISSIONPAGE_CLI_SESSION="mysession"
drissionpage-cli open https://example.com  # uses "mysession"
```

## Common Patterns

### Concurrent Scraping

```bash
#!/bin/bash
# Scrape multiple sites concurrently
drissionpage-cli -s=site1 open https://site1.com &
drissionpage-cli -s=site2 open https://site2.com &
drissionpage-cli -s=site3 open https://site3.com &
wait

drissionpage-cli -s=site1 snapshot
drissionpage-cli -s=site2 snapshot
drissionpage-cli -s=site3 snapshot

drissionpage-cli close-all
```

### A/B Testing

```bash
drissionpage-cli -s=variant-a open "https://app.com?variant=a"
drissionpage-cli -s=variant-b open "https://app.com?variant=b"

drissionpage-cli -s=variant-a screenshot
drissionpage-cli -s=variant-b screenshot
```

### Persistent Profile

```bash
# Use persistent profile
drissionpage-cli open https://example.com --profile=/path/to/profile

# Specific CDP port
drissionpage-cli open https://example.com --port=9222
```

## Default Session

When `-s` is omitted, the `default` session is used:

```bash
drissionpage-cli open https://example.com
drissionpage-cli snapshot
drissionpage-cli close
```

## Best Practices

### 1. Name Sessions Semantically

```bash
# GOOD
drissionpage-cli -s=github-auth open https://github.com
drissionpage-cli -s=docs-scrape open https://docs.example.com

# AVOID
drissionpage-cli -s=s1 open https://github.com
```

### 2. Always Clean Up

```bash
drissionpage-cli -s=auth close
drissionpage-cli -s=scrape close
# Or:
drissionpage-cli close-all
```

### 3. Delete Stale Data

```bash
drissionpage-cli -s=oldsession delete-data
```

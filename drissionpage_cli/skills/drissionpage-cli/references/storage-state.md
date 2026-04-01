# Storage Management

Manage cookies, localStorage, sessionStorage, and full browser state.

## State Save / Load

Save and restore complete browser state including cookies and storage.

### Save State

```bash
# Auto-generated filename
drissionpage-cli state-save

# Specific filename
drissionpage-cli state-save my-auth-state.json
```

### Load State

```bash
drissionpage-cli state-load my-auth-state.json
```

### State File Format

```json
{
  "url": "https://example.com/dashboard",
  "cookies": [
    {
      "name": "session_id",
      "value": "abc123",
      "domain": "example.com",
      "path": "/",
      "httpOnly": true,
      "secure": true
    }
  ],
  "localStorage": [
    ["theme", "dark"],
    ["user_id", "12345"]
  ],
  "sessionStorage": [
    ["step", "3"]
  ]
}
```

## Cookies

### List All Cookies

```bash
drissionpage-cli cookie-list
```

### Filter by Domain

```bash
drissionpage-cli cookie-list --domain=example.com
```

### Get Specific Cookie

```bash
drissionpage-cli cookie-get session_id
```

### Set a Cookie

```bash
# Basic cookie
drissionpage-cli cookie-set session abc123

# Cookie with options
drissionpage-cli cookie-set session abc123 --domain=example.com --path=/ --httpOnly --secure
```

### Delete / Clear Cookies

```bash
drissionpage-cli cookie-delete session_id
drissionpage-cli cookie-clear
```

### Advanced: Multiple Cookies via run-code

```bash
drissionpage-cli run-code "
page.set.cookies([
    {'name': 'session_id', 'value': 'sess_abc', 'domain': 'example.com'},
    {'name': 'prefs', 'value': 'dark', 'domain': 'example.com'}
])
result = 'cookies set'
"
```

## LocalStorage

```bash
drissionpage-cli localstorage-list
drissionpage-cli localstorage-get token
drissionpage-cli localstorage-set theme dark
drissionpage-cli localstorage-set user_settings '{"theme":"dark","lang":"en"}'
drissionpage-cli localstorage-delete token
drissionpage-cli localstorage-clear
```

## SessionStorage

```bash
drissionpage-cli sessionstorage-list
drissionpage-cli sessionstorage-get form_data
drissionpage-cli sessionstorage-set step 3
drissionpage-cli sessionstorage-delete step
drissionpage-cli sessionstorage-clear
```

## Common Patterns

### Authentication State Reuse

```bash
# Step 1: Login and save state
drissionpage-cli open https://app.example.com/login
drissionpage-cli snapshot
drissionpage-cli fill "css:input[name=email]" "user@example.com"
drissionpage-cli fill "css:input[name=password]" "password123"
drissionpage-cli click "tag:button"
drissionpage-cli state-save auth.json

# Step 2: Restore state later
drissionpage-cli state-load auth.json
drissionpage-cli goto https://app.example.com/dashboard
# Already logged in!
```

## Security Notes

- Never commit state files containing auth tokens
- Add `*.json` state files to `.gitignore`
- Delete state files after automation completes
- Use environment variables for sensitive data

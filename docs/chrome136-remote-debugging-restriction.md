# Chrome 136: Remote Debugging Blocked on Default Profile

## Primary Source

**Official blog post by Will Harris (Google Chrome Security Team)**
- URL: https://developer.chrome.com/blog/remote-debugging-port
- Published: March 17, 2025
- Title: "Changes to remote debugging switches to improve security"

---

## What Changed

From **Chrome 136**, the `--remote-debugging-port` and `--remote-debugging-pipe`
command-line switches **no longer work** when Chrome is launched against its
**default user data directory**.

These switches must now be accompanied by `--user-data-dir` pointing to a
**non-standard (non-default) directory**.

This restriction applies to:
- **All platforms: Windows, Linux, macOS**
- **Headed mode only** (see exceptions below)

---

## Why

Google introduced [App-Bound Encryption for Chrome cookies](https://security.googleblog.com/2024/07/improving-security-of-chrome-cookies-on.html)
in 2024 to combat infostealers. That change significantly reduced cookie theft.
However, attackers adapted by pivoting to remote debugging as an alternative
extraction method — a technique that has been [publicly documented since 2018](https://mango.pdf.zone/stealing-chrome-cookies-without-a-password/).

The core security property of the new restriction:
> A **non-standard data directory uses a different encryption key**, meaning
> Chrome's data is protected from attackers even if they can launch Chrome with
> remote debugging enabled.

---

## Exact Quote from the Blog Post

> "Therefore, from Chrome 136 we're making changes to the behavior of
> `--remote-debugging-port` and `--remote-debugging-pipe`. These switches will
> no longer be respected if attempting to debug the default Chrome data
> directory. These switches must now be accompanied by the `--user-data-dir`
> switch to point to a non-standard directory. A non-standard data directory
> uses a different encryption key meaning Chrome's data is now protected from
> attackers."

---

## Exceptions (Not Affected)

| Scenario | Affected? | Notes |
|---|---|---|
| Headed mode + default profile | **YES — blocked** | The restriction |
| Headed mode + custom `--user-data-dir` | No | Explicitly allowed |
| Headless mode (`--headless=new`) | No | Not subject to this restriction |
| Chrome for Testing | No | Continues to respect existing behaviour |

---

## Impact on drissionpage-cli

`use_system_user_path(True)` in DrissionPage strips `--user-data-dir` entirely
and lets Chrome default to the OS system profile path. This worked in headless
mode (Chrome 136's exception), but fails in **headed mode on all platforms**
because Chrome now refuses remote debugging on the default profile.

### Default profile paths by OS

| OS | Default Chrome user data directory |
|---|---|
| Windows | `%LOCALAPPDATA%\Google\Chrome\User Data` |
| macOS | `~/Library/Application Support/Google/Chrome` |
| Linux | `~/.config/google-chrome` (or `$XDG_CONFIG_HOME/google-chrome`) |

### Linux workaround (used in this project)

On Linux, Chrome detects "default profile" by comparing `--user-data-dir`
against the path derived from `$XDG_CONFIG_HOME`. The workaround is to:

1. Pass the real system profile path explicitly via `set_user_data_path()`
2. Set `XDG_CONFIG_HOME` to a fake/nonexistent path **before** Chrome launches

This makes Chrome treat the real profile as "non-default", bypassing the
restriction while still loading the user's actual data.

This workaround **does not apply to Windows or macOS** — their default-profile
detection is not based on environment variables.

---

## Related Links

- [App-Bound Encryption announcement (July 2024)](https://security.googleblog.com/2024/07/improving-security-of-chrome-cookies-on.html)
- [Cookie theft via remote debugging (2018, mango.pdf.zone)](https://mango.pdf.zone/stealing-chrome-cookies-without-a-password/)
- [Cookie theft techniques blog post that triggered this change (embracethered.com)](https://embracethered.com/blog/posts/2024/cookie-theft-in-2024-and-what-todo/)
- [cookie_crimes tool (GitHub)](https://github.com/defaultnamehere/cookie_crimes)
- [Chrome for Testing](https://developer.chrome.com/blog/chrome-for-testing)

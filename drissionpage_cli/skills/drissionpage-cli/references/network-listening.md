# Network Listening

Monitor and capture network requests using DrissionPage's built-in listener.

## Starting the Listener

Use `run-code` to start network monitoring:

```bash
# Listen for all requests
drissionpage-cli run-code "
page.listen.start()
"

# Listen for specific URL patterns
drissionpage-cli run-code "
page.listen.start('api/users')
"

# Listen with regex
drissionpage-cli run-code "
page.listen.start('api/.*', is_regex=True)
"

# Listen for specific HTTP methods
drissionpage-cli run-code "
page.listen.start('api/', method='POST')
"

# Listen for specific response types
drissionpage-cli run-code "
page.listen.start(res_type='xhr')
"
```

## Capturing Requests

```bash
# Navigate to trigger requests, then collect
drissionpage-cli run-code "
page.listen.start('api/')
page.get('https://example.com/dashboard')
import time; time.sleep(3)
packets = page.listen.steps()
result = []
for p in packets:
    result.append({
        'url': p.url,
        'method': p.method,
        'status': p.response.status if p.response else None,
        'body': str(p.response.body)[:200] if p.response else None
    })
page.listen.stop()
"
```

## Stopping the Listener

```bash
drissionpage-cli run-code "
page.listen.stop()
result = 'listener stopped'
"
```

## Common Patterns

### API Response Capture

```bash
drissionpage-cli run-code "
page.listen.start('api/data')
page.ele('#load-data').click()
import time; time.sleep(2)
packets = page.listen.steps()
if packets:
    result = packets[0].response.body
else:
    result = 'no requests captured'
page.listen.stop()
"
```

### Monitoring Login Flow

```bash
drissionpage-cli run-code "
page.listen.start('auth', method='POST')
page.ele('@name=username').input('admin')
page.ele('@name=password').input('secret')
page.ele('tag:button').click()
import time; time.sleep(3)
packets = page.listen.steps()
result = [{'url': p.url, 'status': p.response.status} for p in packets]
page.listen.stop()
"
```

### Waiting for Specific Request

```bash
drissionpage-cli run-code "
page.listen.start('api/submit')
page.ele('#submit-form').click()
# Wait for the request with timeout
packet = page.listen.wait(timeout=10)
if packet:
    result = {'status': packet.response.status, 'body': str(packet.response.body)[:500]}
else:
    result = 'timeout waiting for request'
page.listen.stop()
"
```

## Notes

- The listener captures requests made by the browser via CDP
- Use `page.listen.steps()` to get all captured packets since last call
- Use `page.listen.wait()` to block until a matching request arrives
- Always call `page.listen.stop()` when done
- Listener targets can be strings or regex patterns

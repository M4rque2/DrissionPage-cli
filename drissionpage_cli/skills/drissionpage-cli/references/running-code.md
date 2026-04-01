# Running Custom DrissionPage Code

Use `run-code` to execute arbitrary DrissionPage Python code for advanced scenarios.

## Syntax

```bash
# Inline code
drissionpage-cli run-code "result = page.title"

# From file
drissionpage-cli run-code --filename=script.py
```

The `page` variable is the active `ChromiumPage` instance. Set `result` to return a value.

## Page Information

```bash
# Get page title
drissionpage-cli run-code "result = page.title"

# Get current URL
drissionpage-cli run-code "result = page.url"

# Get page HTML (truncated)
drissionpage-cli run-code "result = page.html[:500]"

# Get page text content
drissionpage-cli run-code "result = page.ele('tag:body').text[:500]"
```

## Element Interaction

```bash
# Find and click
drissionpage-cli run-code "
ele = page.ele('@id=submit')
ele.click()
result = 'clicked'
"

# Fill a form
drissionpage-cli run-code "
page.ele('@name=username').input('admin')
page.ele('@name=password').input('secret')
page.ele('tag:button').click()
result = 'form submitted'
"

# Get element attributes
drissionpage-cli run-code "
ele = page.ele('tag:img')
result = {'src': ele.attr('src'), 'alt': ele.attr('alt')}
"
```

## Wait Strategies

```bash
# Wait for element to appear
drissionpage-cli run-code "
ele = page.ele('@id=result', timeout=10)
result = ele.text
"

# Wait for URL change
drissionpage-cli run-code "
page.ele('tag:button').click()
page.wait.url_change('dashboard')
result = page.url
"

# Wait for element to be displayed
drissionpage-cli run-code "
page.wait.ele_displayed('@id=modal')
result = page.ele('@id=modal').text
"
```

## JavaScript Execution

```bash
# Run JavaScript on the page
drissionpage-cli run-code "
result = page.run_js('return document.title')
"

# Run JavaScript with return value
drissionpage-cli run-code "
result = page.run_js('return navigator.userAgent')
"

# Modify page via JavaScript
drissionpage-cli run-code "
page.run_js('document.body.style.background = \"red\"')
result = 'background changed'
"
```

## Network Listening

```bash
# Start listening for API calls
drissionpage-cli run-code "
page.listen.start('api/users')
page.get('https://example.com/users')
import time; time.sleep(2)
packets = page.listen.steps()
result = [{'url': p.url, 'status': p.response.status} for p in packets]
page.listen.stop()
"
```

## File Downloads

```bash
# Set download path and trigger download
drissionpage-cli run-code "
page.set.download_path('./downloads')
page.ele('text:Download PDF').click()
result = 'download triggered'
"
```

## Scraping Data

```bash
# Extract data from a table
drissionpage-cli run-code "
rows = page.eles('css:table tbody tr')
data = []
for row in rows:
    cells = row.eles('tag:td')
    data.append([c.text for c in cells])
result = data
"

# Extract all links
drissionpage-cli run-code "
links = page.eles('tag:a')
result = [{'text': a.text, 'href': a.link} for a in links if a.link]
"
```

## Error Handling

```bash
# Try-catch pattern
drissionpage-cli run-code "
try:
    ele = page.ele('@id=missing', timeout=2)
    result = ele.text
except Exception as e:
    result = f'Element not found: {e}'
"
```

## Multi-page Workflows

```bash
# Scrape multiple pages
drissionpage-cli run-code "
import json
results = []
for i in range(1, 4):
    page.get(f'https://example.com/page/{i}')
    items = page.eles('css:.item')
    results.extend([item.text for item in items])
result = results
"
```

## Iframe Access

```bash
# Work with iframes
drissionpage-cli run-code "
frame = page.get_frame('@id=my-iframe')
result = frame.ele('tag:h1').text
"
```

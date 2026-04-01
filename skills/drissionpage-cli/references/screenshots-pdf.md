# Screenshots and PDF

Capture browser screenshots and save pages as PDF.

## Screenshots

### Full Page Screenshot

```bash
# Auto-generated filename
drissionpage-cli screenshot

# Custom filename
drissionpage-cli screenshot --filename=homepage.png
```

### Element Screenshot

```bash
# Screenshot a specific element
drissionpage-cli screenshot "#main-content"
drissionpage-cli screenshot "@id=hero-image"
drissionpage-cli screenshot "tag:table"
```

### Advanced Screenshots via run-code

```bash
# Full-page screenshot with custom path
drissionpage-cli run-code "
page.get_screenshot(path='./screenshots/full-page.png', full_page=True)
result = 'screenshot saved'
"

# Screenshot with specific element
drissionpage-cli run-code "
ele = page.ele('@id=chart')
ele.get_screenshot(path='./screenshots/chart.png')
result = 'element screenshot saved'
"
```

## PDF

### Save Page as PDF

```bash
# Auto-generated filename
drissionpage-cli pdf

# Custom filename
drissionpage-cli pdf --filename=report.pdf
```

### Advanced PDF via run-code

```bash
drissionpage-cli run-code "
page.save(path='./output/report.pdf', as_pdf=True)
result = 'PDF saved'
"
```

## Common Patterns

### Before/After Comparison

```bash
drissionpage-cli open https://example.com/form
drissionpage-cli screenshot --filename=before.png

drissionpage-cli fill "css:input[name=email]" "test@example.com"
drissionpage-cli click "#submit"
drissionpage-cli screenshot --filename=after.png
```

### Evidence Capture

```bash
drissionpage-cli open https://app.example.com/dashboard
drissionpage-cli screenshot --filename=evidence/dashboard.png
drissionpage-cli click "text:Reports"
drissionpage-cli screenshot --filename=evidence/reports.png
```

### Multi-Tab Screenshots

```bash
drissionpage-cli open https://site1.com
drissionpage-cli screenshot --filename=site1.png
drissionpage-cli tab-new https://site2.com
drissionpage-cli screenshot --filename=site2.png
```

# Element Locator Strategies

DrissionPage supports rich locator syntax beyond CSS and XPath.

## Locator Types

### CSS Selector

```bash
drissionpage-cli click "css:#main > button.submit"
drissionpage-cli fill "css:input[name=email]" "test@example.com"
drissionpage-cli snapshot "css:.content-area"
```

### XPath

```bash
drissionpage-cli click "xpath://button[@id='submit']"
drissionpage-cli fill "xpath://input[@placeholder='Search']" "query"
```

### Tag Name

```bash
drissionpage-cli click "tag:button"
drissionpage-cli snapshot "tag:main"
```

### Text Content

```bash
# Exact text match
drissionpage-cli click "text:Submit"
# Partial text match
drissionpage-cli click "text=Submit"
```

### Attribute Matching

```bash
# Exact attribute match
drissionpage-cli click "@id=submit-btn"
drissionpage-cli click "@data-testid=login-button"

# Contains
drissionpage-cli click "@class:btn-primary"

# Starts with
drissionpage-cli click "@name^=user"

# Ends with
drissionpage-cli click "@href$=.pdf"
```

### Combined Attributes (AND)

```bash
# Element must match ALL conditions
drissionpage-cli click "@@tag()=button@@text()=Submit"
drissionpage-cli click "@@class:btn@@text():Login"
```

### Combined Attributes (OR)

```bash
# Element must match ANY condition
drissionpage-cli click "@|id=btn1@id=btn2"
```

### Negation

```bash
# Element must NOT match
drissionpage-cli click "@!class:disabled"
```

## Inspecting Element Properties

When the snapshot doesn't reveal element properties, use `eval`:

```bash
# Get element id
drissionpage-cli eval "return this.id" "#some-element"

# Get all CSS classes
drissionpage-cli eval "return this.className" "tag:button"

# Get a specific attribute
drissionpage-cli eval "return this.getAttribute('data-testid')" "@class:card"

# Get computed style
drissionpage-cli eval "return window.getComputedStyle(this).display" "#element"

# Get element text content
drissionpage-cli eval "return this.textContent" "tag:h1"
```

## Navigation Between Elements

DrissionPage locators support relative element navigation:

```bash
# Use run-code for complex element traversal
drissionpage-cli run-code "
ele = page.ele('@id=container')
child = ele.child('tag:span')
result = child.text
"
```

## Best Practices

1. **Prefer semantic locators**: `@data-testid=login` is more stable than `css:.btn-3`
2. **Use text for buttons/links**: `text:Submit` reads naturally
3. **Use @id when available**: `@id=submit` is fastest and most reliable
4. **Combine for specificity**: `@@tag()=input@@name=email` when simple locators are ambiguous

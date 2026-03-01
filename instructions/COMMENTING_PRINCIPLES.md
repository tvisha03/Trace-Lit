# Code Commenting Principles & Best Practices

## The Golden Rule of Commenting

**"Programs must be written for people to read and only incidentally for machines to execute."** - Hal Abelson, MIT

**The best code is self-documenting. The best comments explain what self-documenting code cannot.**

---

## Core Philosophy: Why, Not What

### The Fundamental Principle

Comments should explain the reasoning and context behind code decisions, rather than describing what the code does. Your code already shows *what* it does—comments should reveal *why* it does it.

**BAD - Describes What:**

```javascript
// Loop through users array
for (let i = 0; i < users.length; i++) {
  // Check if user is active
  if (users[i].isActive) {
    // Add to active users
    activeUsers.push(users[i]);
  }
}
```

**GOOD - Explains Why:**

```javascript
// Filter active users to exclude deactivated accounts from billing calculation
for (let i = 0; i < users.length; i++) {
  if (users[i].isActive) {
    activeUsers.push(users[i]);
  }
}
```

---

## The 9 Essential Rules

### Rule 1: Comments Should Not Duplicate the Code

The code itself already tells the computer what to do—comments shouldn't repeat this information.

**BAD:**

```python
# Set x to 5
x = 5

# Increment counter by 1
counter += 1
```

**GOOD:**

```python
# Use 5 threads for optimal performance on 4-core systems
x = 5

# Track number of retry attempts for exponential backoff
counter += 1
```

### Rule 2: Good Comments Do Not Excuse Unclear Code

If you need extensive comments to explain what your code does, the code itself is probably the problem. Refactor unclear code first rather than trying to explain it with comments.

**BAD:**

```javascript
// Get the first letter of firstName and lastName, combine them, 
// convert to uppercase, and add a random 4-digit number
let id = (fN.charAt(0) + lN.charAt(0)).toUpperCase() + Math.floor(Math.random() * 10000);
```

**GOOD:**

```javascript
function generateUserID(firstName, lastName) {
  const initials = (firstName[0] + lastName[0]).toUpperCase();
  const randomSuffix = Math.floor(Math.random() * 10000);
  return initials + randomSuffix;
}

let id = generateUserID(firstName, lastName);
```

### Rule 3: If You Can't Write a Clear Comment, There May Be a Problem with the Code

Difficulty explaining code in a comment often signals that the code needs refactoring. Step back and consider restructuring.

### Rule 4: Comments Should Dispel Confusion, Not Cause It

**The worst comment is an outdated or incorrect one.** Misleading comments are more harmful than no comments at all.

**BAD:**

```java
// Returns the user's age
public int getUserID() {
  return this.userId;
}
```

**Maintenance Rule:** When you change code, ALWAYS update associated comments.

### Rule 5: Explain Unidiomatic Code in Comments

When you must write code in a non-standard way—for performance, compatibility, or to work around a bug—explain why.

**GOOD:**

```python
# Using manual iteration instead of list comprehension
# because we need to break early on first match (50% faster for large datasets)
for item in collection:
    if item.matches(criteria):
        result = item
        break
```

### Rule 6: Provide Links to Original Sources of Copied Code

Always credit where you found solutions, especially from Stack Overflow, documentation, or research papers.

**GOOD:**

```javascript
// Binary search implementation adapted from:
// https://stackoverflow.com/questions/12345678/efficient-binary-search
// Modified to handle null values in dataset
function binarySearch(arr, target) {
  // ... implementation
}
```

### Rule 7: Include Links to External References Where Helpful

Link to documentation, RFCs, bug reports, or specifications that provide context.

**GOOD:**

```python
# Implements OAuth 2.0 Authorization Code Flow
# Spec: https://datatracker.ietf.org/doc/html/rfc6749#section-4.1
def authorize_user(client_id, redirect_uri):
    # ... implementation
```

### Rule 8: Add Comments When Fixing Bugs

When fixing a bug, explain what the bug was and why your fix works. This prevents future developers from "fixing" your fix.

**GOOD:**

```java
// Bug fix: Previous code didn't handle negative temperatures
// causing incorrect Celsius to Fahrenheit conversions below 0°C
if (celsius < 0) {
    fahrenheit = (celsius * 9/5) + 32;
}
```

### Rule 9: Use Comments to Mark Incomplete Implementations

Use standard markers like TODO, FIXME, HACK, or NOTE for temporary code that needs attention.

**GOOD:**

```javascript
// TODO: Add input validation for email format
// FIXME: Memory leak when processing large files (Issue #234)
// HACK: Temporary workaround until API v2 is available
// NOTE: This function must be called before initialize()
```

**CRITICAL:** Never push TODOs to production code. Convert them to proper issue tracker items instead.

---

## When to Comment

### DO Comment When

1. **Explaining Business Logic**

   ```javascript
   // Apply 15% discount for enterprise customers per 2024 pricing policy
   const discount = isEnterprise ? 0.15 : 0;
   ```

2. **Documenting Algorithm Choices**

   ```python
   # Using quicksort instead of merge sort because our data 
   # is mostly sorted (quicksort performs better on nearly-sorted arrays)
   quicksort(data)
   ```

3. **Warning About Side Effects**

   ```java
   // CAUTION: This method modifies the original array in place
   public void sortInPlace(int[] arr) { ... }
   ```

4. **Explaining Workarounds**

   ```javascript
   // Safari doesn't support ResizeObserver, falling back to polling
   if (!window.ResizeObserver) {
     setInterval(checkSize, 100);
   }
   ```

5. **Complex Calculations or Formulas**

   ```python
   # Haversine formula for calculating distance between GPS coordinates
   # Formula: a = sin²(Δφ/2) + cos φ1 ⋅ cos φ2 ⋅ sin²(Δλ/2)
   distance = calculateHaversine(lat1, lon1, lat2, lon2)
   ```

6. **Non-Obvious Performance Optimizations**

   ```java
   // Cache result since this calculation is expensive (O(n²))
   // and data rarely changes
   if (cachedResult == null) {
       cachedResult = computeExpensiveOperation();
   }
   ```

7. **Security-Critical Code**

   ```python
   # SECURITY: Input must be sanitized to prevent SQL injection
   # Never pass user input directly to database queries
   sanitized_input = escape_sql(user_input)
   ```

### DON'T Comment When

1. **The Code Is Self-Explanatory**

   ```python
   # BAD: Don't do this
   # Get user name
   user_name = user.get_name()
   
   # GOOD: Just write this
   user_name = user.get_name()
   ```

2. **Stating the Obvious**

   ```javascript
   // BAD
   i++; // Increment i by 1
   
   // BAD
   return true; // Return true
   ```

3. **Commenting Every Line**
   Over-commenting clutters code and makes it harder to read.

4. **Restating Variable Names**

   ```java
   // BAD
   int userAge; // User's age
   String userName; // User's name
   ```

---

## Types of Comments

### 1. Inline Comments

Brief comments on the same line as code. Use sparingly and separate by at least two spaces from the statement.

```python
x = calculate_total() + 10  # Add $10 service fee per company policy
```

### 2. Block Comments

Multi-line comments that apply to code following them, indented to the same level.

```python
# This algorithm uses a two-pointer approach to find pairs
# that sum to the target value. Time complexity: O(n)
# Space complexity: O(1) since we modify in place
def find_pairs(arr, target):
    # ... implementation
```

### 3. Documentation Comments (Docstrings)

Formal documentation for functions, classes, and modules.

**Python (docstring):**

```python
def calculate_tax(income, tax_rate):
    """
    Calculate tax amount based on income and rate.
    
    Args:
        income (float): Total income amount
        tax_rate (float): Tax rate as decimal (e.g., 0.15 for 15%)
    
    Returns:
        float: Calculated tax amount
    
    Raises:
        ValueError: If income is negative or tax_rate not in [0, 1]
    """
    if income < 0 or not 0 <= tax_rate <= 1:
        raise ValueError("Invalid input parameters")
    return income * tax_rate
```

**JavaScript (JSDoc):**

```javascript
/**
 * Fetches user data from the API
 * 
 * @param {string} userId - Unique identifier for user
 * @param {Object} options - Optional configuration
 * @param {boolean} options.includeInactive - Include deactivated users
 * @returns {Promise<User>} User object with all properties
 * @throws {APIError} If user not found or server error
 * 
 * @example
 * const user = await fetchUser('abc123', { includeInactive: true });
 */
async function fetchUser(userId, options = {}) {
    // ... implementation
}
```

### 4. File Headers

Document file purpose, author, copyright, and metadata.

```python
"""
Financial Calculator Module

This module provides functions for calculating various financial metrics
including compound interest, loan payments, and investment returns.

Author: Jane Smith
Created: 2025-01-05
License: MIT
"""
```

---

## Comment Style Guidelines

### Length and Formatting

- Keep comments concise and limit line length to 72-80 characters for readability.
- Use complete sentences with proper capitalization and punctuation
- Start with a capital letter unless referring to a code identifier

### Language and Clarity

- Write comments in English unless you're certain the code will never be read by non-speakers of your language.
- Be specific and precise—avoid vague terms like "stuff", "things", "handles it"
- Use consistent terminology throughout your codebase

### Consistency

Follow your team's or project's established commenting conventions. If none exist, create them:

- Where do comments go (above or beside code)?
- How are multi-line comments formatted?
- What tags do you use (TODO, FIXME, HACK, NOTE)?
- How are functions and classes documented?

---

## Documentation Standards by Language

### Python

- Use docstrings for all public modules, functions, classes, and methods
- Follow PEP 257 conventions
- Use `"""triple double quotes"""`

### JavaScript/TypeScript

- Use JSDoc format with `/** */` for documentation
- Include `@param`, `@returns`, `@throws` tags
- Use single-line `//` for brief inline comments

### Java

- Use Javadoc format with `/** */`
- Document all public APIs
- Include `@param`, `@return`, `@throws` tags

### C/C++

- Use `/** */` for documentation (Doxygen compatible)
- Use `//` for inline comments
- Document headers thoroughly

### PHP

- Use PHPDoc format with `/** */`
- Include type hints in comments when not in code
- Document all public methods and properties

---

## Special Comment Tags

Standard tags that many IDEs recognize:

- **TODO:** Work that needs to be done

  ```javascript
  // TODO: Implement caching layer (Priority: High)
  ```

- **FIXME:** Known bugs or problems

  ```python
  # FIXME: Race condition when multiple users edit simultaneously
  ```

- **HACK:** Quick and dirty solutions that need proper implementation

  ```java
  // HACK: Using sleep() until async properly implemented
  ```

- **NOTE:** Important information or warnings

  ```javascript
  // NOTE: Do not change this order—database migration depends on it
  ```

- **OPTIMIZE:** Performance improvement opportunities

  ```python
  # OPTIMIZE: This loop is O(n²) and slows down with large datasets
  ```

- **REVIEW:** Code that needs peer review

  ```javascript
  // REVIEW: Is this the correct calculation for leap years?
  ```

---

## Documentation Tools

Leverage tools to maintain high-quality documentation:

- **Python:** Sphinx, pydoc
- **JavaScript:** JSDoc, TypeDoc
- **Java:** Javadoc
- **C/C++:** Doxygen
- **Multi-language:** Swagger/OpenAPI for APIs

**IDE Extensions:**

- Better Comments (VSCode) - Color-coded comments
- DocBlockr - Auto-generates comment templates
- Kite, Copilot - AI-assisted comment generation

---

## Anti-Patterns: What NOT to Do

### 1. Commenting Out Code

**DON'T DO THIS:**

```javascript
function processData(data) {
  // let result = oldMethod(data);
  // return result;
  return newMethod(data);
}
```

**Instead:** Use version control (Git) to track old code. Delete commented code.

### 2. Excessive Commenting

**DON'T DO THIS:**

```python
# Create a new user object
user = User()
# Set the user's name
user.name = "John"
# Set the user's email
user.email = "john@example.com"
# Save the user to database
user.save()
```

**Instead:** Let clear code speak for itself.

### 3. Redundant Comments

**DON'T DO THIS:**

```java
// Constructor for User class
public User() {
    // Initialize empty user
}
```

### 4. Misleading Comments

**DON'T DO THIS:**

```javascript
// Calculate average
function calculateTotal(values) {
  return values.reduce((sum, val) => sum + val, 0);
}
```

### 5. Vague Comments

**DON'T DO THIS:**

```python
# Fix the bug
value = value + 1
```

**INSTEAD:**

```python
# Increment value by 1 to account for zero-indexing in display
value = value + 1
```

---

## Maintaining Comments

### The Comment Maintenance Cycle

1. **Write:** Add comments when writing new code
2. **Review:** Check comments during code reviews
3. **Update:** Change comments whenever code changes
4. **Delete:** Remove outdated or unnecessary comments

### Signs of Comment Decay

- Comments contradict the code
- Comments reference removed features
- Comments use outdated terminology
- Comments mention deprecated functions

**Prevention:** Remember that comments require maintenance just like code. Treat them as first-class citizens in your codebase.

---

## Comment Quality Checklist

Before committing code, verify your comments:

- [ ] Do comments explain *why*, not *what*?
- [ ] Are comments accurate and up-to-date?
- [ ] Have I avoided redundant comments?
- [ ] Are complex algorithms explained?
- [ ] Are workarounds and hacks documented?
- [ ] Are security concerns highlighted?
- [ ] Are external references linked?
- [ ] Are TODOs converted to issues?
- [ ] Do I follow team conventions?
- [ ] Are comments clear and concise?

---

## Real-World Examples

### Example 1: Algorithm Explanation

**GOOD:**

```python
def find_median(numbers):
    """
    Find median using QuickSelect algorithm.
    
    We use QuickSelect instead of sorting because it's O(n) average case
    compared to O(n log n) for sorting. Since we only need the median
    and not a fully sorted array, this gives us better performance.
    """
    # ... implementation
```

### Example 2: Business Rule

**GOOD:**

```javascript
// Apply 20% discount for orders over $100 as per 2025 promotion
// See: docs/promotions/2025-spring-sale.md
if (orderTotal > 100) {
  discount = orderTotal * 0.20;
}
```

### Example 3: Bug Fix

**GOOD:**

```java
// Bug fix #487: Division by zero when user count is 0
// Previous code crashed when no users were active
if (userCount > 0) {
    averageScore = totalScore / userCount;
} else {
    averageScore = 0;  // Default to 0 when no users
}
```

### Example 4: Performance Note

**GOOD:**

```python
# Cache compiled regex for performance (compiling on every call
# added 200ms overhead per request in production)
PHONE_REGEX = re.compile(r'^\+?1?\d{9,15}$')
```

---

## Final Thoughts

Remember these key principles:

1. **Comments are for humans, not computers**
2. **Explain why, not what**
3. **Keep comments updated or delete them**
4. **Less is more—only comment when necessary**
5. **Use self-documenting code first, comments second**
6. **Bad comments are worse than no comments**

> "A comment is a failure to express yourself in code. If you fail, then write a comment; but try not to fail."  
> — Robert C. Martin (Uncle Bob)

Well-commented code is:

- **Maintainable** - Easy for others to modify
- **Understandable** - Clear to readers months or years later
- **Professional** - Shows care and consideration
- **Collaborative** - Enables team productivity

Great code tells you *what* it does. Great comments tell you *why* it does it.

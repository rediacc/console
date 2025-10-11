# Security Policy

## Supported Versions

We release patches for security vulnerabilities in the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 1.x.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

The Rediacc team takes security bugs seriously. We appreciate your efforts to responsibly disclose your findings and will make every effort to acknowledge your contributions.

### How to Report a Security Vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

Instead, please report them via one of the following methods:

1. **Email**: Send an email to security@rediacc.com with:
   - A description of the vulnerability
   - Steps to reproduce the issue
   - Potential impact of the vulnerability
   - Any suggested fixes (if you have them)

2. **GitHub Security Advisory**: Use GitHub's private security vulnerability reporting feature:
   - Go to https://github.com/rediacc/console/security/advisories
   - Click "New draft security advisory"
   - Fill in the details

### What to Include in Your Report

To help us understand and resolve the issue quickly, please include:

- **Type of issue** (e.g., XSS, CSRF, SQL injection, authentication bypass)
- **Full paths of source file(s)** related to the issue
- **Location of the affected source code** (tag/branch/commit or direct URL)
- **Step-by-step instructions** to reproduce the issue
- **Proof-of-concept or exploit code** (if possible)
- **Impact of the issue**, including how an attacker might exploit it

### Response Timeline

- **Initial Response**: Within 48 hours
- **Status Update**: Within 7 days
- **Fix Timeline**: Depends on severity and complexity
  - Critical: Within 7 days
  - High: Within 30 days
  - Medium: Within 90 days
  - Low: Best effort

### What to Expect

After you submit a report:

1. **Acknowledgment**: We'll confirm receipt of your vulnerability report
2. **Communication**: We'll keep you informed about our progress
3. **Validation**: We'll work to validate and reproduce the issue
4. **Fix Development**: We'll develop and test a fix
5. **Disclosure**: We'll coordinate disclosure timing with you
6. **Credit**: We'll credit you in our security advisory (if you wish)

## Security Update Process

When we receive a security bug report, we will:

1. Confirm the problem and determine affected versions
2. Audit code to find similar problems
3. Prepare fixes for all supported versions
4. Release patches as soon as possible

## Security Best Practices for Contributors

When contributing to the Rediacc Console, please follow these security guidelines:

### Code Security

- **Input Validation**: Always validate and sanitize user inputs
- **Output Encoding**: Properly encode output to prevent XSS
- **Authentication**: Never bypass authentication checks
- **Authorization**: Verify user permissions for all actions
- **Secrets**: Never commit API keys, tokens, or passwords
- **Dependencies**: Keep dependencies up to date
- **Encryption**: Use the vault system for sensitive data

### Examples of What NOT to Do

❌ **Don't** hardcode credentials:
```typescript
const apiKey = "sk_live_1234567890"; // NEVER DO THIS
```

❌ **Don't** trust user input:
```typescript
const html = userInput; // Missing sanitization
element.innerHTML = html; // XSS vulnerability
```

❌ **Don't** expose sensitive data:
```typescript
console.log("User password:", password); // NEVER LOG SECRETS
```

### Examples of What TO Do

✅ **Do** use environment variables:
```typescript
const apiKey = import.meta.env.VITE_API_KEY;
```

✅ **Do** sanitize inputs:
```typescript
const sanitized = DOMPurify.sanitize(userInput);
```

✅ **Do** use the vault system:
```typescript
const encrypted = await encryptVault(sensitiveData, masterPassword);
```

## Known Security Features

The Rediacc Console implements the following security measures:

### Authentication & Authorization

- **Token-based Authentication**: Rotating tokens for API requests
- **Automatic Token Rotation**: New token provided with each response
- **Session Management**: Secure session handling with expiration
- **Permission Checks**: Server-side authorization for all actions

### Data Protection

- **Vault Encryption**: Client-side encryption for sensitive data
- **HTTPS Only**: All communications encrypted in transit
- **Master Password**: Required for vault decryption
- **No Password Storage**: Master passwords never stored or transmitted

### Application Security

- **XSS Protection**: React's built-in XSS protection
- **CSRF Protection**: Token-based CSRF prevention
- **Content Security Policy**: Restrictive CSP headers (when deployed)
- **Dependency Scanning**: Automated vulnerability scanning with Dependabot
- **Input Validation**: Server-side validation for all inputs

### Infrastructure Security

- **GitHub Actions**: Secure CI/CD pipeline
- **Dependabot**: Automated security updates
- **Branch Protection**: Protected main branch
- **Code Review**: Required reviews for all changes
- **Secret Scanning**: Automated secret detection

## Security Disclosure Policy

### Coordinated Disclosure

We follow a coordinated disclosure process:

1. **Report Received**: Security issue reported privately
2. **Investigation**: Issue validated and severity assessed
3. **Fix Development**: Patch developed and tested
4. **Embargo Period**: 90 days to develop and deploy fix
5. **Public Disclosure**: Security advisory published
6. **Credit Given**: Reporter credited (if desired)

### Public Disclosure

After a fix is released, we will:

- Publish a security advisory on GitHub
- Update this SECURITY.md file
- Notify users through appropriate channels
- Credit the reporter (with permission)

## Security Hall of Fame

We'd like to thank the following security researchers for responsibly disclosing vulnerabilities:

*(This section will be updated as we receive and address security reports)*

## Additional Resources

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [GitHub Security Best Practices](https://docs.github.com/en/code-security)
- [React Security Best Practices](https://reactjs.org/docs/dom-elements.html#dangerouslysetinnerhtml)

## Questions?

If you have questions about this security policy, please contact security@rediacc.com.

---

Last Updated: 2025-10-11

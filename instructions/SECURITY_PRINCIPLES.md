# Core Security Principles — Always Follow

These are non-negotiable, foundational principles that apply to every layer of your application at all times.

---

## 1. 🔒 Never Trust Input — Validate Everything

**Treat all input as hostile by default** — from users, APIs, files, databases, environment variables, and even your own LLM's output.

- Validate type, length, format, and range on every input
- Reject anything that doesn't match an explicit allowlist
- Never trust client-supplied values for security decisions (roles, IDs, permissions)
- Sanitize before storing, and encode before rendering

> **RAG context:** User queries AND document content ingested into the knowledge base are both untrusted inputs.

---

## 2. 🔑 Least Privilege — Always

**Every component, user, and service should have only the minimum permissions needed to do its job — nothing more.**

- Database users have only the tables/operations they need
- Cloud IAM roles are scoped per service
- API keys carry the narrowest possible scope
- LLM tool/function call permissions are explicitly restricted
- Users can only access data they are authorized to see

> If a component is compromised, least privilege limits the blast radius.

---

## 3. 🛡️ Defense in Depth — Never Rely on One Layer

**Assume every single security control will eventually fail. Layer your defenses so that no single failure leads to a breach.**

- Auth check at the API gateway AND the service AND the database
- Input validation on the client AND the server
- ACLs at the UI layer AND the retrieval layer AND the storage layer
- Encryption in transit AND at rest
- Monitoring AND alerting AND incident response

> One lock on the door is not enough. Build walls, not just doors.

---

## 4. 🚫 Fail Securely — Default to Deny

**When something goes wrong, the system must fail in a safe state — not an open one.**

- If auth check fails → deny access, never grant it
- If a permission is ambiguous → deny by default
- If an error occurs → return a generic message to the user, log details server-side
- If a dependency is unavailable → block the request, don't bypass security checks

> Never write fallback logic that grants access when a security check errors out.

---

## 5. 🔐 Protect Secrets — Absolute Rule

**Secrets (API keys, passwords, tokens, certificates) must never appear in code, logs, client-side code, or version control. Ever.**

- Use a secrets manager (Vault, AWS Secrets Manager, etc.) — never `.env` files committed to git
- Rotate secrets regularly and immediately after any suspected exposure
- Never log secrets, even partially
- All LLM/vector DB API calls are server-side only — keys never reach the browser

> A secret seen once is a secret compromised.

---

## 6. 📉 Minimize Attack Surface — Remove What You Don't Need

**Every unused feature, open port, enabled service, dependency, and endpoint is a potential entry point.**

- Disable unused API endpoints, HTTP methods, and features
- Remove unused dependencies; pin the ones you keep
- Close all ports not required for the application
- Delete unused accounts, keys, and access tokens
- Keep the knowledge base to only what users genuinely need

> The safest code is the code that doesn't exist.

---

## 7. 🔍 Audit Everything — Assume You Will Be Breached

**Log actions comprehensively so you can detect attacks, investigate incidents, and prove compliance.**

- Log every auth event (success and failure), every privilege escalation, every data access
- Log RAG queries with user ID, retrieved chunk IDs, and timestamp — redact PII
- Never log secrets or full sensitive payloads
- Set up alerting for anomalies (repeated failures, unusual query volumes, off-hours access)
- Regularly review and test your logs — silent failures are dangerous

> If it wasn't logged, it didn't happen.

---

## 8. 🔄 Keep Dependencies Updated — Always

**Vulnerabilities in dependencies are one of the most common real-world attack vectors.**

- Run automated vulnerability scanning (Dependabot, Snyk) in every CI/CD pipeline
- Pin dependency versions with lock files
- Update dependencies on a regular schedule, not only when convenient
- Monitor CVE databases for critical packages you depend on

> Outdated libraries are open doors.

---

## 9. 🧪 Test Security — Continuously

**Security is not a one-time audit. It must be built into the development lifecycle.**

- Run SAST tools on every commit
- Test for OWASP Top 10 vulnerabilities before every release
- Include prompt injection and data exfiltration tests in your RAG test suite
- Conduct penetration testing at least annually
- Treat security bugs with the same (or higher) priority as functional bugs

> If you don't break it first, someone else will.

---

## 10. 🏗️ Separation of Concerns — Isolate Everything

**Security boundaries must match architectural boundaries. Components should not share more access than necessary.**

- Frontend never has direct DB or vector store access
- LLM orchestration service is isolated from core business logic
- Each microservice authenticates independently — no implicit trust between services
- Tenant data is strictly namespaced and isolated at the storage level
- Production, staging, and dev environments are completely separated

> Shared access means shared risk.

---

## The Golden Rules — At a Glance

| # | Principle | One-Line Rule |
|---|---|---|
| 1 | Validate Everything | All input is hostile until proven safe |
| 2 | Least Privilege | Grant only what is absolutely necessary |
| 3 | Defense in Depth | Never rely on a single security control |
| 4 | Fail Securely | Errors must deny, never grant |
| 5 | Protect Secrets | Secrets never touch code, logs, or the client |
| 6 | Minimize Attack Surface | Remove everything you don't actively need |
| 7 | Audit Everything | Log actions; monitor anomalies |
| 8 | Keep Dependencies Updated | Scan and patch continuously |
| 9 | Test Security | Break it yourself before others do |
| 10 | Separate Concerns | Isolate components and trust boundaries |

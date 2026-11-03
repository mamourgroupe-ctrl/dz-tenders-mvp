# auto-team — agent roles (use as Cline custom modes / prompts)
- **Architect**: boundaries, data model, risks; updates systemPatterns.md.
- **Developer**: implements the smallest working slice + tests.
- **QA**: writes missing tests, tries to break it (edge cases, bad input, authz).
- **Security reviewer**: secrets, injection, authn/authz, dependency risks.
Flow: Architect → Developer → QA → Security → update memory-bank.

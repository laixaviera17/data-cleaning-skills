# Security policy

## Supported versions

Security fixes are applied to the latest code on the default branch. The project is currently pre-1.0, so older snapshots are not maintained as separate security release lines.

## Reporting a vulnerability

Do not disclose credentials, personal data, exploitable payloads, or unpatched vulnerability details in a public issue.

Use the repository's GitHub **Security → Report a vulnerability** flow when available. If private vulnerability reporting is unavailable, contact the maintainer through the GitHub profile and request a private channel without including sensitive details in the first message.

Include the affected version or commit, reproduction conditions, impact, and a minimal sanitized proof of concept. You should receive an acknowledgement within seven days. Timelines for validation, remediation, and disclosure depend on severity and maintainer availability.

## Scope

Relevant reports include unsafe file handling, path traversal, archive issues, dependency vulnerabilities with a demonstrated impact, sensitive-data leakage, and ways to bypass rule or artifact validation. General feature requests and malformed input that produces a documented validation error are not security vulnerabilities.

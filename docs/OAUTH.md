# Lunex DevCore OAuth gateway
Private owner profile. Uses MCP SDK OAuth authorization code flow and PKCE (S256).
The owner is prompted for a strong password when the user initiates OAuth from
ChatGPT. OAuth clients are dynamically registered; bearer and refresh tokens are
stored hashed with expiration. Admin secrets and OAuth database are not committed.

Planned public URL: https://rikagro.ru/devcore/mcp
Issuer: https://rikagro.ru/devcore

The gateway runs at 127.0.0.1:18791, never at 0.0.0.0. Configure HTTPS
reverse proxy only after full integration tests. Password hash is SHA256 of a
high-entropy installation password; store a generated random password in a
mode-0600 owner-only secret outside the repository, never in logs.
The owner login flow is not the paid subscription system.

Owner Full Access applies to administrative tools only when those tools exist.
At this stage the only exposed MCP tool is devcore_status.

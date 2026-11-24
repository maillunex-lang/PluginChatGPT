# Lunex DevCore architecture (actual deployed pre-alpha)
Date: 2026-11-24

- A single root-owned systemd service: lunex-devcore.service.
- Source checkout: /opt/lunex-devcore (public repo maillunex-lang/PluginChatGPT).
- Process listens only at 127.0.0.1:18791. Nginx terminates TLS.
- Public MCP endpoint: https://rikagro.ru/devcore/mcp
- OAuth issuer: https://rikagro.ru/devcore, authorization code + PKCE S256.
- OAuth owner login password and credential hash are kept in /etc/lunex-devcore, mode 0600.
- OAuth grants and registered clients persist in /var/lib/lunex-devcore/oauth.db.
- Isolated PostgreSQL 16 in Docker: lunex-devcore-postgres, bound at 127.0.0.1:15465.
- Project/memory/task state stored in separate PostgreSQL database devcore.
- Database credentials are kept on VPS, not committed.
- Owner Full Access tools execute commands as root; no command or filesystem allowlist.
- Existing projects are not to be modified without explicit owner instructions.
- SQLite registry and task queue are older prototypes; PostgreSQL is the live implementation.
- 20 versioned skill catalog entries; deterministic keyword router is not an LLM.
- Background execution of AI-generated code, advanced GameLab, license issuer,
  Android build automation and unattended GitHub push are not yet implemented.
- Commercial Source Available license terms are provisional pending legal review.
- PostgreSQL connection, OAuth and MCP tests run locally. Public metadata/unauthorized
  endpoint are monitored, but a real owner OAuth login must be completed by the owner.

The OAuth implementation is pre-alpha, not independently security audited. Do not
enroll additional external users until authorization and security are reviewed.

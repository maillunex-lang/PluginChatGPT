# Verified progress through 2026-11-24
- DC-00: initial GDD, roadmap, constitution rules, owner profile, commercial baseline docs published. Detailed specifications incomplete.
- DC-01: VPS audit and isolated checkout done.
- DC-02: MCP streamable HTTP with HTTPS nginx route, persistent owner OAuth, PKCE S256, dynamic OAuth client registration, token refresh/revoke, 401 without login. Live ChatGPT client connection not yet user-verified; security audit pending.
- DC-03: Owner Full Access command, file read and atomic write tools implemented; internal tool permission boundaries waived by explicit owner decision.
- DC-04: dedicated PostgreSQL 16 deployed, versioned project memory with source and supersession, project isolation tested. Automatic chat event capture incomplete.
- DC-05: project registry and initial bounded context loader implemented; advanced token index/AST not done.
- DC-06: 20 skill catalog entries and deterministic keyword router implemented; full per-skill playbooks not done.
- DC-07: PostgreSQL queued/running/completed/paused tasks and durable checkpoints; autonomous executor and GitHub auto-push not done.
- DC-08 to DC-15: remain substantially unimplemented.
- DC-13: read-only Doctor checks for service, disk and database (partial).
- DC-13C: commercial terms documented; license issuer and subscription services not implemented.

Evidence: strict pytest suite passes on Lunex; HTTP OAuth metadata returns 200,
MCP requests without credentials return 401; existing Nginx /studio/ and
/gametest/ endpoint response codes unchanged. No VPS reboot.

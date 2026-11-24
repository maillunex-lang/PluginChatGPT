# Installation and operations (current pre-alpha)
The owner deployment is on the Lunex Ubuntu VPS. This describes the current state,
not a verified one-command installer.

Requires Python 3.12+, Docker, an existing TLS-enabled nginx server, and a dedicated
PostgreSQL 16 instance. Clone source into /opt/lunex-devcore, create Python venv and
install requirements. Use a dedicated PostgreSQL database and an isolated localhost
port 15465. Generate a strong owner login password locally and keep its SHA-256
digest and PostgreSQL DSN in a private systemd EnvironmentFile. Never commit secrets.

MCP process command:
    /opt/lunex-devcore/.venv/bin/python -m devcore.owner_gateway

Current environment variable names:
    DEVCORE_ISSUER
    DEVCORE_RESOURCE
    DEVCORE_OAUTH_DB
    DEVCORE_OWNER_PASSWORD_HASH
    DEVCORE_DATABASE_URL

The service binds to 127.0.0.1:18791. Reverse-proxy /devcore/ to this port,
and proxy /.well-known/oauth-protected-resource/devcore/mcp to the resource
metadata endpoint. Validate nginx -t before reloading.

Diagnostics (on VPS):
    systemctl is-active lunex-devcore
    systemctl status lunex-devcore --no-pager
    docker exec lunex-devcore-postgres pg_isready -U devcore -d devcore
    cd /opt/lunex-devcore && .venv/bin/python -m pytest -q -W error

For integration tests, export the private DEVCORE_DATABASE_URL temporarily
in the executing shell; the other tests work without database configuration.
Manual encrypted offsite backups and restore/migration procedures are required
before production use, but are not automated yet.

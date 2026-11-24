"""Single-owner OAuth authorization provider for MCP SDK.

The SDK handles PKCE, client authentication and OAuth metadata. This provider
persists grants in a standalone SQLite database, never in the source tree.
"""
import hashlib
import hmac
import json
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl

from mcp.server.auth.provider import (
    OAuthAuthorizationServerProvider, AuthorizationParams, AuthorizationCode,
    AccessToken, RefreshToken, RegistrationError, TokenError,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

SCOPE = "devcore:read"


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class OwnerOAuthProvider(
    OAuthAuthorizationServerProvider[AuthorizationCode, RefreshToken, AccessToken]
):
    def __init__(self, database: str, issuer: str, owner_hash: str):
        if urlsplit(issuer).scheme != "https":
            raise ValueError("OAuth issuer must use HTTPS")
        if len(owner_hash) != 64:
            raise ValueError("Owner secret digest must be configured")
        self.db = str(Path(database))
        self.issuer = issuer.rstrip("/")
        self.owner_hash = owner_hash
        with self.connect() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS clients (id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS pending (
                    ticket TEXT PRIMARY KEY, client TEXT NOT NULL,
                    data TEXT NOT NULL, expires REAL NOT NULL, attempts INT DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS codes (
                    hash TEXT PRIMARY KEY, client TEXT NOT NULL,
                    data TEXT NOT NULL, expires REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tokens (
                    hash TEXT PRIMARY KEY, client TEXT NOT NULL,
                    kind TEXT NOT NULL, data TEXT NOT NULL, expires REAL NOT NULL
                );
            """)

    @contextmanager
    def connect(self):
        c = sqlite3.connect(self.db, timeout=10)
        try:
            with c:
                yield c
        finally:
            c.close()

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        with self.connect() as c:
            row = c.execute("SELECT data FROM clients WHERE id=?", (client_id,)).fetchone()
        return OAuthClientInformationFull.model_validate_json(row[0]) if row else None

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        if not client_info.client_id:
            raise RegistrationError(error="invalid_client_metadata", error_description="Missing client id")
        with self.connect() as c:
            if c.execute("SELECT count(*) FROM clients").fetchone()[0] >= 64:
                raise RegistrationError(error="invalid_client_metadata", error_description="Registration limit reached")
            c.execute("INSERT INTO clients VALUES (?,?)",
                      (client_info.client_id, client_info.model_dump_json()))

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        if set(params.scopes or []) != {SCOPE}:
            raise ValueError("Only devcore:read is supported")
        ticket = secrets.token_urlsafe(32)
        with self.connect() as c:
            c.execute("INSERT INTO pending(ticket,client,data,expires) VALUES(?,?,?,?)",
                      (digest(ticket), client.client_id, params.model_dump_json(), time.time()+300))
        return f"{self.issuer}/owner/approve/{ticket}"

    def approve(self, ticket: str, password: str) -> str | None:
        with self.connect() as c:
            row = c.execute("SELECT client,data,expires,attempts FROM pending WHERE ticket=?",
                            (digest(ticket),)).fetchone()
            if not row or row[2] < time.time() or row[3] >= 5:
                return None
            c.execute("UPDATE pending SET attempts=attempts+1 WHERE ticket=?", (digest(ticket),))
            if not hmac.compare_digest(digest(password), self.owner_hash):
                return None
            params = AuthorizationParams.model_validate_json(row[1])
            code = secrets.token_urlsafe(32)
            auth_code = AuthorizationCode(
                code=code, client_id=row[0], scopes=[SCOPE],
                expires_at=time.time()+120, code_challenge=params.code_challenge,
                redirect_uri=params.redirect_uri,
                redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
                resource=params.resource, subject="owner"
            )
            c.execute("DELETE FROM pending WHERE ticket=?", (digest(ticket),))
            c.execute("INSERT INTO codes VALUES (?,?,?,?)",
                      (digest(code), row[0], auth_code.model_dump_json(), auth_code.expires_at))
        destination = str(params.redirect_uri)
        u = urlsplit(destination)
        query = dict(parse_qsl(u.query, keep_blank_values=True))
        query["code"] = code
        if params.state is not None:
            query["state"] = params.state
        return urlunsplit((u.scheme,u.netloc,u.path,urlencode(query),u.fragment))

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        with self.connect() as c:
            row = c.execute("SELECT data,expires FROM codes WHERE hash=? AND client=?",
                            (digest(authorization_code), client.client_id)).fetchone()
        if row and row[1] > time.time():
            return AuthorizationCode.model_validate_json(row[0])
        return None

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        with self.connect() as c:
            removed = c.execute("DELETE FROM codes WHERE hash=? AND client=? RETURNING data",
                                (digest(authorization_code.code), client.client_id)).fetchone()
            if not removed:
                raise TokenError(error="invalid_grant", error_description="Code already used")
            access = secrets.token_urlsafe(48)
            refresh = secrets.token_urlsafe(48)
            expires = int(time.time())+3600
            at = AccessToken(token=access, client_id=client.client_id,
                             scopes=[SCOPE], subject="owner", expires_at=expires,
                             resource=authorization_code.resource)
            rt = RefreshToken(token=refresh, client_id=client.client_id,
                              scopes=[SCOPE], subject="owner",
                              expires_at=int(time.time())+7*86400,
                              resource=authorization_code.resource)
            c.execute("INSERT INTO tokens VALUES (?,?,?,?,?)",
                      (digest(access),client.client_id,"access",at.model_dump_json(),expires))
            c.execute("INSERT INTO tokens VALUES (?,?,?,?,?)",
                      (digest(refresh),client.client_id,"refresh",rt.model_dump_json(),rt.expires_at))
        return OAuthToken(access_token=access, refresh_token=refresh, expires_in=3600,
                          scope=SCOPE, token_type="Bearer")

    async def load_access_token(self, token: str) -> AccessToken | None:
        with self.connect() as c:
            row = c.execute("SELECT data,expires FROM tokens WHERE hash=? AND kind='access'",
                            (digest(token),)).fetchone()
        return AccessToken.model_validate_json(row[0]) if row and row[1] > time.time() else None

    async def load_refresh_token(self, client: OAuthClientInformationFull, refresh_token: str) -> RefreshToken | None:
        with self.connect() as c:
            row = c.execute("SELECT data,expires FROM tokens WHERE hash=? AND kind='refresh' AND client=?",
                            (digest(refresh_token),client.client_id)).fetchone()
        return RefreshToken.model_validate_json(row[0]) if row and row[1] > time.time() else None

    async def exchange_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: RefreshToken,
        scopes: list[str]
    ) -> OAuthToken:
        if set(scopes) - set(refresh_token.scopes):
            raise TokenError(error="invalid_scope", error_description="Scope escalation denied")
        with self.connect() as c:
            deleted = c.execute("DELETE FROM tokens WHERE hash=? AND kind='refresh' AND client=?",
                                (digest(refresh_token.token), client.client_id)).rowcount
            if not deleted:
                raise TokenError(error="invalid_grant", error_description="Refresh token already used")
            access = secrets.token_urlsafe(48)
            new_refresh = secrets.token_urlsafe(48)
            expiry = int(time.time())+3600
            at=AccessToken(token=access,client_id=client.client_id,subject="owner",
                           scopes=refresh_token.scopes, expires_at=expiry,
                           resource=refresh_token.resource)
            rt=RefreshToken(token=new_refresh,client_id=client.client_id,subject="owner",
                            scopes=refresh_token.scopes, expires_at=int(time.time())+7*86400,
                            resource=refresh_token.resource)
            c.execute("INSERT INTO tokens VALUES (?,?,?,?,?)",
                      (digest(access),client.client_id,"access",at.model_dump_json(),expiry))
            c.execute("INSERT INTO tokens VALUES (?,?,?,?,?)",
                      (digest(new_refresh),client.client_id,"refresh",rt.model_dump_json(),rt.expires_at))
        return OAuthToken(access_token=access, refresh_token=new_refresh,
                          expires_in=3600, scope=" ".join(refresh_token.scopes),
                          token_type="Bearer")

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        with self.connect() as c:
            c.execute("DELETE FROM tokens WHERE hash=?", (digest(token.token),))

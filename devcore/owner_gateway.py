"""Self-hosted OAuth/PKCE MCP gateway, loopback bound behind HTTPS reverse proxy."""
import os
from urllib.parse import urlsplit
from mcp.server.transport_security import TransportSecuritySettings

from mcp.server.fastmcp import FastMCP
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from starlette.requests import Request
from starlette.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from devcore.owner_oauth import OwnerOAuthProvider, SCOPE
from devcore import __version__
from devcore.owner_tools import register_owner_tools


def create_gateway(db: str, issuer: str, resource: str, owner_hash: str, port: int = 18791, datastore_url: str | None = None):
    if urlsplit(resource).scheme != "https":
        raise ValueError("Resource must be HTTPS")
    provider = OwnerOAuthProvider(db,issuer,owner_hash)
    server = FastMCP(
        "Lunex DevCore", host="127.0.0.1", port=port,
        stateless_http=True, json_response=True, max_request_body_size=65536,
        auth_server_provider=provider,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=["127.0.0.1:*", "localhost:*", urlsplit(issuer).netloc],
            allowed_origins=["http://127.0.0.1:*", "http://localhost:*",
                             "https://rikagro.ru", "https://chatgpt.com",
                             "https://chat.openai.com"],
        ),
        auth=AuthSettings(
            issuer_url=issuer, resource_server_url=resource,
            required_scopes=[SCOPE],validate_token_resource=True,
            client_registration_options=ClientRegistrationOptions(
                enabled=True,valid_scopes=[SCOPE],default_scopes=[SCOPE]),
            revocation_options=RevocationOptions(enabled=True),
        ),
    )
    def devcore_status() -> dict:
        """Report live HTTP gateway features and development version."""
        return {"version":__version__, "status":"development",
                "remote_enabled":True, "auth":"OAuth 2.1 PKCE",
                "capabilities":["status","projects","tasks","memory",
                                "owner_access","skills","doctor","code_index"] if datastore_url else ["status"]}
    server.tool()(devcore_status)
    if datastore_url:
        register_owner_tools(server,datastore_url)

    @server.custom_route("/owner/approve/{ticket}", methods=["GET","POST"])
    async def approval(request: Request):
        ticket = request.path_params["ticket"]
        headers = {"Cache-Control":"no-store", "X-Frame-Options":"DENY",
                   "Content-Security-Policy":"default-src 'none'; form-action 'self'; style-src 'unsafe-inline'"}
        if request.method == "GET":
            markup = """<!doctype html><html><meta charset="utf-8"><title>Lunex DevCore authorization</title>
            <style>body{font-family:sans-serif;max-width:26rem;margin:6rem auto;padding:1rem}</style>
            <h2>Authorize Lunex DevCore</h2><p>Only approve an authorization you initiated.</p>
            <form method="post"><input type="password" name="password" autocomplete="current-password"
            autofocus required><button type="submit">Authorize</button></form></html>"""
            return HTMLResponse(markup, headers=headers)
        if int(request.headers.get("content-length","0")) > 4096:
            return PlainTextResponse("Request too large",status_code=413,headers=headers)
        data=await request.form()
        password=data.get("password","")
        if not isinstance(password,str):
            return PlainTextResponse("Invalid request",status_code=400,headers=headers)
        redirect=provider.approve(ticket,password)
        if redirect is None:
            return PlainTextResponse("Authorization denied",status_code=403,headers=headers)
        return RedirectResponse(redirect,status_code=303,headers=headers)

    return server


if __name__ == "__main__":
    create_gateway(os.environ["DEVCORE_OAUTH_DB"], os.environ["DEVCORE_ISSUER"],
                   os.environ["DEVCORE_RESOURCE"],
                   os.environ["DEVCORE_OWNER_PASSWORD_HASH"],
                   datastore_url=os.environ.get("DEVCORE_DATABASE_URL")).run(transport="streamable-http")

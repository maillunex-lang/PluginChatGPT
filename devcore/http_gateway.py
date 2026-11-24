"""Loopback-only MCP resource server. External OAuth issuer required."""
import os
from urllib.parse import urlsplit
import jwt
from jwt import PyJWKClient
from mcp.server.fastmcp import FastMCP
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from devcore.gateway import devcore_status
import anyio

class Verifier:
    def __init__(self, issuer, audience, jwks):
        for url in (issuer, audience, jwks):
            if urlsplit(url).scheme != 'https' or not urlsplit(url).hostname:
                raise ValueError('HTTPS URLs required')
        self.issuer, self.audience = issuer, audience
        self.keys = PyJWKClient(jwks, timeout=5)

    def decode(self, token):
        key = self.keys.get_signing_key_from_jwt(token).key
        return jwt.decode(token, key, algorithms=['RS256'], issuer=self.issuer,
                          audience=self.audience, options={'require':['exp','iss','aud','sub']})

    async def verify_token(self, token):
        try:
            claims = await anyio.to_thread.run_sync(self.decode, token)
            scopes = claims.get('scope', '')
            if not isinstance(scopes, str) or 'devcore:read' not in scopes.split():
                return None
            return AccessToken(token=token, client_id=claims.get('client_id',claims['sub']),
                               subject=claims['sub'], scopes=scopes.split(), expires_at=claims['exp'])
        except (jwt.PyJWTError, ValueError, TypeError, KeyError, OSError):
            return None

def create_server(issuer, audience, jwks, port=18791):
    verifier = Verifier(issuer, audience, jwks)
    server = FastMCP('Lunex DevCore', host='127.0.0.1', port=port,
                     stateless_http=True, json_response=True, max_request_body_size=65536,
                     token_verifier=verifier,
                     auth=AuthSettings(issuer_url=issuer, resource_server_url=audience,
                                       required_scopes=['devcore:read'], validate_token_resource=False))
    server.tool()(devcore_status)
    return server

if __name__ == '__main__':
    create_server(os.environ['DEVCORE_ISSUER'], os.environ['DEVCORE_AUDIENCE'],
                  os.environ['DEVCORE_JWKS']).run(transport='streamable-http')

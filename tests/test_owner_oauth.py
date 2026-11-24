import asyncio
import base64
import hashlib
import json
import time
from urllib.parse import urlparse,parse_qs

import pytest
from mcp.server.auth.provider import AuthorizationParams
from mcp.shared.auth import OAuthClientInformationFull
from starlette.testclient import TestClient
from devcore.owner_oauth import OwnerOAuthProvider,digest
from devcore.owner_gateway import create_gateway

ISS="https://rikagro.ru/devcore"
RESOURCE=ISS+"/mcp"
CALLBACK="https://example.org/callback"

def run(coroutine):
    return asyncio.run(coroutine)

def make_client():
    return OAuthClientInformationFull(client_id="test-client",redirect_uris=[CALLBACK],
                                      token_endpoint_auth_method="none",scope="devcore:read")

def make_params():
    verifier="a"*48
    challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return AuthorizationParams(state="test-state",scopes=["devcore:read"],
                               code_challenge=challenge,redirect_uri=CALLBACK,
                               redirect_uri_provided_explicitly=True,resource=RESOURCE)

def test_oauth_flow_and_replay(tmp_path):
    db=str(tmp_path/"auth.sqlite")
    provider=OwnerOAuthProvider(db,ISS,digest("owner-pass"))
    client=make_client()
    run(provider.register_client(client))
    assert run(provider.get_client(client.client_id)).client_id==client.client_id
    url=run(provider.authorize(client,make_params()))
    ticket=url.rsplit("/",1)[-1]
    assert provider.approve(ticket,"wrong") is None
    redirect=provider.approve(ticket,"owner-pass")
    assert redirect is not None
    query=parse_qs(urlparse(redirect).query)
    assert query["state"]==["test-state"]
    code=query["code"][0]
    assert provider.approve(ticket,"owner-pass") is None
    grant=run(provider.load_authorization_code(client,code))
    assert grant.code==code
    tokens=run(provider.exchange_authorization_code(client,grant))
    assert run(provider.load_access_token(tokens.access_token)).subject=="owner"
    assert run(provider.load_refresh_token(client,tokens.refresh_token)).subject=="owner"
    with pytest.raises(Exception):
        run(provider.exchange_authorization_code(client,grant))
    refreshed=run(provider.exchange_refresh_token(
        client,run(provider.load_refresh_token(client,tokens.refresh_token)),["devcore:read"]))
    assert run(provider.load_refresh_token(client,tokens.refresh_token)) is None
    assert run(provider.load_access_token(refreshed.access_token))
    run(provider.revoke_token(run(provider.load_access_token(refreshed.access_token))))
    assert run(provider.load_access_token(refreshed.access_token)) is None

def test_http_routes_and_authorization(tmp_path):
    gateway=create_gateway(str(tmp_path/"oauth.db"),ISS,RESOURCE,digest("owner-pass"))
    app=gateway.streamable_http_app()
    with TestClient(app,base_url="http://127.0.0.1:18791") as client:
        meta=client.get("/.well-known/oauth-authorization-server")
        assert meta.status_code==200
        assert meta.json()["issuer"]==ISS
        request=client.post("/mcp",json={"jsonrpc":"2.0","id":1,"method":"tools/list"},
                            headers={"Accept":"application/json, text/event-stream"})
        assert request.status_code==401
        response=client.get("/owner/approve/missing")
        assert response.status_code==200
        response=client.post("/owner/approve/missing",data={"password":"owner-pass"})
        assert response.status_code==403
        assert client.get("/register").status_code in (404,405)

def test_owner_password_invalid(tmp_path):
    with pytest.raises(ValueError):
        OwnerOAuthProvider(str(tmp_path/"x.db"),"http://localhost","f"*64)
    with pytest.raises(ValueError):
        OwnerOAuthProvider(str(tmp_path/"x.db"),ISS,"")


def test_complete_pkce_http_flow(tmp_path):
    gateway=create_gateway(str(tmp_path/"full.db"),ISS,RESOURCE,digest("owner-pass"))
    with TestClient(gateway.streamable_http_app(),base_url="http://127.0.0.1:18791",
                    follow_redirects=False) as browser:
        registration=browser.post("/register",json={
            "redirect_uris":[CALLBACK],
            "token_endpoint_auth_method":"none",
            "grant_types":["authorization_code","refresh_token"],
            "response_types":["code"],
            "scope":"devcore:read",
            "client_name":"DevCore Integration Test",
        })
        assert registration.status_code==201,registration.text
        client=registration.json()
        verifier="a"*48
        challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        auth=browser.get("/authorize",params={
            "client_id":client["client_id"],
            "redirect_uri":CALLBACK,
            "response_type":"code",
            "scope":"devcore:read",
            "state":"csrf-state",
            "code_challenge":challenge,
            "code_challenge_method":"S256",
            "resource":RESOURCE,
        })
        assert auth.status_code in (302,303),auth.text
        approve_path=urlparse(auth.headers["location"]).path.replace("/devcore","")
        assert approve_path.startswith("/owner/approve/")
        denied=browser.post(approve_path,data={"password":"wrong"})
        assert denied.status_code==403
        granted=browser.post(approve_path,data={"password":"owner-pass"})
        assert granted.status_code==303
        grant=parse_qs(urlparse(granted.headers["location"]).query)
        assert grant["state"]==["csrf-state"]
        code=grant["code"][0]
        request_data={
            "grant_type":"authorization_code",
            "client_id":client["client_id"],
            "code":code,
            "redirect_uri":CALLBACK,
            "code_verifier":verifier,
            "resource":RESOURCE,
        }
        wrong=browser.post("/token",data=request_data|{"code_verifier":"x"*48})
        assert wrong.status_code==400
        token=browser.post("/token",data=request_data)
        assert token.status_code==200,token.text
        access=token.json()["access_token"]
        second=browser.post("/token",data=request_data)
        assert second.status_code==400
        headers={"Authorization":"Bearer "+access,
                 "Accept":"application/json, text/event-stream",
                 "Content-Type":"application/json",
                 "MCP-Protocol-Version":"2025-06-18"}
        initialize=browser.post("/mcp",json={"jsonrpc":"2.0","id":1,"method":"initialize",
            "params":{"protocolVersion":"2025-06-18","capabilities":{},
                      "clientInfo":{"name":"test","version":"1"}}},headers=headers)
        assert initialize.status_code==200,initialize.text
        tools=browser.post("/mcp",json={"jsonrpc":"2.0","id":2,"method":"tools/list"},headers=headers)
        assert tools.status_code==200,tools.text
        assert "devcore_status" in tools.text

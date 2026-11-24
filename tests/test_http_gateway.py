import time
import asyncio
from types import SimpleNamespace
from unittest.mock import Mock
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from starlette.testclient import TestClient
from devcore.http_gateway import Verifier, create_server

ISS='https://issuer.example'
AUD='https://devcore.example/mcp'
JWKS=ISS+'/jwks'

def test_https_required():
    with pytest.raises(ValueError):
        Verifier('http://issuer.example',AUD,JWKS)

def test_tokens():
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    v=Verifier(ISS,AUD,JWKS)
    v.keys=Mock()
    v.keys.get_signing_key_from_jwt.return_value=SimpleNamespace(key=key.public_key())
    claims=dict(iss=ISS,aud=AUD,sub='owner',exp=int(time.time())+60,scope='devcore:read')
    def verify(**changes):
        return asyncio.run(v.verify_token(jwt.encode(claims|changes,key,algorithm='RS256')))
    assert verify().subject=='owner'
    assert verify(aud='wrong') is None
    assert verify(iss='wrong') is None
    assert verify(exp=1) is None
    assert verify(scope='other') is None
    assert asyncio.run(v.verify_token('invalid')) is None

def test_http_unauthorized():
    app=create_server(ISS,AUD,JWKS).streamable_http_app()
    with TestClient(app,base_url='http://127.0.0.1:18791') as client:
        response=client.post('/mcp',json={'jsonrpc':'2.0','id':1,'method':'tools/list'},headers={'Accept':'application/json, text/event-stream'})
        assert response.status_code==401

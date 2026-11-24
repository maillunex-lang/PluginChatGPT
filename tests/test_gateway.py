import asyncio
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from devcore.gateway import devcore_status

def test_status():
    assert devcore_status()['remote_enabled'] is False

def test_protocol():
    async def run():
        async with stdio_client(StdioServerParameters(command=sys.executable,args=['-m','devcore.gateway'])) as (r,w):
            async with ClientSession(r,w) as s:
                await s.initialize()
                tools=await s.list_tools()
                assert [t.name for t in tools.tools]==['devcore_status']
                result=await s.call_tool('devcore_status',{})
                assert not result.isError
    asyncio.run(run())

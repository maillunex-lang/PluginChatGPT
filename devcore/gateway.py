from mcp.server.fastmcp import FastMCP
from devcore import __version__

mcp = FastMCP('Lunex DevCore', host='127.0.0.1', stateless_http=True, json_response=True)

@mcp.tool()
def devcore_status() -> dict:
    """Report implemented capabilities, not planned functionality."""
    return {'version': __version__, 'status': 'development', 'capabilities': ['status'], 'remote_enabled': False}

if __name__ == '__main__':
    # Local stdio only until OAuth and network security are implemented.
    mcp.run(transport='stdio')

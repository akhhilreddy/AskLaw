import asyncio

from mcp.server.mcpserver import MCPServer


# =========================================================
# ASKLAW MCP SERVER
# =========================================================

server = MCPServer(
    name="AskLaw MCP",
    version="1.0.0",
    description="MCP server for the AskLaw legal research system.",
)


# =========================================================
# HEALTH CHECK
# =========================================================

@server.tool()
def health_check() -> dict:
    """
    Check whether the AskLaw MCP server is running.
    """

    return {
        "status": "ok",
        "service": "AskLaw MCP",
        "version": "1.0.0",
    }


# =========================================================
# ECHO
# =========================================================

@server.tool()
def echo(message: str) -> dict:
    """
    Test MCP tool communication.
    """

    return {
        "message": message,
    }


# =========================================================
# MAIN
# =========================================================

async def main():
    print("=" * 60)
    print("ASKLAW MCP SERVER")
    print("=" * 60)
    print("Starting MCP server...")
    print("URL: http://127.0.0.1:8001/mcp")
    print("=" * 60)

    await server.run_streamable_http_async(
        host="127.0.0.1",
        port=8001,
        streamable_http_path="/mcp",
        stateless_http=True,
    )


# =========================================================
# ENTRY POINT
# =========================================================

if __name__ == "__main__":
    asyncio.run(main())
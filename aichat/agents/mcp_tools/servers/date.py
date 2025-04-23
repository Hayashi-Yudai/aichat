from datetime import datetime

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("date")


@mcp.tool()
def get_current_date() -> str:
    """Get the current date and time."""

    now = datetime.now()
    return now.strftime("%Y-%m-%d %H:%M:%S")


if __name__ == "__main__":
    mcp.run(transport="stdio")

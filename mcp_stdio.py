"""Run the content rewards MCP server over stdio.

Usage: python mcp_stdio.py
Claude Code: claude mcp add sovsrc-rewards -- python /path/to/mcp_stdio.py
"""
from server import mcp

if __name__ == "__main__":
    mcp.run(transport="stdio")

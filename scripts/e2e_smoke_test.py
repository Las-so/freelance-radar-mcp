"""Real end-to-end smoke test: launches the server as an actual MCP client
would (stdio subprocess), does the MCP handshake, lists tools, and calls
score_opportunities with a real query against the live API.

This is not a unit test — it's the "does this actually work as a client
would use it" proof, run once before calling the build done.
"""

import asyncio
import json
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import get_default_environment, stdio_client


async def main() -> None:
    # The MCP stdio client deliberately spawns servers with a minimal env
    # (HOME/PATH/SHELL/TERM only) rather than inheriting everything the
    # launching process has — a real security default, not a bug. In this
    # sandboxed environment that also strips SSL_CERT_FILE, which points at
    # the proxy's CA bundle, so it has to be forwarded explicitly here to
    # reach the live API through the proxy. On a normal machine (e.g. inside
    # Claude Desktop's mcp config) there's no such proxy and nothing extra
    # is needed unless you're enabling Adzuna, which needs its two env vars
    # listed the same way.
    env = get_default_environment()
    if cert := os.environ.get("SSL_CERT_FILE"):
        env["SSL_CERT_FILE"] = cert

    params = StdioServerParameters(command=sys.executable, args=["-m", "freelance_radar_mcp.server"], env=env)

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("TOOLS:", [t.name for t in tools.tools])

            status = await session.call_tool("source_status", {})
            print("SOURCE_STATUS:")
            print(status.content[0].text)

            result = await session.call_tool(
                "score_opportunities",
                {
                    "capability_keywords": ["python", "automation", "api integration", "mcp"],
                    "query": "automation",
                    "limit": 5,
                },
            )
            payload = json.loads(result.content[0].text)
            print(f"\nSCORE_OPPORTUNITIES: sources_used={payload['sources_used']} "
                  f"sources_skipped={payload['sources_skipped']} count={payload['count']}")
            for j in payload["ranked"][:3]:
                print(f"  [{j['score']:>3}] {j['title']} — {j['company']} ({j['source']}) matched={j['matched_keywords']}")

            assert payload["count"] > 0, "expected at least one real job back from the live API"
            assert "remotive" in payload["sources_used"], "remotive must be a used source"
            print("\nE2E_SMOKE_TEST: PASS")


if __name__ == "__main__":
    asyncio.run(main())

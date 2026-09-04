# Headroom Markdown Analysis Rule

Whenever any markdown file (.md) is read, reviewed, or analyzed:
1. First route the content through Headroom using `call_mcp_tool(ServerName="headroom", ToolName="headroom_compress", Arguments={"content": ...})`.
2. Use the compressed representation and retrieval hash for context-optimized analysis.
3. If full uncompressed segments are required, fetch via `headroom_retrieve(hash=...)`.

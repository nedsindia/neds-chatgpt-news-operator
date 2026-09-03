# Deployment checklist

1. Create a **new standalone service/project** named something like `neds-chatgpt-news-operator`.
2. Do NOT deploy this package into `neds-cms` or `neds-official-website`.
3. Configure HTTPS.
4. Add environment variables from `.env.example` securely in the hosting provider.
5. Keep `NEDS_OPERATOR_PUBLISH_ENABLED=false` for initial testing.
6. Test read operations first: portal settings, categories, existing news, get news.
7. Test draft creation and media upload.
8. Test submit/review workflow.
9. Only after verification, enable publishing.
10. Connect the remote MCP endpoint to ChatGPT Developer Mode/custom app on an eligible workspace.

The MCP endpoint is exposed by the FastMCP server at its streamable HTTP endpoint (normally `/mcp`).

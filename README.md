# NEDS India 24x7 — ChatGPT News Operator

Standalone MCP gateway for ChatGPT to operate the existing NEDS News CMS. This is **not** an AI news engine and is intentionally separate from `neds-cms`.

## What it exposes
- get_portal_settings
- get_categories
- search_existing_news
- get_news
- create_news
- update_news
- upload_media_from_url
- submit_news
- publish_news
- verify_published_news

ChatGPT remains responsible for web research, source verification, original Hindi writing, SEO, and image generation/selection. The gateway only performs controlled CMS operations.

## Security
Set `NEDS_OPERATOR_API_KEY` for the MCP gateway. Set CMS credentials as server environment variables; never put them in ChatGPT prompts.

Publishing is disabled by default. Set `NEDS_OPERATOR_PUBLISH_ENABLED=true` only after testing.

## Deployment
This server needs a public HTTPS endpoint. Deploy it as a **separate** service/project from both `neds-cms` and `neds-official-website`.

Recommended environment variables:
- `NEDS_OPERATOR_API_KEY`
- `CMS_BASE_URL` (example: `https://news.nedsindia.com`)
- `CMS_LOGIN_EMAIL`
- `CMS_LOGIN_PASSWORD`
- `NEDS_OPERATOR_PUBLISH_ENABLED=false`
- `NEDS_PORTAL_SLUG` (optional; otherwise read from CMS settings)

## ChatGPT
OpenAI currently documents full MCP write/modify support for Business, Enterprise and Edu workspaces. Pro can connect custom MCPs with read/fetch permissions, but full write support is not currently available there. Custom MCP apps are also web-only. See OpenAI's current documentation before enabling production write access.

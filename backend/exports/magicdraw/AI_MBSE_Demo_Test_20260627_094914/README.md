# MagicDraw Exchange Package

- Root package: `AI_MBSE_Demo_Test`
- Element count: `21`
- Relationship count: `25`

Use `magicdraw_exchange.json` as the primary payload for a MagicDraw/Cameo OpenAPI bridge plugin.
`elements.csv` and `relationships.csv` are fallback review/import tables.

Suggested bridge endpoint contract:

- `GET /api/health` returns bridge status.
- `POST /api/models/import` consumes this JSON payload and creates/reuses model elements in MagicDraw.
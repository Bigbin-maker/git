# MagicDraw Exchange Package

- Root package: `PREVIEW_LEO_Satellite_Internet_100_SysML`
- Element count: `38`
- Relationship count: `34`
- Diagram layout: `AI_MBSE_Trace_View`

Use `magicdraw_exchange.json` as the primary payload for a MagicDraw/Cameo OpenAPI bridge plugin.
`diagram_layout.json` is the shared canvas layout used by both MagicDraw Bridge and the frontend.
`elements.csv` and `relationships.csv` are fallback review/import tables.

Suggested bridge endpoint contract:

- `GET /api/health` returns bridge status.
- `POST /api/models/import` consumes this JSON payload and creates/reuses model elements in MagicDraw.
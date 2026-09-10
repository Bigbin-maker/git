# MagicDraw Exchange Package

- Root package: `PREVIEW_LEO_Satellite_Internet`
- Element count: `39`
- Relationship count: `23`
- Diagram layout: `AI_MBSE_Trace_View`
- Additional diagram views: `0`

Use `magicdraw_exchange.json` as the primary payload for a MagicDraw/Cameo OpenAPI bridge plugin.
`diagram_layout.json` is the shared canvas layout used by both MagicDraw Bridge and the frontend.
`diagram_views.json` contains scoped use-case and internal block diagram layouts.
`elements.csv` and `relationships.csv` are fallback review/import tables.

Suggested bridge endpoint contract:

- `GET /api/health` returns bridge status.
- `POST /api/models/import` consumes this JSON payload and creates/reuses model elements in MagicDraw.
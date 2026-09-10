# MagicDraw Exchange Package

- Root package: `LEO_Satellite_Internet_MBSE`
- Element count: `26`
- Relationship count: `25`
- Diagram layout: `AI_MBSE_Trace_View`

Use `magicdraw_exchange.json` as the primary payload for a MagicDraw/Cameo OpenAPI bridge plugin.
`diagram_layout.json` is the shared canvas layout used by both MagicDraw Bridge and the frontend.
`elements.csv` and `relationships.csv` are fallback review/import tables.

Suggested bridge endpoint contract:

- `GET /api/health` returns bridge status.
- `POST /api/models/import` consumes this JSON payload and creates/reuses model elements in MagicDraw.
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../frontend"
if command -v npm >/dev/null 2>&1; then
  if [ ! -d node_modules ]; then npm install; fi
  npm run dev
else
  if [ ! -d node_modules ]; then pnpm install; fi
  pnpm run dev
fi

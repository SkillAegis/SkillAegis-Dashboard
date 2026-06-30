#!/bin/bash
# Dev-only: serve synthetic dashboard data on :4001 (no MISP/ZMQ/scenarios).
# Run this INSTEAD of ./start.sh, then `npm run dev` and open :5173.
[ -f "backend/venv/bin/activate" ] && source backend/venv/bin/activate
[ -f "venv/bin/activate" ] && source venv/bin/activate
exec python3 backend/dev_mock_server.py "$@"   # --players N --tick S --unauth --port P

#!/usr/bin/env bash
set -a
source .env
set +a

export DATABASE_URL=sqlite:///./dev.db
python3 -m uvicorn src.api.app:app --reload --host 127.0.0.1 --port 8000

#!/usr/bin/env bash
export DATABASE_URL=sqlite:///./dev.db
python -m src.api.app

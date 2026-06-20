#!/bin/bash

source .venv/bin/activate
: "${GOOGLE_CLIENT_ID:?Set GOOGLE_CLIENT_ID before running start.sh}"
: "${GOOGLE_CLIENT_SECRET:?Set GOOGLE_CLIENT_SECRET before running start.sh}"
: "${SESSION_SECRET:?Set SESSION_SECRET before running start.sh}"
: "${BETA_UNLOCK_ALL_FEATURES:=true}"
export BETA_UNLOCK_ALL_FEATURES
python run.py

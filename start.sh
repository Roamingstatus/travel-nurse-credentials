#!/bin/bash

source .venv/bin/activate
: "${GOOGLE_CLIENT_ID:?Set GOOGLE_CLIENT_ID before running start.sh}"
: "${GOOGLE_CLIENT_SECRET:?Set GOOGLE_CLIENT_SECRET before running start.sh}"
: "${SESSION_SECRET:?Set SESSION_SECRET before running start.sh}"
python run.py

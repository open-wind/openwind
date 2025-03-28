#!/bin/bash

if [ -f ".env" ]; then
    . ./.env
fi

. venv/bin/activate
python3 openwind.py "$@"

#!/usr/bin/env bash
# Аватар-хост — запуск на Linux/macOS
set -e
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt
# Свой PIN пульта: export ADMIN_PIN=1234
# Интернет-режим:  export PUBLIC_URL=https://xxx.trycloudflare.com
exec .venv/bin/python server.py

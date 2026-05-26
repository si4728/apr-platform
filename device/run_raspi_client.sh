#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
exec ./.venv/bin/python raspi_iot_publisher.py --config client.config

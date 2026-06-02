#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
exec ./.venv/bin/python raspi_system_metrics_publisher.py --config system_metrics.config

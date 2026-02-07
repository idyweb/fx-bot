#!/bin/bash

source /scripts/02-common.sh

log_message "RUNNING" "06-install-libraries.sh"

# Install MetaTrader5 library in Windows
log_message "INFO" "Upgrading pip in Windows Python..."
$wine_executable python -m pip install --upgrade pip --quiet

log_message "INFO" "Installing MetaTrader5 library and dependencies in Windows"
# Use --ignore-installed to avoid permission issues with locked files in Wine
$wine_executable python -m pip install --ignore-installed --no-cache-dir -r /app/requirements.txt
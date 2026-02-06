#!/bin/bash

source /scripts/02-common.sh

log_message "RUNNING" "06-install-libraries.sh"

# Install MetaTrader5 library in Windows if not installed
log_message "INFO" "Installing MetaTrader5 library and dependencies in Windows"
log_message "INFO" "Installing MetaTrader5 library and dependencies in Windows"
# Force reinstall to ensure we match specific versions in requirements.txt
$wine_executable python -m pip install --force-reinstall --no-cache-dir -r /app/requirements.txt
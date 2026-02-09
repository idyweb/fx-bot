#!/bin/bash

source /scripts/02-common.sh

log_message "RUNNING" "06-install-libraries.sh"

# Install MetaTrader5 library in Windows
REQ_FILE="/app/requirements.txt"
HASH_FILE="/config/.requirements_hash"
CURRENT_HASH=$(md5sum "$REQ_FILE" | awk '{ print $1 }')

if [ -f "$HASH_FILE" ]; then
    SAVED_HASH=$(cat "$HASH_FILE")
    if [ "$CURRENT_HASH" == "$SAVED_HASH" ]; then
        log_message "INFO" "Requirements unchanged (Hash: $CURRENT_HASH). Skipping installation."
        exit 0
    fi
fi

log_message "INFO" "Upgrading pip in Windows Python..."
$wine_executable python -m pip install --upgrade pip --quiet

log_message "INFO" "Installing MetaTrader5 library and dependencies in Windows (Hash: $CURRENT_HASH)"
# Removed --no-cache-dir to allow pip to use local cache if available
if $wine_executable python -m pip install --ignore-installed -r "$REQ_FILE"; then
    echo "$CURRENT_HASH" > "$HASH_FILE"
    log_message "INFO" "Libraries installed successfully."
else
    log_message "ERROR" "Failed to install libraries!"
    exit 1
fi
#!/bin/bash

source /scripts/02-common.sh

log_message "RUNNING" "05-install-python.sh"

# Install Python in Wine if not present
if ! $wine_executable python --version > /dev/null 2>&1; then
    log_message "INFO" "Installing Python in Wine..."
    
    # Download with retries and skip cert check if needed
    if wget --no-check-certificate -O /tmp/python-installer.exe $python_url; then
        log_message "INFO" "Installer downloaded successfully. Size: $(du -h /tmp/python-installer.exe | cut -f1)"
    else
        log_message "ERROR" "Failed to download Python installer!"
        exit 1
    fi

    # Install Python
    $wine_executable /tmp/python-installer.exe /quiet InstallAllUsers=1 PrependPath=1 Include_test=0
    
    # Basic check if python works now
    if ! $wine_executable python --version > /dev/null 2>&1; then
        log_message "ERROR" "Python installation failed or not found in path!"
        # rm /tmp/python-installer.exe
        exit 1
    fi
    
    rm /tmp/python-installer.exe
    log_message "INFO" "Python installed in Wine."
else
    log_message "INFO" "Python is already installed in Wine."
fi

log_message "INFO" "Linux Python version: $(python3 --version 2>&1)"
log_message "INFO" "Wine Python version: $($wine_executable python --version 2>&1)"

log_message "INFO" "Checking Wine Python environment..."
$wine_executable python -c "import sys; print(sys.prefix); print(sys.executable); print(sys.path)"

# Output Python and package information for Wine environment
log_message "INFO" "Wine Python installation details:"
$wine_executable python -c "import sys; print(f'Python version: {sys.version}')"
$wine_executable python -c "import sys; print(f'Python executable: {sys.executable}')"
$wine_executable python -c "import sys; print(f'Python path: {sys.path}')"
$wine_executable python -c "import site; print(f'Site packages: {site.getsitepackages()}')"

log_message "INFO" "Installed packages in Wine Python environment:"
$wine_executable python -m pip list
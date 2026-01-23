#!/bin/bash
# Post-removal script for Rediacc Desktop

# Update desktop database
if command -v update-desktop-database &> /dev/null; then
    update-desktop-database -q
fi

exit 0

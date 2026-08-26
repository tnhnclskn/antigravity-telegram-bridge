#!/bin/bash
PLIST_FILE="com.antigravity.telegram.bridge.plist"
TARGET_DIR="$HOME/Library/LaunchAgents"

launchctl unload "$TARGET_DIR/$PLIST_FILE"
rm "$TARGET_DIR/$PLIST_FILE"
echo "macOS LaunchAgent uninstalled successfully."

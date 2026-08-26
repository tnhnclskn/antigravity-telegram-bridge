#!/bin/bash
PLIST_FILE="com.antigravity.telegram.bridge.plist"
TARGET_DIR="$HOME/Library/LaunchAgents"

mkdir -p "$TARGET_DIR"
cp "launchd/$PLIST_FILE" "$TARGET_DIR/"
launchctl load "$TARGET_DIR/$PLIST_FILE"
echo "macOS LaunchAgent installed and loaded successfully."

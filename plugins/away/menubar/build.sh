#!/bin/bash
# Builds Away.app (menu bar moon) and puts it in ~/Applications. Needs Xcode Command Line Tools.
command -v swiftc >/dev/null || { echo "NEEDS_XCODE_TOOLS: run  xcode-select --install  then try again"; exit 2; }
set -euo pipefail
cd "$(dirname "$0")"
APP="$(mktemp -d)/Away.app"   # build outside the plugin folder
mkdir -p "$APP/Contents/MacOS"
swiftc -O Away.swift -o "$APP/Contents/MacOS/Away" -framework AppKit -framework ServiceManagement
cat > "$APP/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>Away</string>
  <key>CFBundleIdentifier</key><string>com.thepurvangmehta.away</string>
  <key>CFBundleExecutable</key><string>Away</string>
  <key>CFBundleVersion</key><string>0.8.0</string>
  <key>CFBundleShortVersionString</key><string>0.8.0</string>
  <key>LSUIElement</key><true/>
  <key>LSMinimumSystemVersion</key><string>13.0</string>
</dict></plist>
EOF
codesign --force --sign - "$APP"   # ad-hoc: fine for your own Mac; public downloads need a Developer ID
mkdir -p ~/Applications
pkill -x Away 2>/dev/null || true
ditto "$APP" ~/Applications/Away.app
open ~/Applications/Away.app
echo "Away is in your menu bar (the moon)."

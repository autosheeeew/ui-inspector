#!/bin/bash
# Build script for android-ui-inspector package
# Run: ./build.sh  or  bash build.sh

set -e
cd "$(dirname "$0")"

echo "=== Building frontend ==="
cd frontend
npm ci 2>/dev/null || npm install
npx vite build
cd ..

echo ""
echo "=== Build complete ==="
echo "Frontend built to: frontend/dist/"
echo ""
echo "Install and run:"
echo "  pip install -e ."
echo "  android-ui-inspector"
echo ""
echo "Or run directly (from project root):"
echo "  python -m android_ui_inspector"

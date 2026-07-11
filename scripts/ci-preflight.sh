#!/usr/bin/env bash
# scripts/ci-preflight.sh
# Asserts required files exist before a workflow runs.

WORKFLOW_NAME=$1
SKIP="false"

case "$WORKFLOW_NAME" in
  rust)
    if [ ! -d "core/rust" ]; then
      echo "=== [PREFLIGHT] Rust core not yet scaffolded. Skipping. ==="
      SKIP="true"
    fi
    ;;
  android)
    if [ ! -d "android" ]; then
      echo "=== [PREFLIGHT] Android directory not found. Skipping. ==="
      SKIP="true"
    fi
    ;;
  ios)
    if [ ! -d "ios" ]; then
      echo "=== [PREFLIGHT] iOS directory not found. Skipping. ==="
      SKIP="true"
    fi
    ;;
  js)
    if [ ! -f "web/package.json" ] && [ ! -f "packages/typescript-sdk/package.json" ]; then
      echo "=== [PREFLIGHT] JS package config not found. Skipping. ==="
      SKIP="true"
    fi
    ;;
  *)
    # Default to no skip
    SKIP="false"
    ;;
esac

if [ -n "$GITHUB_OUTPUT" ]; then
  echo "skip=$SKIP" >> "$GITHUB_OUTPUT"
fi

echo "=== [PREFLIGHT] Preflight check for '$WORKFLOW_NAME': skip=$SKIP ==="
exit 0

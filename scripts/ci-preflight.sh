#!/usr/bin/env bash
# scripts/ci-preflight.sh — Fail-Closed Preflight Component Verification
# Enforces existence of core components before CI jobs execute.

WORKFLOW_NAME=$1
STRICT_MODE=${2:-"--required"}
SKIP="false"

case "$WORKFLOW_NAME" in
  rust)
    if [ ! -d "core/rust" ]; then
      echo "=== [PREFLIGHT ERROR] Required Rust core directory 'core/rust' missing! ==="
      if [ "$STRICT_MODE" = "--required" ]; then exit 1; else SKIP="true"; fi
    fi
    ;;
  android)
    if [ ! -d "android" ]; then
      echo "=== [PREFLIGHT ERROR] Required Android directory 'android' missing! ==="
      if [ "$STRICT_MODE" = "--required" ]; then exit 1; else SKIP="true"; fi
    fi
    ;;
  ios)
    if [ ! -d "ios" ]; then
      echo "=== [PREFLIGHT NOTICE] Optional iOS directory 'ios' not found. Skipping ==="
      SKIP="true"
    fi
    ;;
  js|web)
    if [ ! -f "web/package.json" ]; then
      echo "=== [PREFLIGHT ERROR] Required Web configuration 'web/package.json' missing! ==="
      if [ "$STRICT_MODE" = "--required" ]; then exit 1; else SKIP="true"; fi
    fi
    ;;
  python)
    if [ ! -f "requirements.txt" ]; then
      echo "=== [PREFLIGHT ERROR] Required Python dependencies 'requirements.txt' missing! ==="
      if [ "$STRICT_MODE" = "--required" ]; then exit 1; else SKIP="true"; fi
    fi
    ;;
  *)
    SKIP="false"
    ;;
esac

if [ -n "$GITHUB_OUTPUT" ]; then
  echo "skip=$SKIP" >> "$GITHUB_OUTPUT"
fi

echo "=== [PREFLIGHT PASSED] Component verified for '$WORKFLOW_NAME' (skip=$SKIP) ==="
exit 0

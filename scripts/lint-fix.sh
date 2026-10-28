#!/usr/bin/env bash
# Run all linters and auto-fix what can be fixed. Use before pushing.
cd "$(dirname "$0")/.."
if ! command -v pre-commit &>/dev/null; then
  echo "pre-commit is not installed. Install it first:"
  echo "  pip install pre-commit   # or: uv pip install pre-commit"
  echo "  pre-commit install"
  exit 1
fi
if ! command -v npx &>/dev/null; then
  echo "Warning: npx not found. Install Node.js for JS/Prettier/ESLint hooks; Python hooks will still run."
fi
pre-commit run --all-files
r=$?
if [ $r -ne 0 ]; then
  echo ""
  echo "Some hooks modified files; running again..."
  pre-commit run --all-files
  r=$?
fi
exit $r

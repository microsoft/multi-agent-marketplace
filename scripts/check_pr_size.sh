#!/bin/bash

set -e

BASE_BRANCH=$1
HEAD_COMMIT=$2

if [ -z "$BASE_BRANCH" ] || [ -z "$HEAD_COMMIT" ]; then
  echo "Usage: $0 <base_branch> <head_commit>"
  exit 1
fi

# Get total lines changed
TOTAL_LINES=$(git diff --stat $BASE_BRANCH...$HEAD_COMMIT | tail -n1 | grep -oE '[0-9]+' | head -n1)

echo "PR size: $TOTAL_LINES lines changed"

# Check threshold
MAX_LINES=300

if [ "$TOTAL_LINES" -gt "$MAX_LINES" ]; then
  echo "ERROR: PR too large ($TOTAL_LINES lines, max: $MAX_LINES)"
  echo "Break into smaller PRs for better reviewability"
  exit 1
else
  echo "PASS: PR size acceptable"
fi


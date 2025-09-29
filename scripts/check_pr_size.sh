#!/bin/bash

set -e

BASE_BRANCH=$1
HEAD_COMMIT=$2

if [ -z "$BASE_BRANCH" ] || [ -z "$HEAD_COMMIT" ]; then
  echo "Usage: $0 <base_branch> <head_commit>"
  exit 1
fi

# Get total lines changed (insertions + deletions)
STAT_LINE=$(git diff --stat $BASE_BRANCH...$HEAD_COMMIT | tail -n1)
INSERTIONS=$(echo "$STAT_LINE" | grep -oE '[0-9]+ insertions?' | grep -oE '[0-9]+' || echo "0")
DELETIONS=$(echo "$STAT_LINE" | grep -oE '[0-9]+ deletions?' | grep -oE '[0-9]+' || echo "0")
TOTAL_LINES=$((INSERTIONS + DELETIONS))

echo "PR size: $TOTAL_LINES lines changed ($INSERTIONS insertions, $DELETIONS deletions)"

# Check threshold
MAX_LINES=300

if [ "$TOTAL_LINES" -gt "$MAX_LINES" ]; then
  echo "ERROR: PR too large ($TOTAL_LINES lines, max: $MAX_LINES)"
  echo "Break into smaller PRs for better reviewability"
  exit 1
else
  echo "PASS: PR size acceptable"
fi


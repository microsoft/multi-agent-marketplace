#!/bin/bash

set -e

BASE_BRANCH=$1
HEAD_COMMIT=$2

if [ -z "$BASE_BRANCH" ] || [ -z "$HEAD_COMMIT" ]; then
  echo "Usage: $0 <base_branch> <head_commit>"
  exit 1
fi

echo "Checking for emojis in PR changes..."

# Get the diff of all changed files
DIFF_OUTPUT=$(git diff $BASE_BRANCH...$HEAD_COMMIT)

# Check for emojis using Unicode ranges
# Common emoji ranges:
# - U+1F300-U+1F9FF (Miscellaneous Symbols and Pictographs, Emoticons, Transport and Map Symbols)
# - U+2600-U+26FF (Miscellaneous Symbols)
# - U+2700-U+27BF (Dingbats)
# - U+1F600-U+1F64F (Emoticons)
# - U+1F680-U+1F6FF (Transport and Map)
# - U+1F900-U+1F9FF (Supplemental Symbols)

EMOJI_PATTERN='[\x{1F300}-\x{1F9FF}\x{2600}-\x{26FF}\x{2700}-\x{27BF}]'

if echo "$DIFF_OUTPUT" | grep -P "$EMOJI_PATTERN" > /dev/null; then
  echo "ERROR: Emojis found in PR changes"
  echo ""
  echo "Found emojis in the following locations:"
  echo ""

  # Show files and line numbers with emojis
  git diff $BASE_BRANCH...$HEAD_COMMIT --name-only | while read file; do
    if [ -f "$file" ]; then
      if grep -n -P "$EMOJI_PATTERN" "$file" > /dev/null 2>&1; then
        echo "File: $file"
        grep -n -P "$EMOJI_PATTERN" "$file" | head -5
        echo ""
      fi
    fi
  done

  echo "Please remove all emojis from code, comments, and documentation."
  exit 1
else
  echo "PASS: No emojis found in PR changes"
fi
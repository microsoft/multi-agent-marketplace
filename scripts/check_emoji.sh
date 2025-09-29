#!/bin/bash

set -e

BASE_BRANCH=$1
HEAD_COMMIT=$2

if [ -z "$BASE_BRANCH" ] || [ -z "$HEAD_COMMIT" ]; then
  echo "Usage: $0 <base_branch> <head_commit>"
  exit 1
fi

echo "Checking for emojis in PR changes..."

# Check for emojis using Python for portability across macOS and Linux
# This covers common emoji Unicode ranges

TMPFILE=$(mktemp)
HAS_EMOJIS=0

while read file; do
  if [ -f "$file" ]; then
    EMOJI_CHECK=$(python3 -c "
import re
import sys

emoji_pattern = re.compile(
    '[\U0001F300-\U0001F9FF'  # Miscellaneous Symbols and Pictographs, Emoticons, etc.
    '\U00002600-\U000026FF'   # Miscellaneous Symbols
    '\U00002700-\U000027BF'   # Dingbats
    '\U0001F600-\U0001F64F'   # Emoticons
    '\U0001F680-\U0001F6FF'   # Transport and Map
    '\U0001F900-\U0001F9FF]'  # Supplemental Symbols
)

try:
    with open('$file', 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            if emoji_pattern.search(line):
                print(f'{line_num}:{line.rstrip()}')
except Exception:
    pass
" 2>/dev/null)

    if [ -n "$EMOJI_CHECK" ]; then
      echo "ERROR: Emojis found in: $file"
      echo "$EMOJI_CHECK" | head -5
      echo ""
      echo "1" > "$TMPFILE"
    fi
  fi
done < <(git diff $BASE_BRANCH...$HEAD_COMMIT --name-only)

if [ -f "$TMPFILE" ] && [ "$(cat $TMPFILE 2>/dev/null)" = "1" ]; then
  rm -f "$TMPFILE"
  echo "Please remove all emojis from code, comments, and documentation."
  exit 1
else
  rm -f "$TMPFILE"
  echo "PASS: No emojis found in PR changes"
fi
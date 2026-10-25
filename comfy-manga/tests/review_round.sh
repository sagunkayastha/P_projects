#!/bin/bash
# Review one bench round with Codex (gpt-6.1-sol, image input) and Gemini 3 Flash (archbox, free key; test images only).
#   tests/review_round.sh <round dir with contact.png + prompts.json> <char ref png> [<char ref png> ...]
set -u
R="$1"; shift
HERE="$(cd "$(dirname "$0")" && pwd)"
BRIEF="$HERE/review_brief.md"
# Codex: read-only sandbox, images attached, answer saved
( cd "$R" && { cat "$BRIEF"; printf '\n\nPROMPTS:\n'; cat prompts.json; } | codex exec -m gpt-6.1-sol -s read-only \
    --skip-git-repo-check -i contact.png $(printf -- '-i %s ' "$@") -o codex.json - > codex.out 2> codex.err ) &
# Gemini on archbox
REM=/data/scratch/mangafix/$(basename "$R")
ssh archbox "mkdir -p $REM" && scp -q "$R/contact.png" "$R/prompts.json" "$BRIEF" "$HERE/review_gemini.py" "$@" archbox:$REM/ \
  && ssh archbox "cd $REM && python3 review_gemini.py review_brief.md prompts.json gemini.json contact.png $(for f in "$@"; do printf '%s ' "$(basename "$f")"; done)" > /dev/null 2> "$R/gemini.err" \
  && scp -q archbox:$REM/gemini.json "$R/gemini.json"
wait
echo "codex: $(wc -c < "$R/codex.json") bytes, gemini: $(wc -c < "$R/gemini.json" 2>/dev/null) bytes"

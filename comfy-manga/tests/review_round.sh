#!/bin/bash
# Review one bench round with Codex (gpt-6.1-sol, image input) and Gemini 3 Flash (archbox, free key; test images only).
#   [BRIEF=brief.md CONTACT=contact.png PROMPTS=prompts.json OUT=_suffix] tests/review_round.sh <round dir> <char ref png> [...]
set -u
R="$1"; shift
HERE="$(cd "$(dirname "$0")" && pwd)"
BRIEF="$(readlink -f "${BRIEF:-$HERE/review_brief.md}")"; C="${CONTACT:-contact.png}"; P="${PROMPTS:-prompts.json}"; O="${OUT:-}"
# Codex: read-only sandbox, images attached, answer saved
( cd "$R" && { cat "$BRIEF"; printf '\n\nPROMPTS:\n'; cat "$P"; } | codex exec -m gpt-6.1-sol -s read-only \
    --skip-git-repo-check -i "$C" $(printf -- "-i %s " "$@") -o codex$O.json - > codex$O.out 2> codex$O.err ) &
# Gemini on archbox
REM=/data/scratch/mangafix/$(basename "$R")
ssh archbox "mkdir -p $REM" && scp -q "$R/$C" "$R/$P" "$HERE/review_gemini.py" "$@" archbox:$REM/ \
  && scp -q "$BRIEF" archbox:$REM/brief$O.md \
  && ssh archbox "cd $REM && python3 review_gemini.py brief$O.md $P gemini$O.json $C $(for f in "$@"; do printf '%s ' "$(basename "$f")"; done)" > /dev/null 2> "$R/gemini$O.err" \
  && scp -q archbox:$REM/gemini$O.json "$R/gemini$O.json"
wait
echo "codex: $(wc -c < "$R/codex$O.json") bytes, gemini: $(wc -c < "$R/gemini$O.json" 2>/dev/null) bytes"

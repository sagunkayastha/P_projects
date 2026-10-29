#!/usr/bin/env bash
# Tiny speed check: bin/bench.sh <model id> -> prompt and generation tok/s (2nd of 2 runs; the 1st loads the model).
M=$1; PROMPT=$(python3 -c "print('Summarise the history of the printing press in detail. ' + 'Context: ' + 'lorem ipsum dolor sit amet ' * 300)")
for i in 1 2; do
  R=$(curl -s -m 300 http://127.0.0.1:11434/v1/chat/completions -H 'Content-Type: application/json' \
    -d "$(python3 -c "import json,sys; print(json.dumps({'model':sys.argv[1],'messages':[{'role':'user','content':sys.argv[2]}],'max_tokens':400,'temperature':0,'chat_template_kwargs':{'enable_thinking':False},'cache_prompt':False}))" "$M" "$PROMPT")")
done
echo "$R" | python3 -c "import json,sys; d=json.load(sys.stdin); t=d.get('timings',{}); print(f\"$M: prompt {t.get('prompt_n')} tok @ {t.get('prompt_per_second',0):.0f} tok/s, gen {t.get('predicted_n')} tok @ {t.get('predicted_per_second',0):.1f} tok/s\")" 2>/dev/null || echo "$M: FAILED $(echo "$R" | head -c 200)"

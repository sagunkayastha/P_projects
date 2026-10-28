# Count llama.cpp router events in a log slice (stdin): requests, prompt tokens re-processed, generated tokens,
# full re-process events, checkpoint restores.
import re, sys
req = ptok = gtok = full = restore = 0; pms = 0.0; per = []
for l in sys.stdin:
    m = re.search(r'prompt eval time =\s*([\d.]+) ms /\s*(\d+) tokens', l)
    if m: req += 1; ptok += int(m.group(2)); pms += float(m.group(1)); per.append(int(m.group(2)))
    m = re.search(r'\|\s+eval time =\s*[\d.]+ ms /\s*(\d+) tokens', l)
    if m: gtok += int(m.group(1))
    if 'forcing full prompt re-processing' in l: full += 1
    if 'restored context checkpoint' in l: restore += 1
big = sum(1 for x in per if x > 5000)
print(f"requests={req} prompt_tokens_processed={ptok} prompt_time_s={pms/1000:.1f} gen_tokens={gtok} "
      f"full_reprocess={full} checkpoint_restores={restore} requests_over_5k_prompt={big} max_prompt_chunk={max(per or [0])}")

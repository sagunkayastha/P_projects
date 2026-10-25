You review test panels from a local black-and-white manga pipeline (FLUX.2 klein 9B multi-reference edit model).
Picture 1 is a contact sheet: each ROW is one variant (name + seconds per panel on the left), each COLUMN one fixed
test line (same seed per column). The user's complaint: panels do not follow the line (camera angle, pose, action,
place), angles/poses look the same, backgrounds are random. The test lines and their yes/no checks are in "set"
below; the prompts sent are in "prompts". Variants: base = the app today; order = short prompt with shot/action/place
first; noref = no character reference pictures at all (diagnostic); two_klein / two_anima = composition drawn first
without references (klein / Anima), then klein redraws the people as the reference characters; stick = an extra
stick-figure pose guide picture; cfg3 = distilled klein at CFG 3, 8 steps. The remaining pictures are the two test
characters (Nori: young woman, bob, round glasses, striped scarf, cardigan, pleated skirt; Bram: old man, white beard,
flat cap, dark vest).

For EVERY row and EVERY column answer the 3 checks (angle, pose, place) yes/no, then score.
Answer in JSON only:
{"rows": {"<variant>": {"checks": {"<column name>": {"angle": true, "pose": true, "place": true}},
           "adherence": 0-100, "identity": 1-10, "manga_look": 1-10, "problems": ["short"], "fixes": ["short"]}},
 "best_row": "<variant>", "overall": ["what makes panels follow the line, and what to change in the pipeline"]}
Be strict: an over-the-shoulder shot needs one person's back/shoulder big in the foreground; a hands close-up needs
the hands to fill the frame; top-down needs a camera straight above.

You review test panels from a local black-and-white manga pipeline (FLUX.2 klein 9B multi-reference edit model).
Picture 1 is a contact sheet of the HARD shots that every variant failed in the last round. Row 1 "blockout" is the
grey layout guide drawn for each line (dark = near the camera, light = far, pale = furniture/objects). Each other ROW
is one variant, each COLUMN one fixed test line (same seed per column). Lines and yes/no checks are in "set" below,
the prompts in "prompts". Variants: app = the app's new shipped prompt (line + shot first, short); sil_ref = app +
the blockout as an extra layout reference picture; sil_base = the blockout as image 1 to be turned into the scene;
lllite = Anima (trained on scraped anime art; comparison only) draws the layout under ControlNet-LLLite blockout
control, then klein redraws the people as the reference characters. The remaining pictures are the two test
characters (Nori: young woman, bob, round glasses, striped scarf, cardigan, pleated skirt; Bram: old man, white beard,
flat cap, dark vest).

For EVERY row (not the blockout row) and EVERY column answer the 3 checks (angle, pose, place) yes/no, then score.
Answer in JSON only:
{"rows": {"<variant>": {"checks": {"<column name>": {"angle": true, "pose": true, "place": true}},
           "adherence": 0-100, "identity": 1-10, "manga_look": 1-10, "problems": ["short"], "fixes": ["short"]}},
 "best_row": "<variant>", "overall": ["what gets these shots right, and what to change in the pipeline"]}
Be strict: an over-the-shoulder shot needs the named person's back/shoulder big in the foreground and the other
person facing the camera; a hands close-up needs the hands to fill the frame; top-down needs a camera straight above.

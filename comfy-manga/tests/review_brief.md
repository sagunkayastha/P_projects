You review test panels from a local black-and-white manga pipeline (FLUX.2 klein 9B multi-reference edit model,
4 steps, greyscale conversion; optional Anima img2img pass). Picture 1 is the contact sheet: each ROW is one
variant (settings/model/reference handling, name on the left with seconds per panel), each COLUMN is one of 6
fixed test panels (same seed per column): 1 wide street, 2 close-up face, 3 action pose, 4 two characters,
5 interior, 6 low angle. The remaining pictures are the two test characters' reference pictures (Nori: young
woman, bob, round glasses, striped scarf, cardigan, pleated skirt, ankle boots; Bram: old man, white beard,
flat cap, dark vest). The prompts are below.

Answer in JSON only:
{"rows": {"<variant>": {"score": 1-10, "manga_look": 1-10, "prompt_following": 1-10, "consistency": 1-10,
           "problems": ["short"], "fixes": ["short, concrete: prompt words / sampler / steps / model / refs"]}},
 "best_row": "<variant>", "overall": ["what is wrong with these panels in general and what would improve them most"]}
Score as a manga editor would: real manga ink (line weight, solid blacks, screentone, hatching), anatomy and hands,
composition and camera following the prompt, the same characters as the references, no artifacts or text.

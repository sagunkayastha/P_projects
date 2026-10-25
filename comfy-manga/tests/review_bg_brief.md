You review a background-consistency test from a local black-and-white manga pipeline (FLUX.2 klein 9B). Picture 1
is a contact sheet: column 1 is the place picture (an empty clock shop: counter in the middle, workbench with tools
on the left wall, wall of cuckoo clocks on the right wall, front door with a big window). Columns 2-5 are 4 panels
of one page in that shop (1 enter: wide, both people; 2 bench: Bram at the workbench; 3 clocks: Nori at the clock
wall; 4 door: over-the-shoulder from behind Bram, Nori by the door). Each ROW is a way of giving klein the place:
bg_text = words only; bg_plate = the place picture as a reference "do not copy its composition" (the app today);
bg_turn = place picture + "camera turned toward <part of the room>"; bg_crop = the matching crop of the place picture.
Goal: the same room in all 4 panels AND each panel framed as its line says (not a copy of the place picture's camera).
Answer in JSON only:
{"rows": {"<variant>": {"same_room": 1-10, "camera_follows_line": 1-10, "copies_place_picture": 0-4 (panels that
 reuse the place picture's camera), "problems": ["short"], "fixes": ["short"]}}, "best_row": "<variant>",
 "overall": ["how to keep the room the same while varying the camera"]}

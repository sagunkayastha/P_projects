You review a background test from a local black-and-white manga pipeline (FLUX.2 klein 9B). Picture 1 is a contact
sheet for two 4-panel pages: "shop" (old clock shop: counter in the middle, workbench with tools on the left wall,
wall of cuckoo clocks on the right wall, front door with big window) and "station" (country station: platform with
wooden bench, brick building with ticket window, footbridge over the tracks, fields behind). Column 1 is always the
wide place picture (plate). Rows marked "(given)" show, in columns 2-5, the background view each panel was GIVEN
(not a result). The other rows are the panels; lines and checks per panel are in "places" in the prompts JSON.
Variants: plate = the app today (the one wide plate given to every panel, "do not copy its composition");
views_anima = 3 extra empty views drawn by Anima from words (one per direction, Anima = trained on scraped anime art,
comparison only), each panel gets the view its camera faces; views_klein = 3 extra views made by klein from the plate
("same place, camera turned to face X"), each panel gets its view.
Goal: the same place in all 4 panels AND each panel framed as its line says (not a copy of the plate's camera), and
the part of the place the line names visible.
Answer in JSON only:
{"rows": {"<page>/<variant>": {"same_place": 1-10, "camera_follows_line": 1-10, "named_part_visible": 0-4,
 "copies_plate_camera": 0-4, "problems": ["short"], "fixes": ["short"]}},
 "views_quality": {"views_anima": "short", "views_klein": "short"}, "best_variant": "<variant>",
 "overall": ["how to keep the place the same while varying the camera"]}

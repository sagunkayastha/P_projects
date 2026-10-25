You judge an A/B test of image models for a manga app. The attached contact sheets each show rows; every row has
the input (first column: "source" picture to modify, or a rough "sketch") and one result per model column (letters
A, B, C). The same letter is the same model in every row. Do not guess which model is which.

For every row id (printed at the left of each row; full list in PROMPTS) and every column letter, answer yes/no:
- Modify rows: "change" = the asked change is clearly done (PROMPTS "expected"); "identity" = same character as the
  source (face, age, gender; ignore the asked change); "layout" = ONLY for mode "Small change": framing, camera angle
  and background kept apart from the change (omit for "New picture"); "quality" = clean black-and-white manga,
  correct anatomy, no stray text.
- Sketch rows: "layout" = follows the sketch layout (PROMPTS "layout": same figures/objects in the same places and
  poses); "content" = shows the words; "quality" = as above.
Be strict: a half-done change is false. Then per column letter: one short line on its typical strengths/faults.

Answer ONLY JSON:
{"rows": {"<row id>": {"A": {"change": true, ...}, "B": {...}}, ...},
 "columns": {"A": "strengths / faults", "B": "..."}, "best_column": "A|B|C", "why": "..."}

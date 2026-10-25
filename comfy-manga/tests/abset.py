"""Case sets for the Modify / Sketch A/B rounds (2026-10-26). Source pictures and sketches are test-instance images
(ids in ~/scratch/mangaapp/testdata). Each check is a yes/no question for the judges; {src} = picture 1, {out} = 2."""

# source characters on the test instance
SRC = {"bob": 112, "silver": 108, "fisher": 95, "uniform": 109}
WHO = {"bob": "the young woman with a black bob and a leather jacket",
       "silver": "the girl with a light bob in a sailor school uniform",
       "fisher": "the old man with a long white beard",
       "uniform": "the girl with short light hair in a white shirt"}

MODIFY = [  # name, source, words, what the change looks like (for the "change done" check)
    ("outfit", "uniform", "a hooded sweatshirt and jeans instead of the school uniform", "she wears a hooded sweatshirt and jeans"),
    ("hair", "bob", "long straight hair down to her waist", "her hair is long and straight, reaching about her waist"),
    ("glasses", "fisher", "round sunglasses and a straw hat", "he wears round sunglasses and a straw hat"),
    ("remove", "silver", "remove the book from her hands", "her hands hold no book"),
    ("smile", "bob", "a big happy smile with closed eyes", "she smiles widely with her eyes closed"),
    ("front", "uniform", "front view, facing the viewer", "she faces the viewer, seen from the front"),
    ("side", "bob", "side view, her profile facing left", "she is seen from the side, in profile"),
    ("back", "fisher", "back view, seen from behind", "he is seen from behind (his back faces the viewer)"),
    ("stand", "silver", "standing up, full body", "she stands upright and her full body is visible"),
    ("sit", "fisher", "sitting on a wooden crate", "he sits on a wooden crate"),
    ("scene", "uniform", "in a library, putting a book on a high shelf", "she is in a library putting a book on a high shelf"),
    ("scarf", "silver", "a scarf around her neck and a cat on her lap", "she wears a scarf and a cat sits on her lap"),
]

SKETCH = [  # name, file in ~/scratch/mangafix/sketchtest, words, layout check
    ("stand", "s1_stand.jpg", "a girl in a school uniform standing on a street",
     "one person stands in the middle of the picture, arms slightly out, feet apart, full body"),
    ("bench", "s2_bench.jpg", "a girl sitting on a park bench reading a book under a big tree",
     "a person sits on a bench on the LEFT half and a big tree stands on the RIGHT half"),
    ("cafe", "s3_cafe.jpg", "two friends talking at a cafe table by a big window, cups of coffee",
     "two people sit at the far left and far right facing each other, a table between them, a big window behind"),
    ("room", "s4_room.jpg", "an empty bedroom: a bed on the left, a window on the back wall, a desk with a laptop and a chair on the right, a door at the far right",
     "a bed on the left, a window in the upper middle of the back wall, a desk and chair on the right, a door at the far right edge"),
    ("closeup", "s5_closeup.jpg", "close-up of a girl's face with long hair, calm look",
     "a face fills most of the picture, seen from the front, hair framing both sides"),
    ("hands", "s6_hands.jpg", "close-up of two hands holding a steaming cup of tea",
     "a cup in the center held by two hands coming from the left and right edges, steam above, no face"),
    ("running", "s7_running.jpg", "a boy running fast to the right on a sports track",
     "one person runs toward the right, mid-stride, one leg forward one leg back, full body"),
    ("street", "s8_street.jpg", "two people on a narrow street between tall buildings, one points down the street",
     "a street going into the distance in the center, buildings on both sides, two small people in the middle, the left one points"),
]
SEEDS = (1101, 2202)

"""Round p2 (B) test pages: two places, 4 panels each. Each place has a few named views (the direction the camera
faces, with the words that pick it from a panel line); each panel has yes/no checks for the VLM judge."""
import re

PLACES = {
    "shop": {"bible": "location: small old clock shop, long wooden counter in the middle, a workbench with tools on the "
                      "left wall, a wall of cuckoo clocks on the right wall, a front door with a big shop window; time and "
                      "light: afternoon sun through the shop window",
             "views": [("counter", "the long wooden counter in the middle of the shop", ["counter", "steps into"]),
                       ("workbench", "the workbench with tools on the left wall", ["workbench", "tools", "magnifier"]),
                       ("clocks", "the wall of cuckoo clocks on the right wall", ["clocks", "cuckoo"]),
                       ("door", "the front door and the big shop window", ["door", "window"])],
             "panels": [
                 {"name": "enter", "who": ["nori", "bram"], "shape": "wide",
                  "line": "Wide shot: Nori steps into the clock shop, Bram stands behind the counter",
                  "checks": {"angle": "Is it a wide shot showing most of the shop, with the people small in the frame?",
                             "pose": "Is the old bearded man standing behind a counter?",
                             "place": "Is a long wooden counter visible?"}},
                 {"name": "bench", "who": ["bram"], "shape": "tall",
                  "line": "Medium shot: Bram looks up from his workbench, a magnifier in his hand",
                  "checks": {"angle": "Is it a medium shot (the man framed from about the waist up)?",
                             "pose": "Is the old bearded man holding a magnifying glass?",
                             "place": "Is a workbench with tools visible?"}},
                 {"name": "clocks", "who": ["nori"], "shape": "tall",
                  "line": "Nori stares at the wall of cuckoo clocks, amazed",
                  "checks": {"angle": "Are the young woman and the wall of clocks both in the picture?",
                             "pose": "Is the young woman looking at the clocks with an amazed or surprised face?",
                             "place": "Is a wall full of cuckoo clocks visible?"}},
                 {"name": "door", "who": ["bram", "nori"], "shape": "wide",
                  "line": "Over-the-shoulder shot from behind Bram at the counter, Nori waiting by the door",
                  "checks": {"angle": "Is it an over-the-shoulder shot: the old bearded man's back/shoulder big in the "
                                      "foreground, the young woman further away?",
                             "pose": "Is the young woman standing by a door?",
                             "place": "Is the shop's front door or a big shop window visible?"}}]},
    "station": {"bible": "location: small country train station, a long platform with a wooden bench, a brick station "
                         "building with a ticket window, a footbridge over the tracks, open fields behind the tracks; "
                         "time and light: early morning, light fog",
                "views": [("platform", "along the platform with the wooden bench", ["platform", "bench", "waits"]),
                          ("ticket", "the ticket window in the brick station building", ["ticket", "coins"]),
                          ("footbridge", "the footbridge over the tracks", ["footbridge", "crosses"]),
                          ("fields", "across the tracks to the open fields", ["fields", "tracks"])],
                "panels": [
                    {"name": "wait", "who": ["nori"], "shape": "wide",
                     "line": "Wide shot: Nori waits alone on the platform, a wooden bench beside her",
                     "checks": {"angle": "Is it a wide shot where the young woman is small and the platform is large?",
                                "pose": "Is the young woman standing or waiting on a platform?",
                                "place": "Is a wooden bench on a train platform visible?"}},
                    {"name": "ticket", "who": ["bram"], "shape": "tall",
                     "line": "Medium shot: Bram counts coins at the ticket window",
                     "checks": {"angle": "Is it a medium shot (the man framed from about the waist up)?",
                                "pose": "Is the old bearded man holding or counting coins?",
                                "place": "Is a ticket window (in a brick wall) visible?"}},
                    {"name": "bridge", "who": ["nori"], "shape": "tall",
                     "line": "Low angle: Nori crosses the footbridge above the tracks",
                     "checks": {"angle": "Is the camera low, looking UP at the young woman?",
                                "pose": "Is the young woman walking on a footbridge?",
                                "place": "Is a footbridge over railway tracks visible?"}},
                    {"name": "fields", "who": ["nori", "bram"], "shape": "wide",
                     "line": "Back view of Nori and Bram standing side by side, looking across the tracks at the "
                             "foggy fields",
                     "checks": {"angle": "Do we see the two people from BEHIND (their backs to the camera)?",
                                "pose": "Are the two people standing side by side?",
                                "place": "Are railway tracks and open fields visible beyond them?"}}]}}


def pick_view(line, views):
    """Index of the view whose words the line uses most; a tie goes to the view named last (what the camera looks
    toward: "from behind Bram at the counter, Nori by the door" faces the door); no words: view 0, the wide plate."""
    def score(i):
        pos = [m.end() for w in views[i][2] for m in re.finditer(r"\b" + w + r"\b", line, re.I)]
        return (len({w for w in views[i][2] if re.search(r"\b" + w + r"\b", line, re.I)}), max(pos, default=-1))
    best = max(range(len(views)), key=score)
    return best if score(best)[0] else 0

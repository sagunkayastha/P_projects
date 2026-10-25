"""(Ran against pages._extras of commit 959727b; its signature changed after: check out that commit to rerun.)
Doubled-person test: page-style single-character lines, same seeds, prompt as pages.panel_job builds it, with
or without "appears exactly once" wording, and with or without a previous-panel reference (sequential pages).

  docker cp tests/exp_double.py manga-app-test:/app/ && docker exec manga-app-test python exp_double.py <round>
Output: APP_DIR/../bench/quality/<round>/<variant>_<k>_<name>.png (judge_quality.py style names)
"""
import sys

import db
import graphs
import pages
import writer
from bench_quality import chars_of, once_text, ref_names, run, up
import media

LINES = [("bram", "Bram feeds pigeons in a quiet park"), ("bram", "Bram sits on a bench and reads"),
         ("bram", "Bram walks home at sunset"), ("nori", "Nori waves as the bird flies away"),
         ("nori", "Nori waters plants on a sunny balcony"), ("nori", "Nori waits at a bus stop in the evening")]
SEEDS = [777, 778]


def main():
    rnd = sys.argv[1]
    db.init()
    out = db.APP_DIR.parent / "bench" / "quality" / rnd
    out.mkdir(parents=True, exist_ok=True)
    prev = {"bram": media.read(db.get("pages", 17)["panels"][0]["image_id"]),
            "nori": media.read(db.get("pages", 14)["panels"][1]["image_id"])}
    w, h = graphs.SHAPES["tall"]
    for var in ("plain", "once", "prev", "prev_once"):
        k = 0
        for slug, line in LINES:
            chs = chars_of([slug])
            names, per = ref_names(chs, line, "sheet")
            prev_slot = None
            if var.startswith("prev"):
                names.append(up(prev[slug]))
                prev_slot = len(names)
            p = writer.template(line, [{"name": chs[0]["name"], "n": 1, "sheet": True}], None)
            extra = pages._extras(None, None, prev_slot, True)
            if var.endswith("once"):
                extra = once_text(chs) + extra
            p = p.replace(graphs.STYLE, extra + " " + graphs.STYLE, 1)
            for s in SEEDS:
                k += 1
                name = "lowangle" if slug == "bram" else "action"  # judge_quality WHO key: bram / nori alone
                (out / f"{var}_{k}_{name}.png").write_bytes(run(graphs.klein_refs(p, names, w, h, s)))
                print(var, k, flush=True)


if __name__ == "__main__":
    main()

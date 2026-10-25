"""(Ran against pages._extras of commit 959727b; its signature changed after: check out that commit to rerun.)
Does the character's NAME steer klein away from the reference? Same test character refs + seeds, only the name
in the prompt changes (e.g. a name klein's text encoder knows from anime vs a neutral one).

  docker cp tests/exp_name.py manga-app-test:/app/ && docker exec manga-app-test python exp_name.py nori Nori,Rem
"""
import sys

import db
import graphs
import pages
import writer
from bench_quality import chars_of, ref_names, run

LINES = ["{n} orders a coffee at a cafe counter", "close-up: {n} smiles", "{n} walks home in the rain with an umbrella"]
SEEDS = [11, 12]


def main():
    slug, names = sys.argv[1], sys.argv[2].split(",")
    db.init()
    ch = chars_of([slug])
    out = db.APP_DIR.parent / "bench" / "name"
    out.mkdir(parents=True, exist_ok=True)
    w, h = graphs.SHAPES["tall"]
    for li, line in enumerate(LINES):
        refs_, per = ref_names(ch, line.format(n=ch[0]["name"]), "sheet")
        for nm in names:
            c = [{**ch[0], "name": nm}]
            p = writer.template(line.format(n=nm), [{"name": nm, "n": 1, "sheet": True}], None)
            p = p.replace(graphs.STYLE, pages._extras(None, None, None, True) + " " + graphs.STYLE, 1)
            for s in SEEDS:
                (out / f"{nm}_l{li}_s{s}.png").write_bytes(run(graphs.klein_refs(p, refs_, w, h, s)))
                print(nm, li, s, flush=True)


if __name__ == "__main__":
    main()

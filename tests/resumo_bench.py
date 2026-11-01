"""Resume os JSON do benchmark em tabelas Markdown.

    python tests/resumo_bench.py eval.json [--base legado] [--por categoria|orientacao|type]
"""
import argparse
import json
from collections import defaultdict

import numpy as np

METRICS = ["SAD", "MSE", "Grad", "Conn", "MSE_trans", "Grad_trans"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("arquivo")
    ap.add_argument("--base", default="legado")
    ap.add_argument("--por", default="")
    ap.add_argument("--metrica", default="MSE_trans")
    a = ap.parse_args()
    r = json.load(open(a.arquivo, encoding="utf-8"))
    imgs = r["images"]
    names = list(r["configs"])
    print(f"{len(imgs)} imagens, modelo {r['model']}\n")
    print("| config | " + " | ".join(METRICS) + f" | vence {a.base} (MSE_trans) | t refino |")
    print("|---|" + "---|" * (len(METRICS) + 2))
    for n in names:
        vals = {m: np.mean([i["results"][n][m] for i in imgs]) for m in METRICS}
        wins = sum(i["results"][n]["MSE_trans"] < i["results"][a.base]["MSE_trans"] - 1e-9 for i in imgs)
        t = np.mean([i["results"][n]["t_refino_s"] for i in imgs])
        print(f"| {n} | " + " | ".join(f"{vals[m]:.2f}" for m in METRICS) + f" | {wins}/{len(imgs)} | {t:.2f}s |")
    if a.por:
        groups = defaultdict(list)
        for i in imgs:
            groups[i[a.por]].append(i)
        print(f"\n{a.metrica} por {a.por}:\n")
        print("| config | " + " | ".join(f"{g} ({len(v)})" for g, v in groups.items()) + " |")
        print("|---|" + "---|" * len(groups))
        for n in names:
            print(f"| {n} | " + " | ".join(f"{np.mean([i['results'][n][a.metrica] for i in v]):.2f}" for v in groups.values()) + " |")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Campagne complète : pour chaque ville, lister les restaurants (avec périphérie),
écrire un CSV par ville, puis un fichier de prospection Excel par ville et un
fichier global. Le script reprend où il s'est arrêté : une ville dont le CSV
existe déjà n'est pas réinterrogée.

    python3 campagne.py --toutes                     # 20 grandes villes + périphérie
    python3 campagne.py --touristiques --saison ete  # stations balnéaires + périphérie
    python3 campagne.py --toutes --touristiques      # tout (plusieurs heures)
    python3 campagne.py --villes Toulouse Albi --rayon 3 --sans-peripherie

Fichiers produits dans le dossier campagne/ :
    csv/<ville>.csv                 données brutes par ville
    xlsx/prospection-<ville>.xlsx   fichier de prospection par ville
    toutes-villes.csv               assemblage de tous les CSV
    prospection-toutes-villes.xlsx  fichier de prospection global

Les fichiers Excel nécessitent openpyxl (pip install openpyxl) ; sans lui,
seuls les CSV sont produits.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import time
import unicodedata
from datetime import date
from pathlib import Path

import lister_restaurants as lr

try:
    import prospection_xlsx as px
except ImportError:  # openpyxl absent
    px = None


def slug(nom: str) -> str:
    sans_accents = unicodedata.normalize("NFKD", nom).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", sans_accents.lower()).strip("-")


def ecrire_csv(chemin: Path, lignes: list[dict]) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    tmp = chemin.with_suffix(".tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        lr.ecrire_csv(lignes, f)
    tmp.replace(chemin)  # écriture atomique : pas de CSV à moitié écrit


def lire_csv(chemin: Path) -> list[dict]:
    with open(chemin, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def construire_xlsx(csv_path: Path, xlsx_path: Path, titre: str) -> bool:
    if px is None:
        return False
    if xlsx_path.exists() and xlsx_path.stat().st_mtime >= csv_path.stat().st_mtime:
        return True
    xlsx_path.parent.mkdir(parents=True, exist_ok=True)
    fiches, doublons = px.lire_csv(str(csv_path))
    if not fiches:
        return False
    source = (f"Liste extraite d'OpenStreetMap (API Overpass) le {date.today():%d/%m/%Y} "
              "avec lister_restaurants.py (campagne.py).")
    px.construire(fiches, doublons, str(xlsx_path), titre, source)
    return True


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--villes", nargs="+", metavar="VILLE", help="villes à traiter")
    p.add_argument("--toutes", action="store_true", help=f"les {len(lr.VILLES)} plus grandes villes, Toulouse en premier")
    p.add_argument("--touristiques", action="store_true", help=f"les {len(lr.VILLES_TOURISTIQUES)} villes touristiques")
    p.add_argument("--saison", nargs="+", choices=sorted(lr.SAISONS_LIBELLES), metavar="SAISON",
                   help="avec --touristiques : annee, ete, hiver, evenement")
    p.add_argument("--sans-peripherie", action="store_true", help="ville seule, sans les communes voisines")
    p.add_argument("--rayon", type=float, default=lr.RAYON_PAR_DEFAUT_KM, metavar="KM",
                   help=f"périphérie : distance autour des limites de la ville (défaut : {lr.RAYON_PAR_DEFAUT_KM:g})")
    p.add_argument("--types", nargs="+", default=lr.TYPES_PAR_DEFAUT, choices=lr.TYPES_POSSIBLES)
    p.add_argument("--pause", type=float, default=5.0, help="pause entre deux requêtes, en secondes (défaut : 5)")
    p.add_argument("--dossier", default="campagne", help="dossier de sortie (défaut : campagne)")
    p.add_argument("--refaire", action="store_true", help="réinterroger même les villes déjà exportées")
    p.add_argument("--sans-xlsx", action="store_true", help="ne produire que les CSV")
    args = p.parse_args()

    villes: list[str] = []
    if args.toutes:
        villes += lr.VILLES
    if args.villes:
        villes += args.villes
    if args.touristiques:
        saisons = set(args.saison or lr.SAISONS_LIBELLES)
        villes += [n for n, _, s in lr.VILLES_TOURISTIQUES if s in saisons]
    if not villes:
        p.error("indiquez --villes, --toutes ou --touristiques")
    villes = list(dict.fromkeys(villes))

    dossier = Path(args.dossier)
    faire_xlsx = not args.sans_xlsx and px is not None
    if not args.sans_xlsx and px is None:
        print("openpyxl absent : seuls les CSV seront produits (pip install openpyxl).", file=sys.stderr)

    debut = time.time()
    bilan: list[tuple[str, int, str]] = []
    for i, ville in enumerate(villes):
        csv_path = dossier / "csv" / f"{slug(ville)}.csv"
        xlsx_path = dossier / "xlsx" / f"prospection-{slug(ville)}.xlsx"
        print(f"\n[{i + 1}/{len(villes)}] {ville}", file=sys.stderr)
        if csv_path.exists() and not args.refaire:
            lignes = lire_csv(csv_path)
            print(f"    déjà exporté ({len(lignes)} établissements), on passe", file=sys.stderr)
            etat = "repris"
        else:
            try:
                if args.sans_peripherie:
                    print("    interrogation…", file=sys.stderr, end=" ", flush=True)
                    lignes = lr.lister_ville(ville, args.types)
                    print(f"{len(lignes)} établissements", file=sys.stderr)
                else:
                    print("    ", file=sys.stderr, end="", flush=True)
                    lignes = lr.lister_peripherie(ville, args.rayon, args.types, args.pause)
            except Exception as e:  # la campagne continue avec la ville suivante
                print(f"    échec : {e}", file=sys.stderr)
                bilan.append((ville, 0, "échec"))
                time.sleep(args.pause)
                continue
            ecrire_csv(csv_path, lignes)
            print(f"    {len(lignes)} établissements écrits dans {csv_path}", file=sys.stderr)
            etat = "ok"
            time.sleep(args.pause)
        if faire_xlsx and lignes:
            titre = ville if args.sans_peripherie else f"{ville} et périphérie ({args.rayon:g} km)"
            if construire_xlsx(csv_path, xlsx_path, titre):
                print(f"    fichier de prospection : {xlsx_path}", file=sys.stderr)
        bilan.append((ville, len(lignes), etat))

    # ---- assemblage global
    toutes: list[dict] = []
    for ville, _, etat in bilan:
        chemin = dossier / "csv" / f"{slug(ville)}.csv"
        if chemin.exists():
            toutes.extend(lire_csv(chemin))
    if toutes:
        global_csv = dossier / "toutes-villes.csv"
        ecrire_csv(global_csv, toutes)
        print(f"\n{len(toutes)} établissements assemblés dans {global_csv}", file=sys.stderr)
        if faire_xlsx:
            global_xlsx = dossier / "prospection-toutes-villes.xlsx"
            if construire_xlsx(global_csv, global_xlsx, f"{len(bilan)} villes"):
                print(f"fichier de prospection global : {global_xlsx}", file=sys.stderr)

    duree = int(time.time() - debut)
    print(f"\nBilan ({duree // 60} min {duree % 60} s) :", file=sys.stderr)
    for ville, n, etat in bilan:
        print(f"    {ville:<28} {n:>6}  {etat}", file=sys.stderr)
    echecs = [v for v, _, e in bilan if e == "échec"]
    if echecs:
        print(f"\nÀ relancer (même commande, les villes réussies seront reprises) : {', '.join(echecs)}",
              file=sys.stderr)
    return 1 if echecs else 0


if __name__ == "__main__":
    sys.exit(main())

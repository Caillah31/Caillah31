#!/usr/bin/env python3
"""
Lister les restaurants des grandes villes de France.

Source des données : OpenStreetMap, interrogé via l'API Overpass
(gratuite, sans clé d'API). Les villes sont traitées dans l'ordre
défini par VILLES, Toulouse en tête.

Exemples :
    python3 lister_restaurants.py                       # Toulouse uniquement
    python3 lister_restaurants.py --villes Toulouse Lyon
    python3 lister_restaurants.py --toutes --format csv --sortie restos.csv
    python3 lister_restaurants.py --types restaurant fast_food --limite 50
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# Grandes villes de France métropolitaine, Toulouse en priorité,
# puis par population décroissante (INSEE, communes).
VILLES: list[str] = [
    "Toulouse",
    "Paris",
    "Marseille",
    "Lyon",
    "Nice",
    "Nantes",
    "Montpellier",
    "Strasbourg",
    "Bordeaux",
    "Lille",
    "Rennes",
    "Toulon",
    "Reims",
    "Saint-Étienne",
    "Le Havre",
    "Dijon",
    "Grenoble",
    "Angers",
    "Nîmes",
    "Clermont-Ferrand",
]

TYPES_PAR_DEFAUT = ["restaurant"]
TYPES_POSSIBLES = ["restaurant", "fast_food", "cafe", "bar", "pub", "food_court"]

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.fr/api/interpreter",
]

COLONNES = [
    "ville",
    "nom",
    "type",
    "cuisine",
    "adresse",
    "code_postal",
    "telephone",
    "site_web",
    "horaires",
    "latitude",
    "longitude",
    "osm_id",
]


def construire_requete(ville: str, types: list[str]) -> str:
    """Construit la requête Overpass QL pour une commune française."""
    types_regex = "|".join(types)
    # On part de la France (ISO3166-1=FR) puis on cherche la commune
    # (admin_level=8) à l'intérieur, pour éviter les homonymes à l'étranger.
    return f"""
[out:json][timeout:180];
area["ISO3166-1"="FR"]["admin_level"="2"]->.fr;
rel["name"="{ville}"]["boundary"="administrative"]["admin_level"="8"](area.fr);
map_to_area->.commune;
(
  nwr["amenity"~"^({types_regex})$"](area.commune);
);
out center tags;
"""


def appeler_overpass(requete: str, tentatives: int = 3) -> dict:
    """Envoie la requête à Overpass, avec bascule de serveur et nouvelles tentatives."""
    donnees = urllib.parse.urlencode({"data": requete}).encode("utf-8")
    derniere_erreur: Exception | None = None
    for tentative in range(tentatives):
        url = OVERPASS_URLS[tentative % len(OVERPASS_URLS)]
        req = urllib.request.Request(
            url,
            data=donnees,
            headers={"User-Agent": "lister-restaurants-france/1.0"},
        )
        try:
            with urllib.request.urlopen(req, timeout=200) as rep:
                return json.load(rep)
        except urllib.error.HTTPError as e:
            derniere_erreur = e
            # 429 = trop de requêtes, 504 = serveur saturé : on attend puis on réessaie
            if e.code in (429, 502, 503, 504):
                attente = 10 * (tentative + 1)
                print(f"    serveur occupé ({e.code}), nouvelle tentative dans {attente}s…",
                      file=sys.stderr)
                time.sleep(attente)
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as e:
            derniere_erreur = e
            time.sleep(5 * (tentative + 1))
    raise RuntimeError(f"Overpass injoignable après {tentatives} tentatives : {derniere_erreur}")


def formater_adresse(tags: dict) -> str:
    morceaux = [
        tags.get("addr:housenumber", ""),
        tags.get("addr:street", ""),
    ]
    return " ".join(m for m in morceaux if m).strip()


def normaliser(element: dict, ville: str) -> dict | None:
    """Transforme un élément OSM en ligne plate. Ignore les éléments sans nom."""
    tags = element.get("tags", {})
    nom = tags.get("name")
    if not nom:
        return None
    if element["type"] == "node":
        lat, lon = element.get("lat"), element.get("lon")
    else:
        centre = element.get("center", {})
        lat, lon = centre.get("lat"), centre.get("lon")
    return {
        "ville": ville,
        "nom": nom,
        "type": tags.get("amenity", ""),
        "cuisine": tags.get("cuisine", "").replace(";", ", "),
        "adresse": formater_adresse(tags),
        "code_postal": tags.get("addr:postcode", ""),
        "telephone": tags.get("phone") or tags.get("contact:phone", ""),
        "site_web": tags.get("website") or tags.get("contact:website", ""),
        "horaires": tags.get("opening_hours", ""),
        "latitude": lat,
        "longitude": lon,
        "osm_id": f"{element['type']}/{element['id']}",
    }


def lister_ville(ville: str, types: list[str]) -> list[dict]:
    reponse = appeler_overpass(construire_requete(ville, types))
    lignes = []
    for element in reponse.get("elements", []):
        ligne = normaliser(element, ville)
        if ligne:
            lignes.append(ligne)
    lignes.sort(key=lambda l: l["nom"].lower())
    return lignes


def afficher_table(lignes: list[dict]) -> None:
    ville_courante = None
    for l in lignes:
        if l["ville"] != ville_courante:
            ville_courante = l["ville"]
            print(f"\n=== {ville_courante} ===")
        details = " | ".join(x for x in (l["cuisine"], l["adresse"], l["telephone"]) if x)
        print(f"- {l['nom']}" + (f"  ({details})" if details else ""))


def ecrire_csv(lignes: list[dict], fichier) -> None:
    w = csv.DictWriter(fichier, fieldnames=COLONNES)
    w.writeheader()
    w.writerows(lignes)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--villes", nargs="+", metavar="VILLE",
                   help="villes à traiter (défaut : Toulouse)")
    p.add_argument("--toutes", action="store_true",
                   help=f"traiter les {len(VILLES)} plus grandes villes, Toulouse en premier")
    p.add_argument("--types", nargs="+", default=TYPES_PAR_DEFAUT, choices=TYPES_POSSIBLES,
                   help="types d'établissements OSM (défaut : restaurant)")
    p.add_argument("--limite", type=int, default=0,
                   help="nombre max d'établissements par ville (0 = tous)")
    p.add_argument("--format", choices=["table", "csv", "json"], default="table")
    p.add_argument("--sortie", metavar="FICHIER", help="fichier de sortie (défaut : écran)")
    p.add_argument("--pause", type=float, default=3.0,
                   help="pause en secondes entre deux villes, par respect du serveur (défaut : 3)")
    args = p.parse_args()

    if args.toutes:
        villes = VILLES
    elif args.villes:
        villes = args.villes
    else:
        villes = [VILLES[0]]

    toutes_lignes: list[dict] = []
    for i, ville in enumerate(villes):
        print(f"[{i + 1}/{len(villes)}] {ville}…", file=sys.stderr, end=" ", flush=True)
        try:
            lignes = lister_ville(ville, args.types)
        except Exception as e:  # une ville en échec ne doit pas bloquer les autres
            print(f"échec : {e}", file=sys.stderr)
            continue
        if args.limite:
            lignes = lignes[: args.limite]
        print(f"{len(lignes)} établissements", file=sys.stderr)
        toutes_lignes.extend(lignes)
        if i < len(villes) - 1:
            time.sleep(args.pause)

    sortie = open(args.sortie, "w", newline="", encoding="utf-8") if args.sortie else sys.stdout
    try:
        if args.format == "csv":
            ecrire_csv(toutes_lignes, sortie)
        elif args.format == "json":
            json.dump(toutes_lignes, sortie, ensure_ascii=False, indent=2)
            sortie.write("\n")
        else:
            if args.sortie:
                # une table dans un fichier : on redirige print
                sys.stdout, ancien = sortie, sys.stdout
                afficher_table(toutes_lignes)
                sys.stdout = ancien
            else:
                afficher_table(toutes_lignes)
    finally:
        if args.sortie:
            sortie.close()
            print(f"\n{len(toutes_lignes)} établissements écrits dans {args.sortie}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())

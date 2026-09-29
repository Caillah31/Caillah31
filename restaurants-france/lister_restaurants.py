#!/usr/bin/env python3
"""
Lister les restaurants des grandes villes de France, et de leur périphérie.

Source des données : OpenStreetMap, interrogé via l'API Overpass
(gratuite, sans clé d'API). Les villes sont traitées dans l'ordre
défini par VILLES, Toulouse en tête.

Exemples :
    python3 lister_restaurants.py                       # Toulouse uniquement
    python3 lister_restaurants.py --peripherie          # Toulouse + communes voisines (5 km)
    python3 lister_restaurants.py --peripherie --rayon 10 --format csv --sortie toulouse.csv
    python3 lister_restaurants.py --villes Toulouse Lyon
    python3 lister_restaurants.py --toutes --format csv --sortie restos.csv
    python3 lister_restaurants.py --types restaurant fast_food --limite 50
"""

from __future__ import annotations

import argparse
import csv
import json
import math
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

# Codes INSEE des communes ci-dessus : ils identifient la commune sans
# ambiguïté et rendent la requête Overpass beaucoup plus rapide.
CODES_INSEE: dict[str, str] = {
    "Toulouse": "31555",
    "Paris": "75056",
    "Marseille": "13055",
    "Lyon": "69123",
    "Nice": "06088",
    "Nantes": "44109",
    "Montpellier": "34172",
    "Strasbourg": "67482",
    "Bordeaux": "33063",
    "Lille": "59350",
    "Rennes": "35238",
    "Toulon": "83137",
    "Reims": "51454",
    "Saint-Étienne": "42218",
    "Le Havre": "76351",
    "Dijon": "21231",
    "Grenoble": "38185",
    "Angers": "49007",
    "Nîmes": "30189",
    "Clermont-Ferrand": "63113",
}

TYPES_PAR_DEFAUT = ["restaurant"]
TYPES_POSSIBLES = ["restaurant", "fast_food", "cafe", "bar", "pub", "food_court"]

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.fr/api/interpreter",
]

RAYON_PAR_DEFAUT_KM = 5.0
# Nombre de communes interrogées par requête en mode périphérie.
TAILLE_LOT = 10
# Convention Overpass : l'identifiant de la zone d'une relation = 3 600 000 000 + id.
ID_AREA_RELATION = 3_600_000_000

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


# --------------------------------------------------------------------------
# Requêtes Overpass
# --------------------------------------------------------------------------

def construire_requete(ville: str, types: list[str]) -> str:
    """Construit la requête Overpass QL pour une commune française."""
    types_regex = "|".join(types)
    code = CODES_INSEE.get(ville)
    if code:
        # Code INSEE connu : sélection directe, sans ambiguïté.
        selecteur = f'area["ref:INSEE"="{code}"]["boundary"="administrative"]'
    else:
        # Sinon on cherche par nom ; la présence d'un tag ref:INSEE garantit
        # qu'il s'agit bien d'une commune française (évite Paris au Texas…).
        selecteur = (f'area["name"="{ville}"]["boundary"="administrative"]'
                     f'["admin_level"="8"]["ref:INSEE"]')
    return f"""
[out:json][timeout:120];
{selecteur}->.commune;
(
  nwr["amenity"~"^({types_regex})$"](area.commune);
);
out center tags;
"""


def selecteur_commune(ville: str) -> str:
    """Sélecteur Overpass de la relation « limites administratives » d'une commune."""
    code = CODES_INSEE.get(ville)
    if code:
        return f'rel["ref:INSEE"="{code}"]["boundary"="administrative"]["admin_level"="8"]'
    return (f'rel["name"="{ville}"]["boundary"="administrative"]'
            f'["admin_level"="8"]["ref:INSEE"]')


def construire_requete_lot(communes: list[dict], types: list[str]) -> str:
    """Une seule requête pour plusieurs communes.

    Chaque commune est annoncée par sa relation (« out ids »), puis suivie
    de ses établissements : l'ordre de sortie permet de les rattacher.
    """
    types_regex = "|".join(types)
    blocs = []
    for c in communes:
        blocs.append(
            f'rel({c["id"]}); out ids;\n'
            f'area({ID_AREA_RELATION + c["id"]})->.a;\n'
            f'nwr["amenity"~"^({types_regex})$"](area.a);\n'
            f'out center tags;'
        )
    return "[out:json][timeout:180];\n" + "\n".join(blocs) + "\n"


def appeler_overpass(requete: str, tentatives: int = 4) -> dict:
    """Envoie la requête à Overpass, avec bascule de serveur et nouvelles tentatives."""
    donnees = urllib.parse.urlencode({"data": requete}).encode("utf-8")
    derniere_erreur: Exception | None = None
    for tentative in range(tentatives):
        url = OVERPASS_URLS[tentative % len(OVERPASS_URLS)]
        req = urllib.request.Request(
            url,
            data=donnees,
            headers={"User-Agent": "lister-restaurants-france/1.1"},
        )
        try:
            with urllib.request.urlopen(req, timeout=200) as rep:
                return json.load(rep)
        except urllib.error.HTTPError as e:
            derniere_erreur = e
            # 429 = trop de requêtes, 504 = serveur saturé : on attend puis on réessaie
            if e.code in (429, 502, 503, 504):
                attente = 10 * (tentative + 1)
                suivant = OVERPASS_URLS[(tentative + 1) % len(OVERPASS_URLS)].split("/")[2]
                print(f"\n    serveur occupé ({e.code}), nouvelle tentative sur {suivant} "
                      f"dans {attente}s…", file=sys.stderr)
                time.sleep(attente)
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as e:
            derniere_erreur = e
            time.sleep(5 * (tentative + 1))
    raise RuntimeError(f"Overpass injoignable après {tentatives} tentatives : {derniere_erreur}")


# --------------------------------------------------------------------------
# Mise en forme des résultats
# --------------------------------------------------------------------------

def formater_adresse(tags: dict) -> str:
    morceaux = [
        tags.get("addr:housenumber", ""),
        tags.get("addr:street", ""),
    ]
    return " ".join(m for m in morceaux if m).strip()


def population(tags: dict) -> int:
    """Population OSM d'une commune, 0 si absente ou illisible."""
    try:
        return int(str(tags.get("population", "0")).replace(" ", "").split(".")[0])
    except ValueError:
        return 0


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


# --------------------------------------------------------------------------
# Une ville
# --------------------------------------------------------------------------

def lister_ville(ville: str, types: list[str]) -> list[dict]:
    reponse = appeler_overpass(construire_requete(ville, types))
    lignes = []
    for element in reponse.get("elements", []):
        ligne = normaliser(element, ville)
        if ligne:
            lignes.append(ligne)
    lignes.sort(key=lambda l: l["nom"].lower())
    return lignes


# --------------------------------------------------------------------------
# Une ville et sa périphérie
# --------------------------------------------------------------------------

def trouver_commune(ville: str) -> dict:
    """Retourne la relation OSM de la commune : id, tags et emprise (bounds)."""
    requete = f"[out:json][timeout:60];\n{selecteur_commune(ville)};\nout bb;\n"
    reponse = appeler_overpass(requete)
    candidats = [e for e in reponse.get("elements", [])
                 if e.get("type") == "relation" and "bounds" in e]
    if not candidats:
        raise RuntimeError(f"commune introuvable dans OpenStreetMap : {ville}")
    # En cas d'homonymes, on garde la plus peuplée.
    candidats.sort(key=lambda e: -population(e.get("tags", {})))
    return candidats[0]


def communes_autour(ville: str, rayon_km: float) -> list[dict]:
    """Communes dont le territoire entre dans l'emprise de la ville élargie de rayon_km.

    La ville elle-même est en tête, puis les autres par population décroissante.
    """
    principale = trouver_commune(ville)
    b = principale["bounds"]
    lat_moy = (b["minlat"] + b["maxlat"]) / 2
    dlat = rayon_km / 111.32
    dlon = rayon_km / (111.32 * math.cos(math.radians(lat_moy)))
    sud, ouest = b["minlat"] - dlat, b["minlon"] - dlon
    nord, est = b["maxlat"] + dlat, b["maxlon"] + dlon
    requete = f"""
[out:json][timeout:90];
rel["boundary"="administrative"]["admin_level"="8"]["ref:INSEE"]({sud:.5f},{ouest:.5f},{nord:.5f},{est:.5f});
out tags;
"""
    reponse = appeler_overpass(requete)
    communes: list[dict] = []
    vus: set[int] = set()
    for e in reponse.get("elements", []):
        tags = e.get("tags", {})
        if e.get("type") != "relation" or not tags.get("name") or e["id"] in vus:
            continue
        vus.add(e["id"])
        communes.append({
            "id": e["id"],
            "nom": tags["name"],
            "insee": tags.get("ref:INSEE", ""),
            "population": population(tags),
        })
    if principale["id"] not in vus:
        tags = principale.get("tags", {})
        communes.append({
            "id": principale["id"],
            "nom": tags.get("name", ville),
            "insee": tags.get("ref:INSEE", ""),
            "population": population(tags),
        })
    communes.sort(key=lambda c: (c["id"] != principale["id"], -c["population"], c["nom"]))
    return communes


def lister_lot(communes: list[dict], types: list[str]) -> list[dict]:
    """Liste les établissements d'un lot de communes en une seule requête."""
    reponse = appeler_overpass(construire_requete_lot(communes, types))
    par_id = {c["id"]: c for c in communes}
    groupes: dict[int, list[dict]] = {c["id"]: [] for c in communes}
    courante: int | None = None
    for element in reponse.get("elements", []):
        if element["type"] == "relation" and element["id"] in par_id:
            courante = element["id"]          # en-tête : on change de commune
            continue
        if courante is None:
            continue
        ligne = normaliser(element, par_id[courante]["nom"])
        if ligne:
            groupes[courante].append(ligne)
    lignes: list[dict] = []
    for ident in groupes:                     # ordre des communes conservé
        groupes[ident].sort(key=lambda l: l["nom"].lower())
        lignes.extend(groupes[ident])
    return lignes


def lister_peripherie(ville: str, rayon_km: float, types: list[str], pause: float) -> list[dict]:
    print(f"recherche des communes à moins de {rayon_km:g} km…",
          file=sys.stderr, end=" ", flush=True)
    communes = communes_autour(ville, rayon_km)
    print(f"{len(communes)} communes", file=sys.stderr)
    lots = [communes[i:i + TAILLE_LOT] for i in range(0, len(communes), TAILLE_LOT)]
    lignes: list[dict] = []
    for j, lot in enumerate(lots):
        apercu = ", ".join(c["nom"] for c in lot[:3]) + ("…" if len(lot) > 3 else "")
        print(f"    lot {j + 1}/{len(lots)} ({apercu})…", file=sys.stderr, end=" ", flush=True)
        try:
            resultat = lister_lot(lot, types)
        except Exception as e:  # un lot en échec ne doit pas bloquer les autres
            print(f"échec : {e}", file=sys.stderr)
            continue
        print(f"{len(resultat)} établissements", file=sys.stderr)
        lignes.extend(resultat)
        if j < len(lots) - 1:
            time.sleep(pause)
    return lignes


# --------------------------------------------------------------------------
# Sorties
# --------------------------------------------------------------------------

def limiter_par_ville(lignes: list[dict], maximum: int) -> list[dict]:
    compte: dict[str, int] = {}
    resultat = []
    for l in lignes:
        compte[l["ville"]] = compte.get(l["ville"], 0) + 1
        if compte[l["ville"]] <= maximum:
            resultat.append(l)
    return resultat


def afficher_table(lignes: list[dict], fichier=None) -> None:
    fichier = fichier or sys.stdout
    par_ville: dict[str, list[dict]] = {}
    for l in lignes:
        par_ville.setdefault(l["ville"], []).append(l)
    for ville, etablissements in par_ville.items():
        print(f"\n=== {ville} ({len(etablissements)} établissements) ===", file=fichier)
        for l in etablissements:
            details = " | ".join(x for x in (l["cuisine"], l["adresse"], l["telephone"]) if x)
            print(f"- {l['nom']}" + (f"  ({details})" if details else ""), file=fichier)


def ecrire_csv(lignes: list[dict], fichier) -> None:
    w = csv.DictWriter(fichier, fieldnames=COLONNES)
    w.writeheader()
    w.writerows(lignes)


# --------------------------------------------------------------------------
# Programme principal
# --------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--villes", nargs="+", metavar="VILLE",
                   help="villes à traiter (défaut : Toulouse)")
    p.add_argument("--toutes", action="store_true",
                   help=f"traiter les {len(VILLES)} plus grandes villes, Toulouse en premier")
    p.add_argument("--peripherie", action="store_true",
                   help="inclure les communes de la périphérie de chaque ville "
                        "(voir --rayon), regroupées par commune")
    p.add_argument("--rayon", type=float, default=RAYON_PAR_DEFAUT_KM, metavar="KM",
                   help=f"périphérie : distance autour des limites de la ville, en km "
                        f"(défaut : {RAYON_PAR_DEFAUT_KM:g})")
    p.add_argument("--types", nargs="+", default=TYPES_PAR_DEFAUT, choices=TYPES_POSSIBLES,
                   help="types d'établissements OSM (défaut : restaurant)")
    p.add_argument("--limite", type=int, default=0,
                   help="nombre max d'établissements par commune (0 = tous)")
    p.add_argument("--format", choices=["table", "csv", "json"], default="table")
    p.add_argument("--sortie", metavar="FICHIER", help="fichier de sortie (défaut : écran)")
    p.add_argument("--pause", type=float, default=3.0,
                   help="pause en secondes entre deux requêtes, par respect du serveur (défaut : 3)")
    args = p.parse_args()

    if args.rayon <= 0:
        p.error("--rayon doit être strictement positif")

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
            if args.peripherie:
                lignes = lister_peripherie(ville, args.rayon, args.types, args.pause)
            else:
                lignes = lister_ville(ville, args.types)
        except Exception as e:  # une ville en échec ne doit pas bloquer les autres
            print(f"échec : {e}", file=sys.stderr)
            continue
        if args.limite:
            lignes = limiter_par_ville(lignes, args.limite)
        if args.peripherie:
            print(f"    total {ville} et périphérie : {len(lignes)} établissements",
                  file=sys.stderr)
        else:
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
            afficher_table(toutes_lignes, sortie)
    finally:
        if args.sortie:
            sortie.close()
            print(f"\n{len(toutes_lignes)} établissements écrits dans {args.sortie}",
                  file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())

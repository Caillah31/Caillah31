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
    python3 lister_restaurants.py --touristiques --saison ete   # stations balnéaires…
    python3 lister_restaurants.py --liste-touristiques
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

SAISONS_LIBELLES = {
    "annee": "toute l'année",
    "ete": "été",
    "hiver": "hiver",
    "evenement": "événement / saison particulière",
}

# Villes à forte fréquentation touristique : (commune, département, saison).
# Le département sert à lever les homonymes dans OpenStreetMap.
VILLES_TOURISTIQUES: list[tuple[str, str, str]] = [
    # --- Toute l'année : grandes destinations urbaines et patrimoniales
    ("Paris", "75", "annee"), ("Nice", "06", "annee"), ("Bordeaux", "33", "annee"),
    ("Lyon", "69", "annee"), ("Strasbourg", "67", "annee"), ("Marseille", "13", "annee"),
    ("Montpellier", "34", "annee"), ("Nantes", "44", "annee"), ("Lille", "59", "annee"),
    ("Aix-en-Provence", "13", "annee"), ("Avignon", "84", "annee"), ("Carcassonne", "11", "annee"),
    ("Colmar", "68", "annee"), ("Annecy", "74", "annee"), ("Reims", "51", "annee"),
    ("Tours", "37", "annee"), ("Rouen", "76", "annee"), ("Dijon", "21", "annee"),
    ("Beaune", "21", "annee"), ("Albi", "81", "annee"), ("Cahors", "46", "annee"),
    ("Nîmes", "30", "annee"), ("Arles", "13", "annee"), ("Perpignan", "66", "annee"),
    ("Bayonne", "64", "annee"), ("Pau", "64", "annee"), ("Versailles", "78", "annee"),
    ("Chartres", "28", "annee"), ("Blois", "41", "annee"), ("Amboise", "37", "annee"),
    ("Saint-Émilion", "33", "annee"), ("Bayeux", "14", "annee"), ("Honfleur", "14", "annee"),
    ("Le Mont-Saint-Michel", "50", "annee"), ("Vannes", "56", "annee"), ("Quimper", "29", "annee"),
    ("La Rochelle", "17", "annee"),
    # --- Été : littoral, îles, villages de caractère, stations thermales
    ("Biarritz", "64", "ete"), ("Saint-Jean-de-Luz", "64", "ete"), ("Soorts-Hossegor", "40", "ete"),
    ("Capbreton", "40", "ete"), ("Mimizan", "40", "ete"), ("Lacanau", "33", "ete"),
    ("Arcachon", "33", "ete"), ("La Teste-de-Buch", "33", "ete"), ("Royan", "17", "ete"),
    ("Saint-Martin-de-Ré", "17", "ete"), ("Les Sables-d'Olonne", "85", "ete"),
    ("Noirmoutier-en-l'Île", "85", "ete"), ("La Baule-Escoublac", "44", "ete"),
    ("Saint-Malo", "35", "ete"), ("Dinard", "35", "ete"), ("Quiberon", "56", "ete"),
    ("Carnac", "56", "ete"), ("Concarneau", "29", "ete"), ("Deauville", "14", "ete"),
    ("Trouville-sur-Mer", "14", "ete"), ("Cabourg", "14", "ete"), ("Étretat", "76", "ete"),
    ("Le Touquet-Paris-Plage", "62", "ete"), ("Cannes", "06", "ete"), ("Antibes", "06", "ete"),
    ("Menton", "06", "ete"), ("Saint-Tropez", "83", "ete"), ("Fréjus", "83", "ete"),
    ("Saint-Raphaël", "83", "ete"), ("Hyères", "83", "ete"), ("Bandol", "83", "ete"),
    ("Sanary-sur-Mer", "83", "ete"), ("Cassis", "13", "ete"), ("Saintes-Maries-de-la-Mer", "13", "ete"),
    ("Le Grau-du-Roi", "30", "ete"), ("La Grande-Motte", "34", "ete"), ("Palavas-les-Flots", "34", "ete"),
    ("Sète", "34", "ete"), ("Agde", "34", "ete"), ("Gruissan", "11", "ete"),
    ("Collioure", "66", "ete"), ("Argelès-sur-Mer", "66", "ete"), ("Canet-en-Roussillon", "66", "ete"),
    ("Ajaccio", "2A", "ete"), ("Porto-Vecchio", "2A", "ete"), ("Bonifacio", "2A", "ete"),
    ("Bastia", "2B", "ete"), ("Calvi", "2B", "ete"), ("L'Île-Rousse", "2B", "ete"),
    ("Sarlat-la-Canéda", "24", "ete"), ("Rocamadour", "46", "ete"), ("Cordes-sur-Ciel", "81", "ete"),
    ("Gordes", "84", "ete"), ("L'Isle-sur-la-Sorgue", "84", "ete"), ("Évian-les-Bains", "74", "ete"),
    ("Aix-les-Bains", "73", "ete"), ("Vichy", "03", "ete"),
    # --- Hiver : stations de ski
    ("Chamonix-Mont-Blanc", "74", "hiver"), ("Megève", "74", "hiver"), ("Morzine", "74", "hiver"),
    ("Les Gets", "74", "hiver"), ("Châtel", "74", "hiver"), ("La Clusaz", "74", "hiver"),
    ("Le Grand-Bornand", "74", "hiver"), ("Samoëns", "74", "hiver"), ("Arâches-la-Frasse", "74", "hiver"),
    ("Val-d'Isère", "73", "hiver"), ("Tignes", "73", "hiver"), ("Courchevel", "73", "hiver"),
    ("Les Allues", "73", "hiver"), ("Les Belleville", "73", "hiver"), ("La Plagne Tarentaise", "73", "hiver"),
    ("Bourg-Saint-Maurice", "73", "hiver"), ("Valloire", "73", "hiver"), ("Les Deux Alpes", "38", "hiver"),
    ("Huez", "38", "hiver"), ("Villard-de-Lans", "38", "hiver"), ("Briançon", "05", "hiver"),
    ("Saint-Chaffrey", "05", "hiver"), ("Vars", "05", "hiver"), ("Les Orres", "05", "hiver"),
    ("Font-Romeu-Odeillo-Via", "66", "hiver"), ("Les Angles", "66", "hiver"), ("Cauterets", "65", "hiver"),
    ("Saint-Lary-Soulan", "65", "hiver"), ("Luz-Saint-Sauveur", "65", "hiver"),
    ("Bagnères-de-Luchon", "31", "hiver"), ("Ax-les-Thermes", "09", "hiver"), ("Gérardmer", "88", "hiver"),
    ("La Bresse", "88", "hiver"), ("Métabief", "25", "hiver"), ("Le Mont-Dore", "63", "hiver"),
    ("Besse-et-Saint-Anastaise", "63", "hiver"),
    # --- Événement ou saison particulière
    ("Lourdes", "65", "evenement"),          # pèlerinages, avril à octobre
    ("Le Mans", "72", "evenement"),          # 24 Heures, juin
    ("Angoulême", "16", "evenement"),        # festival de la BD, janvier
    ("Chantilly", "60", "evenement"),        # château, hippodrome
]
DEPARTEMENTS: dict[str, str] = {nom: dep for nom, dep, _ in VILLES_TOURISTIQUES}
SAISONS: dict[str, str] = {nom: SAISONS_LIBELLES[saison] for nom, _, saison in VILLES_TOURISTIQUES}

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
    "saison_touristique",
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
    selecteur = "area" + filtres_commune(ville)
    return f"""
[out:json][timeout:120];
{selecteur}->.commune;
(
  nwr["amenity"~"^({types_regex})$"](area.commune);
);
out center tags;
"""


def filtres_commune(ville: str) -> str:
    """Filtres Overpass identifiant une commune française.

    Code INSEE connu : sélection directe, sans ambiguïté. Sinon par nom,
    restreint au département s'il est connu ; la présence d'un tag ref:INSEE
    garantit qu'il s'agit bien d'une commune française (évite Paris au Texas…).
    """
    code = CODES_INSEE.get(ville)
    if code:
        return f'["ref:INSEE"="{code}"]["boundary"="administrative"]["admin_level"="8"]'
    dep = DEPARTEMENTS.get(ville)
    insee = f'["ref:INSEE"~"^{dep}"]' if dep else '["ref:INSEE"]'
    return f'["name"="{ville}"]["boundary"="administrative"]["admin_level"="8"]{insee}'


def selecteur_commune(ville: str) -> str:
    """Sélecteur Overpass de la relation « limites administratives » d'une commune."""
    return "rel" + filtres_commune(ville)


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
        "saison_touristique": SAISONS.get(ville, ""),
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
    p.add_argument("--touristiques", action="store_true",
                   help=f"ajouter les {len(VILLES_TOURISTIQUES)} villes à forte fréquentation "
                        "touristique (seules, si --villes/--toutes sont absents)")
    p.add_argument("--saison", nargs="+", choices=sorted(SAISONS_LIBELLES), metavar="SAISON",
                   help="avec --touristiques : ne garder que ces saisons "
                        "(annee, ete, hiver, evenement)")
    p.add_argument("--liste-touristiques", action="store_true",
                   help="afficher les villes touristiques par saison et quitter")
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

    if args.liste_touristiques:
        for cle, libelle in SAISONS_LIBELLES.items():
            noms = [n for n, _, sais in VILLES_TOURISTIQUES if sais == cle]
            print(f"{libelle} ({len(noms)}) : {', '.join(noms)}")
        return 0

    villes: list[str] = []
    if args.toutes:
        villes += VILLES
    elif args.villes:
        villes += args.villes
    if args.touristiques:
        saisons = set(args.saison or SAISONS_LIBELLES)
        villes += [n for n, _, sais in VILLES_TOURISTIQUES if sais in saisons]
    if not villes:
        villes = [VILLES[0]]
    villes = list(dict.fromkeys(villes))  # doublons retirés, ordre conservé

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

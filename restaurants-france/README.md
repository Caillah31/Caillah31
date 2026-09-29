# Restaurants de France

Script Python (sans dépendance externe, bibliothèque standard uniquement)
qui liste les restaurants des grandes villes françaises à partir des
données **OpenStreetMap**, via l'API **Overpass** (gratuite, sans clé).

Les villes sont traitées dans cet ordre, **Toulouse en priorité**, puis
par population décroissante : Toulouse, Paris, Marseille, Lyon, Nice,
Nantes, Montpellier, Strasbourg, Bordeaux, Lille, Rennes, Toulon, Reims,
Saint-Étienne, Le Havre, Dijon, Grenoble, Angers, Nîmes, Clermont-Ferrand.

## Utilisation

```bash
# Toulouse uniquement, affichage à l'écran
python3 lister_restaurants.py

# Plusieurs villes
python3 lister_restaurants.py --villes Toulouse Bordeaux Montpellier

# Les 20 plus grandes villes, export CSV
python3 lister_restaurants.py --toutes --format csv --sortie restaurants.csv

# Restaurants + fast-foods, 100 max par ville, export JSON
python3 lister_restaurants.py --types restaurant fast_food --limite 100 --format json --sortie toulouse.json
```

## Options

| Option      | Description                                                        |
|-------------|--------------------------------------------------------------------|
| `--villes`  | Villes à traiter (défaut : Toulouse)                               |
| `--toutes`  | Traite les 20 plus grandes villes, Toulouse en premier             |
| `--types`   | `restaurant` (défaut), `fast_food`, `cafe`, `bar`, `pub`, `food_court` |
| `--limite`  | Nombre max d'établissements par ville (0 = tous)                   |
| `--format`  | `table` (défaut), `csv`, `json`                                    |
| `--sortie`  | Fichier de sortie (sinon écran)                                    |
| `--pause`   | Pause entre deux villes, en secondes (défaut : 3)                  |

## Colonnes exportées

`ville, nom, type, cuisine, adresse, code_postal, telephone, site_web,
horaires, latitude, longitude, osm_id`

## Remarques

- Overpass limite le débit : le script attend et réessaie automatiquement
  en cas de saturation (codes 429 / 504) et bascule sur un serveur miroir.
- Paris compte plus de 15 000 restaurants dans OSM : la requête peut
  prendre une minute. Utilisez `--limite` pour un aperçu rapide.
- Les données OSM sont contributives : certains établissements n'ont pas
  d'adresse, de téléphone ou d'horaires renseignés.

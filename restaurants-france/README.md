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

# Toulouse et toute sa périphérie (communes à moins de 5 km des limites de la ville)
python3 lister_restaurants.py --peripherie

# Périphérie élargie à 10 km, export CSV pour un tableur
python3 lister_restaurants.py --peripherie --rayon 10 --format csv --sortie toulouse-peripherie.csv

# Plusieurs villes
python3 lister_restaurants.py --villes Toulouse Bordeaux Montpellier

# Villes touristiques : toutes, ou seulement l'été / l'hiver
python3 lister_restaurants.py --touristiques --format csv --sortie touristiques.csv
python3 lister_restaurants.py --touristiques --saison ete hiver
python3 lister_restaurants.py --liste-touristiques      # affiche la liste sans interroger

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
| `--touristiques` | Ajoute les 134 villes à forte fréquentation touristique (seules si `--villes`/`--toutes` absents) |
| `--saison`  | Avec `--touristiques` : `annee`, `ete`, `hiver`, `evenement` (plusieurs possibles) |
| `--liste-touristiques` | Affiche les villes touristiques par saison et quitte |
| `--peripherie` | Ajoute les communes de la périphérie de chaque ville, regroupées par commune |
| `--rayon`   | Périphérie : distance autour des limites de la ville, en km (défaut : 5) |
| `--types`   | `restaurant` (défaut), `fast_food`, `cafe`, `bar`, `pub`, `food_court` |
| `--limite`  | Nombre max d'établissements par commune (0 = tous)                 |
| `--format`  | `table` (défaut), `csv`, `json`                                    |
| `--sortie`  | Fichier de sortie (sinon écran)                                    |
| `--pause`   | Pause entre deux requêtes, en secondes (défaut : 3)                |

## Colonnes exportées

`ville, saison_touristique, nom, type, cuisine, adresse, code_postal, telephone, site_web,
horaires, latitude, longitude, osm_id`

## Villes touristiques

La liste `VILLES_TOURISTIQUES` du script regroupe 134 communes classées en
quatre saisons : **toute l'année** (grandes villes et sites patrimoniaux :
Paris, Nice, Carcassonne, Albi, Le Mont-Saint-Michel…), **été** (littoral,
Corse, villages de caractère, stations thermales : Biarritz, Arcachon,
Saint-Malo, Saint-Tropez, Collioure, Ajaccio, Sarlat…), **hiver** (stations
de ski : Chamonix, Val-d'Isère, Courchevel, Saint-Lary, Luchon, Font-Romeu…)
et **événement** (Lourdes, Le Mans, Angoulême, Chantilly). La colonne
`saison_touristique` des exports reprend cette classification. Chaque
commune est identifiée par son nom et son département pour éviter les
homonymes. La liste se complète librement dans le script.

## Périphérie

Avec `--peripherie`, le script découvre lui-même les communes voisines dans
OpenStreetMap : il prend l'emprise géographique de la ville, l'élargit de
`--rayon` km (5 km par défaut) et retient toutes les communes qui entrent
dans cette zone. Pour Toulouse, cela couvre notamment Blagnac, Colomiers,
Tournefeuille, Cugnaux, Portet-sur-Garonne, Ramonville, Labège,
Castanet-Tolosan, Saint-Orens, Balma, L'Union, Launaguet, Aucamville,
Fenouillet, Beauzelle, Muret… La liste est ensuite produite commune par
commune, la ville principale en premier puis par population décroissante.
Les communes sont interrogées par lots de 10 pour ménager le serveur.

## Remarques

- Overpass limite le débit : le script attend et réessaie automatiquement
  en cas de saturation (codes 429 / 504) et bascule sur un serveur miroir.
- Paris compte plus de 15 000 restaurants dans OSM : la requête peut
  prendre une minute. Utilisez `--limite` pour un aperçu rapide.
- Les données OSM sont contributives : certains établissements n'ont pas
  d'adresse, de téléphone ou d'horaires renseignés.

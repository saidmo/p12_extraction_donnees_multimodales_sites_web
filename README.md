# CheckIt.AI — Pipeline d'acquisition de données multimodales

Pipeline **ETL** d'extraction, transformation et chargement de publications
**multimodales (texte + image)** destinées à l'entraînement d'un détecteur de
fake news. Projet P12 — parcours AI Engineer (OpenClassrooms).

## Objectif

Industrialiser l'acquisition de données : récupérer des publications texte + image
depuis plusieurs sources, les nettoyer et les normaliser, les stocker dans
PostgreSQL, et orchestrer le tout avec Apache Airflow — de façon automatisée,
reproductible et supervisée.

## Architecture hybride

Deux types de sources complémentaires alimentent une même table `publications` :

- **Sources live** (fraîches, non labellisées) : NewsAPI + flux RSS de fact-checkers.
- **Source dataset** (statique, labellisée) : Fakeddit — le socle de vérité terrain.

> Flux frais pour la production, dataset annoté pour l'entraînement : c'est
> l'architecture attendue en amont d'un détecteur multimodal.

## Chaîne de traitement

```
extract  ->  transform  ->  load
(sources)   (nettoyage,      (PostgreSQL)
             normalisation,
             image, colonnes)
```

## Arborescence

```
.
├── docker-compose.yml        # PostgreSQL (données + métadonnées Airflow) + Airflow
├── .env                      # secrets et config (NON versionné)
├── requirements.txt
├── database.py               # connexion, création de table, insertion (ON CONFLICT)
├── extract.py                # sources live : fetch_newsapi(), fetch_rss()
├── extract_dataset.py        # source labellisée : fetch_dataset() (Fakeddit)
├── transform.py              # nettoie_texte(), normalise(), valide_image(), genere_colonnes()
├── main.py                   # pipeline complet en local (live)
├── seed_dataset.py           # chargement one-shot du socle Fakeddit (en local)
├── dashboard.py              # tableau de bord KPI (Streamlit)
├── dags/
│   ├── etl_fakenews_xcom.py     # DAG live — données via XCom (simple)
│   ├── etl_fakenews_staging.py  # DAG live — données via staging PostgreSQL (scalable)
│   ├── staging_db.py            # helpers SQL de la version staging
│   └── seed_fakeddit.py         # DAG one-shot — chargement du socle Fakeddit
├── docs/
│   ├── schema_conceptuel.md / .mermaid   # modèle conceptuel des données
│   ├── flux_pipeline.mermaid             # schéma de flux du pipeline
│   ├── plan_monitoring.md                # plan de surveillance
│   └── demonstration_soutenance.md       # guide de démonstration
├── fakeddit/                 # dataset (multimodal_validate.tsv) — NON versionné
├── images/                   # images téléchargées — NON versionné
└── data/                     # sorties éventuelles — NON versionné
```

## Prérequis

- Docker + Docker Compose
- Python 3.11+ (environnement virtuel recommandé)

## Installation

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows  (source .venv/bin/activate sous Linux/Mac)
pip install -r requirements.txt
```

Créer un fichier `.env` à la racine :

```
# PostgreSQL
DB_HOST=127.0.0.1
DB_PORT=5432
DB_NAME=fakenews
DB_USER=postgres
DB_PASSWORD=************
# NewsAPI
CHECKIT_NEWSAPI_KEY=************
# Airflow
AIRFLOW_FERNET_KEY=************
AIRFLOW_SECRET_KEY=************
AIRFLOW_ADMIN_USER=admin
AIRFLOW_ADMIN_PASSWORD=************
```

## Démarrage

```bash
# 1. Base + Airflow
docker compose up -d
docker exec -it postgres-fakenews psql -U postgres -c "CREATE DATABASE airflow_db;"   # une seule fois

# 2. Pipeline live en local
python main.py

# 3. Socle labellisé (one-shot)
python seed_dataset.py

# 4. Tableau de bord
streamlit run dashboard.py            # http://localhost:8501

# Airflow UI : http://localhost:8080
```

## Orchestration (Airflow)

Trois DAGs, déclenchement manuel :

| DAG | Rôle |
|---|---|
| `etl_fakenews_xcom` | flux live, données échangées via XCom (simple) |
| `etl_fakenews_staging` | flux live, données via staging PostgreSQL (scalable) |
| `seed_fakeddit` | chargement one-shot du socle labellisé Fakeddit |

## Livrables du projet

Rapport d'exploration de sources · scripts d'extraction · pipeline de
transformation · schéma conceptuel · DAG Airflow · tableau de bord KPI ·
plan de monitoring.

## Notes

- Les images ne sont pas stockées en base : seul leur **chemin** + métadonnées le sont.
- L'appariement **texte + image** est garanti (une publication sans image est écartée).
- Le `label` provient d'un verdict explicite (fact-checker) ou du dataset annoté ;
  `unknown` par défaut. La réputation d'une source n'est **pas** un label.
- En environnement avec inspection SSL (antivirus), suspendre l'antivirus avant les
  appels réseau (extraction, téléchargement d'images).

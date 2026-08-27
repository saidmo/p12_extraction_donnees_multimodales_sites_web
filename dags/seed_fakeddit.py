"""DAG d'INITIALISATION (one-shot) — charge le socle labellisé Fakeddit.

Contrairement aux DAGs live (etl_fakenews_*), celui-ci ingère un dataset STATIQUE
et n'a pas vocation à tourner régulièrement : on le déclenche manuellement, une fois.

Garde-fous :
  - schedule=None        -> aucune planification (déclenchement manuel uniquement)
  - catchup=False        -> pas de rattrapage de runs passés
  - max_active_runs=1    -> pas d'exécutions simultanées
  - ON CONFLICT DO NOTHING (dans insert_publications) -> relance sans danger : les
    lignes déjà présentes sont ignorées.

Prérequis : le fichier fakeddit/multimodal_validate.tsv accessible depuis le conteneur.
"""
from datetime import datetime

from airflow import DAG
from airflow.operators.python import PythonOperator

from extract_dataset import fetch_dataset
from transform import transforme
from database import create_table, insert_publications


def _json_safe(publications):
    """XCom sérialise en JSON : on convertit les dates (datetime) en chaînes ISO."""
    for pub in publications:
        for champ in ("published_at", "fetched_at"):
            valeur = pub.get(champ)
            if hasattr(valeur, "isoformat"):
                pub[champ] = valeur.isoformat()
    return publications


def _extract(**context):
    return _json_safe(fetch_dataset(echantillon=200))     # -> XCom


def _transform(**context):
    articles = context["ti"].xcom_pull(task_ids="extract")
    return transforme(articles)                            # -> XCom


def _load(**context):
    propres = context["ti"].xcom_pull(task_ids="transform")
    create_table()
    n = insert_publications(propres)
    print(f"{n} échantillons labellisés insérés")


default_args = {"owner": "checkit", "retries": 1}

with DAG(
    dag_id="seed_fakeddit",
    description="Chargement one-shot du socle labellisé Fakeddit (brique hybride)",
    start_date=datetime(2026, 1, 1),
    schedule=None,            # manuel uniquement
    catchup=False,            # pas de rattrapage
    max_active_runs=1,        # pas d'exécutions simultanées
    default_args=default_args,
    tags=["checkit", "dataset", "one-shot"],
) as dag:

    extract = PythonOperator(task_id="extract", python_callable=_extract)
    transform = PythonOperator(task_id="transform", python_callable=_transform)
    load = PythonOperator(task_id="load", python_callable=_load)

    extract >> transform >> load

"""DAG ETL — version simple : les données transitent entre tâches via XCom.

extract -> transform -> load, chacune un PythonOperator qui réutilise TES fonctions.
Adapté aux petits volumes (XCom stocke dans la base de métadonnées d'Airflow).
"""
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

from extract import fetch_newsapi, fetch_rss
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
    articles = fetch_newsapi(query="actualité", language="fr", page_size=20)
    articles += fetch_rss()
    return _json_safe(articles)                      # -> stocké dans XCom


def _transform(**context):
    ti = context["ti"]
    articles = ti.xcom_pull(task_ids="extract")      # <- récupère le résultat d'extract
    return transforme(articles)                      # -> stocké dans XCom


def _load(**context):
    ti = context["ti"]
    propres = ti.xcom_pull(task_ids="transform")     # <- récupère le résultat de transform
    create_table()
    n = insert_publications(propres)
    print(f"{n} publications insérées en base")


default_args = {"owner": "checkit", "retries": 1, "retry_delay": timedelta(minutes=1)}

with DAG(
    dag_id="etl_fakenews_xcom",
    description="ETL multimodal (NewsAPI + RSS) -> PostgreSQL, échange via XCom",
    start_date=datetime(2026, 1, 1),
    schedule=None,            # déclenchement manuel
    catchup=False,
    default_args=default_args,
    tags=["checkit", "etl"],
) as dag:

    extract = PythonOperator(task_id="extract", python_callable=_extract)
    transform = PythonOperator(task_id="transform", python_callable=_transform)
    load = PythonOperator(task_id="load", python_callable=_load)

    extract >> transform >> load

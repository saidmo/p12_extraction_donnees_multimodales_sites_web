"""DAG ETL — version scalable : les tâches communiquent via une table de staging.

XCom ne transporte que des compteurs ; les données transitent par PostgreSQL.
  extract_to_staging : insère le BRUT en staging
  transform_in_db    : nettoie + colonnes EN SQL, puis télécharge les images
  load_to_final      : INSERT ... SELECT du staging vers la table finale
"""
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

from extract import fetch_newsapi, fetch_rss
from transform import valide_et_telecharge_image
from database import create_table
import staging_db as sdb


def _extract(**context):
    sdb.create_staging_table()
    articles = fetch_newsapi(query="actualité", language="fr", page_size=20)
    articles += fetch_rss()
    n = sdb.insert_raw(articles)
    print(f"{n} lignes brutes insérées en staging")
    return n                                   # XCom = simple compteur


def _transform(**context):
    # 1) nettoyage + colonnes dérivées : DANS la base (set-based -> scalable)
    sdb.clean_and_features_in_db()
    # 2) images : le téléchargement reste en Python (binaire), mais par petits lots
    pairs = []
    for pub_id, image_url in sdb.rows_without_image():
        chemin = valide_et_telecharge_image(image_url, pub_id) if image_url else None
        if chemin:
            pairs.append((chemin, pub_id))
    sdb.set_image_paths(pairs)
    supprimees = sdb.delete_without_image()    # sans image -> écartées (multimodal)
    print(f"{len(pairs)} images téléchargées, {supprimees} lignes sans image supprimées")
    return len(pairs)


def _load(**context):
    create_table()                             # table finale
    n = sdb.promote_to_final()                 # INSERT ... SELECT (set-based)
    sdb.truncate_staging()
    print(f"{n} publications promues en table finale")
    return n


default_args = {"owner": "checkit", "retries": 1, "retry_delay": timedelta(minutes=1)}

with DAG(
    dag_id="etl_fakenews_staging",
    description="ETL multimodal via staging PostgreSQL (scalable ; XCom = métadonnées)",
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    default_args=default_args,
    tags=["checkit", "etl", "staging"],
) as dag:

    extract = PythonOperator(task_id="extract_to_staging", python_callable=_extract)
    transform = PythonOperator(task_id="transform_in_db", python_callable=_transform)
    load = PythonOperator(task_id="load_to_final", python_callable=_load)

    extract >> transform >> load

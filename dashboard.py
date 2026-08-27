"""Tableau de bord KPI de l'ETL (Étape 5).

Deux familles d'indicateurs :
  1. Données  : qualité et composition du dataset (base 'fakenews', table publications).
  2. Pipeline : exécution de l'ETL (métadonnées Airflow : dag_run, task_instance).

Lancement :  streamlit run dashboard.py
"""
import os

import pandas as pd
import psycopg2
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# Paramètres de connexion communs (l'hôte est 127.0.0.1 en local)
DB = dict(
    host=os.getenv("DB_HOST", "127.0.0.1"),
    port=os.getenv("DB_PORT", "5432"),
    user=os.getenv("DB_USER", "postgres"),
    password=os.getenv("DB_PASSWORD"),
)


def run_query(dbname, sql):
    """Exécute une requête sur la base indiquée et renvoie un DataFrame pandas."""
    conn = psycopg2.connect(dbname=dbname, **DB)
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            colonnes = [d[0] for d in cur.description]
            lignes = cur.fetchall()
        return pd.DataFrame(lignes, columns=colonnes)
    finally:
        conn.close()


st.set_page_config(page_title="KPI ETL — CheckIt.AI", layout="wide")
st.title("Tableau de bord — Pipeline de détection de fake news")
st.caption("Indicateurs de qualité des données et de performance du pipeline ETL.")

# ===========================================================================
# 1. KPI DONNÉES (base fakenews)
# ===========================================================================
st.header("1. Qualité des données")

try:
    df = run_query(os.getenv("DB_NAME", "fakenews"), "SELECT * FROM publications;")
except Exception as exc:
    st.error(f"Impossible de lire la base de données : {exc}")
    st.stop()

total = len(df)
if total == 0:
    st.warning("Aucune publication en base. Lance d'abord le DAG d'extraction.")
    st.stop()

# % de données valides = texte non vide + image présente
valides = df[(df["content"].notna()) & (df["image_path"].notna()) & (df["content_length"] > 0)]
pct_valide = 100 * len(valides) / total
pct_image = 100 * df["image_path"].notna().mean()
pct_label = 100 * (df["label"] != "unknown").mean()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Publications", total)
c2.metric("Données valides", f"{pct_valide:.0f} %")
c3.metric("Avec image", f"{pct_image:.0f} %")
c4.metric("Avec label", f"{pct_label:.0f} %")

col1, col2 = st.columns(2)
with col1:
    st.subheader("Publications par source")
    st.bar_chart(df["source"].value_counts())
with col2:
    st.subheader("Répartition des labels")
    st.bar_chart(df["label"].value_counts())

st.subheader("Nombre moyen de mots par source")
st.bar_chart(df.groupby("source")["word_count"].mean())

if df["published_at"].notna().any():
    st.subheader("Publications par jour")
    ts = df.dropna(subset=["published_at"]).copy()
    ts["jour"] = pd.to_datetime(ts["published_at"]).dt.date
    st.line_chart(ts.groupby("jour").size())

# ===========================================================================
# 2. KPI PIPELINE (métadonnées Airflow)
# ===========================================================================
st.header("2. Performance du pipeline (Airflow)")

try:
    runs = run_query("airflow_db", """
        SELECT dag_id, state, start_date, end_date,
               EXTRACT(EPOCH FROM (end_date - start_date)) AS duree_s
        FROM dag_run
        WHERE dag_id LIKE 'etl_fakenews%'
        ORDER BY start_date DESC;
    """)
    tasks = run_query("airflow_db", """
        SELECT task_id,
               AVG(duration) AS duree_moyenne_s,
               COUNT(*)      AS executions
        FROM task_instance
        WHERE dag_id LIKE 'etl_fakenews%' AND duration IS NOT NULL
        GROUP BY task_id
        ORDER BY duree_moyenne_s DESC;
    """)
except Exception as exc:
    st.info(f"Métadonnées Airflow indisponibles : {exc}")
    runs = tasks = pd.DataFrame()

if not runs.empty:
    total_runs = len(runs)
    succes = int((runs["state"] == "success").sum())
    duree_moy = runs["duree_s"].dropna().mean()

    d1, d2, d3 = st.columns(3)
    d1.metric("Exécutions du DAG", total_runs)
    d2.metric("Taux de succès", f"{100 * succes / total_runs:.0f} %")
    d3.metric("Durée moyenne", f"{duree_moy:.1f} s" if pd.notna(duree_moy) else "—")

    if not tasks.empty:
        st.subheader("Durée moyenne par tâche (secondes)")
        st.bar_chart(tasks.set_index("task_id")["duree_moyenne_s"])

    st.subheader("Dernières exécutions")
    st.dataframe(runs.head(10), use_container_width=True)
else:
    st.info("Aucune exécution de DAG enregistrée pour le moment.")

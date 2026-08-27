"""Gestion de la base PostgreSQL : connexion, création de la table, insertion.

Volontairement simple : SQL écrit à la main, pas d'ORM.
Les paramètres de connexion sont lus depuis le fichier .env.
"""
import logging
import os

import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. Connexion
# ---------------------------------------------------------------------------
def get_connection():
    """Ouvre et renvoie une connexion à PostgreSQL, avec les paramètres du .env."""
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "fakenews"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD"),
    )


# ---------------------------------------------------------------------------
# 2. Création de la table
# ---------------------------------------------------------------------------
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS publications (
    id             TEXT PRIMARY KEY,
    source         TEXT,
    url            TEXT,
    title          TEXT,
    content        TEXT,
    image_path     TEXT,
    image_url      TEXT,
    language       TEXT,
    label          TEXT DEFAULT 'unknown',
    content_length INTEGER,
    word_count     INTEGER,
    published_at   TIMESTAMP,
    fetched_at     TIMESTAMP
);
"""


def create_table():
    """Crée la table 'publications' si elle n'existe pas déjà."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(CREATE_TABLE_SQL)
        conn.commit()
        log.info("table 'publications' prête")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 3. Insertion
# ---------------------------------------------------------------------------
COLUMNS = [
    "id", "source", "url", "title", "content", "image_path", "image_url",
    "language", "label", "content_length", "word_count",
    "published_at", "fetched_at",
]

INSERT_SQL = """
INSERT INTO publications
    (id, source, url, title, content, image_path, image_url,
     language, label, content_length, word_count, published_at, fetched_at)
VALUES %s
ON CONFLICT (id) DO NOTHING;
"""


def insert_publications(publications):
    """Insère une liste de publications (dicts). Doublons (même id) ignorés.
    Renvoie le nombre de lignes réellement insérées."""
    if not publications:
        log.info("aucune publication à insérer")
        return 0

    valeurs = [tuple(pub.get(col) for col in COLUMNS) for pub in publications]

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            execute_values(cur, INSERT_SQL, valeurs)
            inserees = cur.rowcount
        conn.commit()
        log.info("%d publications insérées (doublons ignorés)", inserees)
        return inserees
    finally:
        conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    create_table()

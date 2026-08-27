"""Helpers de la variante ELT : les tâches communiquent via des tables PostgreSQL.

Principe : les données vivent dans une table de staging ; XCom ne transporte que
de petits compteurs. Ça évite de gonfler la base de métadonnées d'Airflow et ça
passe à l'échelle (les gros volumes ne remontent jamais en masse dans Python).
"""
import logging

from psycopg2.extras import execute_batch, execute_values

from database import get_connection   # on réutilise la connexion déjà écrite

log = logging.getLogger(__name__)

STAGING = "publications_staging"

COLUMNS = ["id", "source", "url", "title", "content", "image_path", "image_url",
           "language", "label", "content_length", "word_count",
           "published_at", "fetched_at"]

CREATE_STAGING_SQL = f"""
CREATE TABLE IF NOT EXISTS {STAGING} (
    id TEXT PRIMARY KEY, source TEXT, url TEXT, title TEXT, content TEXT,
    image_path TEXT, image_url TEXT, language TEXT, label TEXT,
    content_length INTEGER, word_count INTEGER,
    published_at TIMESTAMP, fetched_at TIMESTAMP
);
"""

# Nettoyage EN BASE (set-based) : entités simples, marqueur NewsAPI, balises, espaces.
SQL_CLEAN = rf"""
UPDATE {STAGING} SET
  title = trim(regexp_replace(regexp_replace(
            replace(replace(coalesce(title,''), '&amp;', '&'), '&nbsp;', ' '),
            '<[^>]+>', ' ', 'g'), '\s+', ' ', 'g')),
  content = trim(regexp_replace(regexp_replace(regexp_replace(
            replace(replace(coalesce(content,''), '&amp;', '&'), '&nbsp;', ' '),
            '\[\+\d+\s*chars?\]', '', 'g'), '<[^>]+>', ' ', 'g'), '\s+', ' ', 'g'));
"""

# Colonnes dérivées EN BASE.
SQL_FEATURES = rf"""
UPDATE {STAGING} SET
  content_length = char_length(content),
  word_count = CASE WHEN content = '' THEN 0
                    ELSE array_length(regexp_split_to_array(content, '\s+'), 1) END;
"""


def _run(sql, params=None, fetch=False):
    """Petit utilitaire : exécute une requête, commit, renvoie éventuellement le résultat."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            data = cur.fetchall() if fetch else None
            n = cur.rowcount
        conn.commit()
        return data if fetch else n
    finally:
        conn.close()


def create_staging_table():
    _run(CREATE_STAGING_SQL)


def insert_raw(publications):
    """Insère les données BRUTES en staging (pas de téléchargement d'image ici)."""
    if not publications:
        return 0
    valeurs = [tuple(p.get(c) for c in COLUMNS) for p in publications]
    sql = f"INSERT INTO {STAGING} ({', '.join(COLUMNS)}) VALUES %s ON CONFLICT (id) DO NOTHING;"
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            execute_values(cur, sql, valeurs)
            n = cur.rowcount
        conn.commit()
        return n
    finally:
        conn.close()


def clean_and_features_in_db():
    """Nettoyage + colonnes dérivées directement en SQL (scalable, set-based)."""
    _run(SQL_CLEAN)
    _run(SQL_FEATURES)


def rows_without_image():
    """Lignes de staging dont l'image n'a pas encore été téléchargée."""
    return _run(f"SELECT id, image_url FROM {STAGING} WHERE image_path IS NULL;", fetch=True)


def set_image_paths(pairs):
    """Met à jour image_path pour une liste de (chemin, id), en une seule connexion."""
    if not pairs:
        return
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            execute_batch(cur, f"UPDATE {STAGING} SET image_path=%s WHERE id=%s;", pairs)
        conn.commit()
    finally:
        conn.close()


def delete_without_image():
    """Écarte les lignes restées sans image valide (exigence multimodale)."""
    return _run(f"DELETE FROM {STAGING} WHERE image_path IS NULL;")


def promote_to_final():
    """Déplace les lignes propres de staging vers la table finale (INSERT ... SELECT)."""
    cols = ", ".join(COLUMNS)
    sql = (f"INSERT INTO publications ({cols}) SELECT {cols} FROM {STAGING} "
           f"ON CONFLICT (id) DO NOTHING;")
    return _run(sql)


def truncate_staging():
    _run(f"TRUNCATE {STAGING};")

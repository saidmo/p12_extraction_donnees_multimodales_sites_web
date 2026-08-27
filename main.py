"""Point d'entrée du projet : orchestre l'ensemble de la démarche.

Étapes : 1) créer la table
         2) extraire (NewsAPI + flux RSS de fact-checkers)
         3) transformer (nettoyage, normalisation, image, colonnes)
         4) insérer en base

Toute la logique vit dans extract.py, transform.py et database.py.
"""
import logging

from database import create_table, insert_publications
from extract import fetch_newsapi, fetch_rss
from transform import transforme

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("main")


def main():
    log.info("=== Démarrage du pipeline ===")

    # 1. Table
    create_table()

    # 2. Extraction : on combine les deux sources dans une seule liste
    articles = fetch_newsapi(query="actualité", language="fr", page_size=20)
    articles += fetch_rss()
    log.info("total extrait (toutes sources) : %d", len(articles))
    if not articles:
        log.warning("aucun article récupéré, arrêt.")
        return

    # 3. Transformation
    articles_propres = transforme(articles)
    if not articles_propres:
        log.warning("aucune publication exploitable après transformation, arrêt.")
        return

    # 4. Insertion
    inserees = insert_publications(articles_propres)
    log.info("=== Terminé : %d nouvelles publications en base ===", inserees)


if __name__ == "__main__":
    main()

"""Chargement PONCTUEL du socle labellisé Fakeddit (brique hybride).

À lancer une seule fois pour enrichir la base avec des données à label fiable :
    python seed_dataset.py

Réutilise la chaîne existante : fetch_dataset -> transforme -> insert_publications.
Séparé du pipeline live (main.py / DAGs) car ce n'est pas un flux récurrent.
"""
import logging

from database import create_table, insert_publications
from extract_dataset import fetch_dataset
from transform import transforme

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("seed_dataset")


def main():
    log.info("=== Chargement du socle labellisé Fakeddit ===")
    create_table()

    articles = fetch_dataset(echantillon=200)     # petit échantillon (200 images max)
    if not articles:
        log.warning("aucun échantillon Fakeddit, arrêt.")
        return

    propres = transforme(articles)                # nettoyage + téléchargement/validation image
    if not propres:
        log.warning("aucun échantillon exploitable après transformation, arrêt.")
        return

    inserees = insert_publications(propres)
    log.info("=== Terminé : %d échantillons labellisés insérés ===", inserees)


if __name__ == "__main__":
    main()

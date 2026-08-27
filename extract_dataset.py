"""Source labellisée (dataset) — brique 'hybride' du projet.

Contrairement à NewsAPI/RSS (sources live, non labellisées), Fakeddit est un
dataset STATIQUE fortement labellisé : il fournit une vérité terrain fiable,
adaptée à l'entraînement. On l'ingère une fois, via un point d'entrée séparé.

Licence Fakeddit : on n'utilise que les colonnes clean_title, 6_way_label et image_url.
"""
import logging
from datetime import datetime, timezone

import pandas as pd

log = logging.getLogger(__name__)

FICHIER_DEFAUT = "fakeddit/multimodal_validate.tsv"

# Correspondance des 6 catégories Fakeddit -> tes labels
#   0 = authentique | 1 = satire | 2 = fausse connexion | 3 = trompeur
#   4 = contenu manipulé | 5 = faux contenu
MAPPING_LABEL = {
    0: "true",
    1: "mixed",   # satire/parodie : ni vrai ni faux "pur"
    2: "false",   # fausse connexion texte/image
    3: "mixed",   # trompeur
    4: "false",   # image manipulée
    5: "false",   # faux contenu
}


def fetch_dataset(fichier=FICHIER_DEFAUT, echantillon=200):
    """Lit le TSV Fakeddit et renvoie une liste de dicts au format de la table.

    On ne garde que les lignes AVEC image. `echantillon` limite le nombre de
    lignes (donc de téléchargements d'images) — indispensable pour ne pas
    télécharger des milliers d'images.
    """
    try:
        df = pd.read_csv(fichier, sep="\t")
    except FileNotFoundError:
        log.error("fichier introuvable : %s", fichier)
        return []

    # Ne conserver que les lignes réellement multimodales
    df = df[(df["hasImage"] == True) & (df["image_url"].notna()) & (df["image_url"] != "")]

    # Échantillonnage reproductible (random_state fixe -> mêmes lignes à chaque run)
    if echantillon and len(df) > echantillon:
        df = df.sample(n=echantillon, random_state=42)

    publications = []
    for _, row in df.iterrows():
        publications.append({
            "id": f"fakeddit_{row['id']}",       # préfixe -> pas de collision avec les autres sources
            "source": "fakeddit",
            "url": None,                          # le dataset ne fournit pas d'URL d'article exploitable
            "title": row.get("clean_title"),
            "content": row.get("clean_title"),    # le texte du dataset est le titre nettoyé
            "image_path": None,                   # rempli au téléchargement (transforme)
            "image_url": row["image_url"],
            "language": "en",                     # Fakeddit est en anglais
            "label": MAPPING_LABEL.get(int(row["6_way_label"]), "unknown"),
            "published_at": None,
            "fetched_at": datetime.now(timezone.utc),
        })

    log.info("Fakeddit : %d échantillons labellisés préparés", len(publications))
    return publications


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    donnees = fetch_dataset(echantillon=10)
    print(f"\n{len(donnees)} échantillons.")
    for d in donnees[:5]:
        print(f"  [{d['label']:6}] {d['title']}")

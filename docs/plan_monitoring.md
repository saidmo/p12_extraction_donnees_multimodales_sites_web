# Plan de monitoring — Pipeline ETL CheckIt.AI

**Livrable :** Étape 5 — Surveillance du pipeline d'acquisition de données multimodales
**Périmètre :** DAGs Airflow (`etl_fakenews_xcom`, `etl_fakenews_staging`), sources NewsAPI + RSS, base PostgreSQL

---

## 1. Objectif

Garantir que le pipeline continue de produire des données **fraîches, complètes, valides et multimodales**, et détecter au plus tôt toute dégradation (panne de source, chute de qualité, ralentissement). Le plan définit *quoi* surveiller, *quels seuils* déclenchent une alerte, *comment* les erreurs sont gérées, et *à quelle fréquence* on vérifie.

## 2. Indicateurs surveillés et seuils d'alerte

Les quatre indicateurs proviennent des données déjà exposées par le tableau de bord (base `fakenews` et métadonnées Airflow `airflow_db`).

| Indicateur | Valeur nominale observée | Seuil d'alerte | Gravité | Cause probable |
|---|---|---|---|---|
| **Taux de succès du DAG** | 100 % | Tout run en échec ; ou < 100 % sur les 5 derniers runs | Critique | Erreur code, base indisponible |
| **Publications extraites / run** | ~40 (NewsAPI + RSS) | **= 0** → critique ; **< 10** → avertissement | Critique / Moyen | Panne réseau, clé API, blocage SSL, flux RSS cassé |
| **% de données valides** | 100 % | < 90 % | Moyen | Images cassées, textes vides |
| **Durée d'exécution du run** | ~10 s (XCom), ~17 s (staging) | > 60 s | Faible | Lenteur réseau, volume anormal |

**Justification des seuils :** ils sont calibrés sur les valeurs réelles mesurées, avec une marge. Le cas « 0 publication » est le plus important : il s'est déjà produit (blocage SSL Kaspersky) et passe **inaperçu** sans alerte, car le DAG se termine *en succès* avec une liste vide. C'est le scénario prioritaire à couvrir.

## 3. Gestion des erreurs

**Mécanismes déjà en place dans le pipeline :**

- **Nouvelle tentative automatique** : `retries=1` avec `retry_delay=1 min` dans les `default_args` de chaque DAG — absorbe les incidents transitoires (réseau momentané).
- **Isolation par source** : le `try/except` de l'extraction fait qu'une source en panne (ex. flux RSS cassé) n'interrompt pas les autres.
- **Dégradation propre** : en cas d'échec réseau total, l'extraction renvoie une liste vide et journalise l'erreur au lieu de planter → d'où la nécessité de l'alerte « 0 publication » (section 2).
- **Filtrage des images invalides** : `valide_et_telecharge_image` ignore et journalise toute image inaccessible ou corrompue, sans stopper le run.

**Mécanismes à ajouter pour la production :**

- **Notification à l'échec** : `on_failure_callback` sur le DAG (ou alerte e-mail Airflow) pour prévenir immédiatement en cas de tâche en échec.
- **Tâche de contrôle qualité** : une tâche finale qui vérifie les seuils de la section 2 (nb de lignes insérées, % valides) et lève une erreur — ou envoie une alerte — si un seuil est franchi. Cela transforme le « faux vert » (run réussi mais 0 donnée) en véritable alerte.
- **Point d'attention connu — SSL/Kaspersky** : depuis le conteneur, l'inspection TLS de l'antivirus peut bloquer les appels sortants (certificat auto-signé dans la chaîne). Contournement pour la démo : suspendre l'antivirus ; solution durable : injecter le certificat racine dans le conteneur (`REQUESTS_CA_BUNDLE` / `SSL_CERT_FILE`).

## 4. Fréquence des vérifications

| Rythme | Vérification | Moyen |
|---|---|---|
| **À chaque run** | Statut du DAG ; nb de lignes ; % valides | Alerte automatique (callback / tâche de contrôle) |
| **Quotidien** | Dernier run au vert ; fraîcheur des données | Coup d'œil au tableau de bord Streamlit |
| **Hebdomadaire** | Tendances (volume, % de labels, durées) ; espace disque du dossier `images/` ; taille de `airflow_db` | Revue du dashboard + contrôle système |
| **Mensuel** | Validité des flux RSS (ex. AFP déjà cassé) ; rotation de la clé NewsAPI ; mise à jour des dépendances | Contrôle manuel |

## 4bis. Cas particulier — le socle labellisé Fakeddit (chargement ponctuel)

Le socle labellisé (dataset Fakeddit, DAG `seed_fakeddit`) est un **chargement one-shot**,
distinct des flux live : il n'est **pas** soumis au rythme de surveillance des DAGs récurrents.

- **Déclenchement** : manuel, une seule fois (schedule=None, max_active_runs=1).
- **Relance sans risque** : `ON CONFLICT DO NOTHING` ignore les lignes déjà chargées.
- **Ce qu'on surveille lors de ce chargement** : le taux d'images valides récupérées
  (beaucoup d'URL Reddit sont périmées) et le nombre de lignes labellisées effectivement
  insérées — ponctuellement, à l'exécution, et non en continu.
- **Ce qu'on NE surveille pas** : sa fraîcheur ou sa fréquence (le dataset est statique).

Cette distinction est importante : appliquer les seuils des flux live (ex. « fraîcheur »)
au socle statique n'aurait pas de sens.

## 5. Canaux d'alerte et responsabilités

- **Canal** : e-mail (natif Airflow) et/ou message vers une messagerie d'équipe. Alertes critiques traitées sous 24 h, avertissements à la revue hebdomadaire.
- **Responsable** : l'ingénieur data en charge du pipeline reçoit les alertes ; l'escalade se fait vers l'équipe technique en cas d'incident répété.

## 6. Sécurité et traçabilité

Cohérent avec le point de vigilance « base de données sécurisée » de l'énoncé :

- **Secrets** : identifiants et clé API dans `.env`, exclu du dépôt via `.gitignore`. **Amélioration identifiée** : la clé NewsAPI apparaît en clair dans les logs (URL de requête) — la passer en en-tête HTTP plutôt qu'en paramètre d'URL, et masquer les secrets dans les logs.
- **Accès base** : principe du moindre privilège — un rôle en **lecture seule** pour le tableau de bord, distinct du rôle d'écriture du pipeline. Accès Postgres restreint au réseau Docker local.
- **Chiffrement** : clé Fernet d'Airflow pour chiffrer les connexions stockées ; en production, TLS pour toute connexion distante à la base.
- **Journalisation** : logs horodatés par tâche dans Airflow, conservés pour l'audit et le diagnostic des incidents.

## 7. Synthèse : seuil → action

| Alerte | Action immédiate |
|---|---|
| Run en échec | Consulter les logs de la tâche fautive ; relancer après correction |
| 0 publication extraite | Vérifier réseau / clé API / SSL / validité des flux RSS |
| % valides < 90 % | Inspecter les images et textes rejetés ; vérifier les sources |
| Durée > 60 s | Vérifier la charge réseau et le volume ; profiler la tâche la plus lente (`transform`) |

# Automatisation MAJ BDD – Vérifications & Logs (puis orchestration)

Ce repo contient les briques Python pour automatiser le contrôle qualité des fichiers partenaires
et la vérification des résultats de transformation (volumes vs mois précédent, règles de cohérence),
avec journalisation structurée (JSON) et décisions OK/WARNING/KO.

## Objectifs (MVP)
- Valider les fichiers entrants (métadonnées + DE) : encodage, séparateur, ordre/nom des colonnes, champs critiques
- Exécuter des contrôles "métier" : ex. email livré en clair ou SHA-256, cohérences attendues
- Analyser des métriques/reportings (volumes vs M-1)
- Produire un verdict : OK / WARNING / KO
- Générer des logs structurés (JSONL) corrélés par `run_id`

## Structure du repo
- `src/majbdd/` : code applicatif
- `config/` : règles (partners + checks + logging)
- `data/` : répertoires d’exécution (inbox/work/quarantine/archive)
- `logs/` : journaux (JSONL + dossier par run)
- `tests/` : tests unitaires

## Installation (dev)
```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip wheel
pip install -e ".[dev]"

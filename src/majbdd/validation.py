from __future__ import annotations

from pathlib import Path
import csv
import re
from typing import Any, Dict, List, Tuple

import yaml
from pydantic import BaseModel, EmailStr, ValidationError as PydanticValidationError, create_model, field_validator


class ValidationError(Exception):
    """Erreur de validation fonctionnelle (extension, DE, types, etc.)."""
    pass


_SHA256_RE = re.compile(r"^[a-fA-F0-9]{64}$")


def validate_file(
    file_path: Path,
    partner: str,
    file_key: str = "default",
    sample_size: int = 1000,
    config_path: Path = Path("config/partners.yaml"),
) -> dict:
    """
    Vérifie un fichier partenaire selon sa configuration YAML :
    - extension
    - séparateur (utilisé pour lire)
    - DE (colonnes + ordre)
    - types de données (sur échantillon) via Pydantic

    Lève ValidationError en cas de problème.
    Retourne un dict simple en cas de succès.
    """

    # 1) Charger la configuration
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    if partner not in config:
        raise ValidationError(f"Partenaire inconnu : {partner}")

    partner_cfg = config[partner] or {}
    if file_key not in partner_cfg:
        raise ValidationError(f"Fichier '{file_key}' non défini pour le partenaire '{partner}'")

    cfg = partner_cfg[file_key]

    # 2) Extension
    expected_ext = (cfg.get("extension") or "").lower()
    if file_path.suffix.lower() != expected_ext:
        raise ValidationError(f"Extension invalide : {file_path.suffix} (attendu {expected_ext})")

    # 3) Lecture + DE
    separator = cfg.get("separator")
    encoding = cfg.get("encoding", "utf-8")
    expected_columns: List[str] = cfg.get("columns") or []
    type_rules: Dict[str, str] = cfg.get("types") or {}

    if not separator:
        raise ValidationError("Configuration invalide : 'separator' manquant")
    if not expected_columns:
        raise ValidationError("Configuration invalide : 'columns' manquant ou vide")

    # Modèle Pydantic généré pour la validation "types"
    RowModel = _build_row_model(expected_columns, type_rules)

    with open(file_path, encoding=encoding, newline="") as f:
        reader = csv.reader(f, delimiter=separator)

        try:
            header = next(reader)
        except StopIteration:
            raise ValidationError("Fichier vide")

        # DE strict : noms + ordre
        if header != expected_columns:
            raise ValidationError(f"DE invalide.\nAttendu : {expected_columns}\nReçu    : {header}")

        # 4) Validation types sur échantillon
        for i, row in enumerate(reader, start=1):
            if i > sample_size:
                break

            row_dict = _row_to_dict(header, row)

            try:
                RowModel.model_validate(row_dict)
            except PydanticValidationError as e:
                # message lisible + ligne
                raise ValidationError(f"Types invalides à la ligne {i}: {e}") from e

    return {
        "status": "OK",
        "partner": partner,
        "file": file_path.name,
        "file_key": file_key,
        "sample_validated_rows": min(sample_size, i if 'i' in locals() else 0),
    }


def _row_to_dict(columns: List[str], row: List[str]) -> Dict[str, Any]:
    """
    Mappe une ligne CSV (liste) vers un dict {col: value}.
    Si la ligne a moins de valeurs que de colonnes, on complète avec None.
    Si elle en a plus, on ignore l'excédent (DE est déjà validé sur le header).
    """
    values = row[: len(columns)] + [None] * max(0, len(columns) - len(row))
    # normalisation minimale : strip sur les strings
    out: Dict[str, Any] = {}
    for col, val in zip(columns, values):
        if isinstance(val, str):
            val = val.strip()
            if val == "":
                val = None
        out[col] = val
    return out


def _build_row_model(columns: List[str], type_rules: Dict[str, str]) -> type[BaseModel]:
    """
    Construit dynamiquement un modèle Pydantic (RowModel) à partir :
    - columns : liste des colonnes attendues
    - type_rules : mapping colonne -> règle (string/email/sha256/email_or_sha256/int/float/date_... etc.)
    Pour l’instant on implémente surtout ce dont tu as parlé : email / sha256 / email_or_sha256 / string.
    """

    fields: Dict[str, Tuple[Any, Any]] = {}
    validators: Dict[str, classmethod] = {}

    # champs : on rend tout "optionnel" par défaut (None autorisé)
    # tu pourras ajouter plus tard une règle "required: true" dans le YAML si besoin.
    for col in columns:
        rule = (type_rules.get(col) or "string").lower()

        if rule == "email":
            # EmailStr valide le format email
            fields[col] = (EmailStr | None, None)

        elif rule == "sha256":
            # on garde str|None + validator regex
            fields[col] = (str | None, None)

            @field_validator(col)
            def _v_sha256(v: str | None) -> str | None:
                if v is None:
                    return None
                if not _SHA256_RE.fullmatch(v):
                    raise ValueError("doit être un SHA-256 hexadécimal (64 caractères)")
                return v

            validators[f"validate_{col}_sha256"] = _v_sha256

        elif rule == "email_or_sha256":
            fields[col] = (str | EmailStr | None, None)

            @field_validator(col)
            def _v_email_or_sha256(v: Any) -> Any:
                if v is None:
                    return None
                # si c'est déjà un EmailStr (pydantic), OK
                s = str(v)
                if "@" in s:
                    # EmailStr fera le job si le type est EmailStr,
                    # mais si on tombe ici avec str, on laisse passer et on reste permissif.
                    return v
                if not _SHA256_RE.fullmatch(s):
                    raise ValueError("doit être un email (clair) ou un SHA-256 (64 hex)")
                return v

            validators[f"validate_{col}_email_or_sha256"] = _v_email_or_sha256

        else:
            # string (default)
            fields[col] = (str | None, None)

    RowModel = create_model("RowModel", **fields)  # type: ignore[arg-type]

    # Inject validators dynamiques
    for name, fn in validators.items():
        setattr(RowModel, name, fn)

    return RowModel
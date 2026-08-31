from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from decimal import (
    Decimal,
    InvalidOperation,
    ROUND_HALF_UP
)


MISSING = "Non détecté"
MISSING_DATE = "Non détectée"


CLIENT_LABELS = [
    r"NOM\s+DU\s+CLIENT",
    r"CL[IL]ENT",
    r"DESTINATAIRE",
    r"ADRESSE\s+DE\s+FACTURATION",
    r"ADRESSE\s+FACTURATION",
    r"ADRESSE\s+A",
    r"FACTURE\s+A(?!\s+LA\s+SOMME)",
    r"ACHETEUR",
    r"CUSTOMER",
    r"BILL\s+TO",
]


PROVIDER_LABELS = [
    r"FOURNISSEUR",
    r"VENDEUR",
    r"EMETTEUR",
    r"EMIS\s+PAR",
    r"RAISON\s+SOCIALE",
    r"SUPPLIER",
    r"SELLER",
    r"ISSUER",
]


# Libellés client à forte valeur sémantique.
# Ils ont priorité sur un simple mot "client" afin de ne pas
# confondre "Code client" ou "Contact client" avec le nom du client.
CLIENT_STRONG_LABELS = [
    r"NOM\s+DU\s+CLIENT",
    r"DESTINATAIRE",
    r"ADRESSE\s+DE\s+FACTURATION",
    r"ADRESSE\s+FACTURATION",
    r"ADRESSE\s+A",
    r"FACTURE\s+A(?!\s+LA\s+SOMME)",
    r"ACHETEUR",
    r"CUSTOMER",
    r"BILL\s+TO",
]

CLIENT_EXCLUDED_LABELS = [
    r"CODE\s+CLIENT",
    r"CONTACT\s+CLIENT",
    r"REFERENCE\s+CLIENT",
    r"REF\.?\s+CLIENT",
    r"ID\s+CLIENT",
    r"IDENTIFIANT\s+CLIENT",
    r"NUMERO\s+CLIENT",
    r"N[°ºO]\s*CLIENT",
]

ENTITY_COMPANY_MARKERS = (
    r"\b(?:"
    r"SARL|S\.?A\.?R\.?L\.?|SA|S\.?A\.?|SAS|SASU|EURL|"
    r"SOCIETE|ETABLISSEMENT|ETS\.?|ENTREPRISE|COMPANY|"
    r"HOSPITALITY|SOLUTIONS|TELECOM|GROUP|GROUPE"
    r")\b"
    r"|"
    # DISTRIBUTION/COMMERCE/SERVICES/INDUSTRIE sont souvent employés
    # de façon descriptive ("distribution de pièces...", "commerce
    # de gros") plutôt que comme suffixe de raison sociale ("XYZ
    # Distribution"). On ne les compte comme marqueur d'entreprise
    # que lorsqu'ils ne sont PAS suivis de "DE".
    r"\b(?:DISTRIBUTION|COMMERCE|SERVICES|INDUSTRIE)\b(?!\s+DE\b)"
)


def _ascii(value: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize(
            "NFKD",
            value or ""
        )
        if not unicodedata.combining(
            character
        )
    )


def norm(value: str) -> str:
    return re.sub(
        r"\s+",
        " ",
        _ascii(value).upper()
    ).strip()


def clean(
    value: str | None
) -> str:
    return re.sub(
        r"\s+",
        " ",
        value or ""
    ).strip(
        " :-|,;."
    )


def _matches(
    value: str,
    patterns: list[str]
) -> bool:
    return any(
        re.search(
            pattern,
            value,
            re.IGNORECASE
        )
        for pattern in patterns
    )


# Lettres OCR fréquemment confondues avec des chiffres. N'est utilisé
# que pour les identifiants légaux marocains (RC/IF/CNSS/ICE), qui
# sont toujours purement numériques — pas pour les noms d'entreprise
# ou autres champs textuels, où ces lettres sont légitimes.
_OCR_DIGIT_LOOKALIKES = str.maketrans(
    {
        "O": "0",
        "o": "0",
        "I": "1",
        "l": "1",
        "S": "5",
        "s": "5",
        "B": "8",
        "Z": "2",
        "z": "2",
    }
)


def _digitize_ocr_value(value: str) -> str:
    """
    Convertit un fragment de texte OCR en chiffres, en corrigeant
    d'abord les confusions lettre/chiffre courantes (ex. "S645687"
    -> "5645687") avant de retirer tout caractère non numérique
    restant.
    """
    return re.sub(
        r"\D",
        "",
        (value or "").translate(_OCR_DIGIT_LOOKALIKES)
    )


# =========================================================
# MONTANTS
# =========================================================

def parse_amount(
    value: str | None
) -> Decimal | None:

    if not value:
        return None

    raw = str(value).upper()

    raw = (
        raw
        .replace("MAD", "")
        .replace("DHS", "")
        .replace("DH", "")
    )

    raw = re.sub(
        r"[^0-9,\.\- ]",
        "",
        raw
    ).replace(
        " ",
        ""
    )

    if not raw:
        return None

    try:
        if (
            "," in raw
            and "." in raw
        ):
            if (
                raw.rfind(",")
                > raw.rfind(".")
            ):
                raw = (
                    raw
                    .replace(".", "")
                    .replace(",", ".")
                )
            else:
                raw = raw.replace(
                    ",",
                    ""
                )

        elif "," in raw:
            raw = raw.replace(
                ",",
                "."
            )

        return Decimal(raw)

    except (
        InvalidOperation,
        ValueError
    ):
        return None


def fmt(
    value: Decimal | None
) -> str:

    if value is None:
        return MISSING

    return str(
        value.quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP
        )
    )


# =========================================================
# OCR ITEMS
# =========================================================

def prepare_items(
    raw_items: list[dict] | None
) -> list[dict]:

    result = []

    if raw_items is None:
        raw_items = []

    for raw in raw_items:

        text = clean(
            str(
                raw.get(
                    "text",
                    ""
                )
            )
        )

        box = raw.get("box")

        if box is None:
            box = [0, 0, 0, 0]

        if hasattr(
            box,
            "tolist"
        ):
            box = box.tolist()

        if (
            not text
            or len(box) < 4
        ):
            continue

        x1, y1, x2, y2 = [
            float(value)
            for value in box[:4]
        ]

        page_width_raw = raw.get(
            "page_width"
        )

        page_height_raw = raw.get(
            "page_height"
        )

        page_width = float(
            page_width_raw
            if page_width_raw is not None
            else max(x2, 1)
        )

        page_height = float(
            page_height_raw
            if page_height_raw is not None
            else max(y2, 1)
        )

        score_raw = raw.get(
            "score"
        )

        try:
            score = float(
                score_raw
                if score_raw is not None
                else 0
            )
        except (
            TypeError,
            ValueError
        ):
            score = 0.0

        result.append(
            {
                "text": text,
                "n": norm(text),

                "score": score,

                "page": int(
                    raw.get("page")
                    or 1
                ),

                "box": [
                    x1,
                    y1,
                    x2,
                    y2
                ],

                "x": (
                    (x1 + x2) / 2
                ) / max(
                    page_width,
                    1
                ),

                "y": (
                    (y1 + y2) / 2
                ) / max(
                    page_height,
                    1
                ),

                "height": max(
                    y2 - y1,
                    1
                ),

                "page_width":
                    page_width,

                "page_height":
                    page_height,
            }
        )

    return result


# =========================================================
# RECONSTRUIRE LES LIGNES VISUELLES
# =========================================================

def build_lines(
    items: list[dict],
    fallback_text: str = ""
) -> list[dict]:

    if not items:

        raw_lines = [
            clean(line)
            for line
            in (
                fallback_text
                or ""
            ).splitlines()
            if clean(line)
        ]

        return [
            {
                "page": 1,
                "text": line,
                "n": norm(line),
                "y": index / max(
                    len(raw_lines),
                    1
                ),
                "items": []
            }
            for index, line
            in enumerate(
                raw_lines
            )
        ]

    result = []

    pages = sorted(
        {
            item["page"]
            for item in items
        }
    )

    for page in pages:

        page_items = sorted(
            [
                item
                for item in items
                if item["page"]
                == page
            ],
            key=lambda item: (
                item["box"][1],
                item["box"][0]
            )
        )

        groups = []

        for item in page_items:

            target = None

            for group in reversed(
                groups[-8:]
            ):

                center_y = sum(
                    (
                        element["box"][1]
                        + element["box"][3]
                    ) / 2
                    for element in group
                ) / len(group)

                average_height = sum(
                    element["height"]
                    for element in group
                ) / len(group)

                item_center_y = (
                    item["box"][1]
                    + item["box"][3]
                ) / 2

                if abs(
                    item_center_y
                    - center_y
                ) <= max(
                    average_height * 0.65,
                    item["height"] * 0.65,
                    10
                ):
                    target = group
                    break

            if target is None:
                groups.append(
                    [item]
                )
            else:
                target.append(
                    item
                )

        for group in groups:

            group.sort(
                key=lambda item:
                    item["box"][0]
            )

            line_text = " ".join(
                item["text"]
                for item in group
            )

            result.append(
                {
                    "page": page,
                    "text": line_text,
                    "n": norm(
                        line_text
                    ),
                    "y": sum(
                        item["y"]
                        for item in group
                    ) / len(group),
                    "items": group
                }
            )

    return result


# =========================================================
# CLIENT / FOURNISSEUR
# =========================================================

def _looks_like_identifier_code(value: str | None) -> bool:
    """Évite de prendre un code métier pour un nom de société/client."""
    value = clean(value)

    if not value:
        return False

    compact = re.sub(r"[^A-Za-z0-9]", "", value)
    digits = sum(character.isdigit() for character in compact)
    letters = sum(character.isalpha() for character in compact)

    # Exemples visés : CU1905-0001, CL-2024-001, 000001.
    # On ne rejette pas des noms courts comme "3M".
    return (
        " " not in value
        and digits >= 3
        and letters <= 6
        and len(compact) >= 6
    )


def _entity_ok(
    value: str | None
) -> bool:

    value = clean(value)

    if (
        len(value) < 2
        or not re.search(
            r"[A-Za-zÀ-ÿ]",
            value
        )
    ):
        return False

    normalized = norm(value)

    # Libellés/champs qui ne sont jamais des raisons sociales.
    if re.search(
        (
            r"\b(?:"
            r"FACTURE|INVOICE|DATE|ICE|IF|RC|CNSS|"
            r"TOTAL|TVA|TTC|HT|TELEPHONE|TEL|EMAIL|"
            r"PAGE|RIB|BANQUE|PATENTE|REFERENCE|"
            r"CONTACT\s+CLIENT|CODE\s+CLIENT|REFERENCE\s+CLIENT|"
            r"DESTINATAIRE|ADRESSE\s+DE\s+FACTURATION|"
            r"ADRESSE\s+A|EMIS\s+PAR|EMETTEUR|FOURNISSEUR|"
            r"VENDEUR|RAISON\s+SOCIALE"
            r")\b"
        ),
        normalized
    ):
        return False

    if _looks_like_identifier_code(value):
        return False

    return True

def _anchor(
    items: list[dict],
    patterns: list[str]
):

    found = [
        item
        for item in items
        if _matches(
            item["n"],
            patterns
        )
    ]

    if not found:
        return None

    return sorted(
        found,
        key=lambda item: (
            item["page"],
            item["y"],
            item["x"]
        )
    )[0]


def _client_anchor(
    items: list[dict]
):
    """
    Cherche l'ancre client sans confondre :
    - Code client
    - Contact client
    - Référence client
    avec le véritable destinataire/acheteur.
    """
    candidates = []

    for item in items:
        normalized = item["n"]

        if _matches(
            normalized,
            CLIENT_EXCLUDED_LABELS
        ):
            continue

        priority = 0

        if _matches(
            normalized,
            CLIENT_STRONG_LABELS
        ):
            priority = 300
        elif re.search(
            r"\bCL[IL]ENT\b",
            normalized
        ):
            priority = 120

        if priority <= 0:
            continue

        # Les libellés courts et explicites sont plus fiables.
        if len(normalized.split()) <= 5:
            priority += 20

        candidates.append(
            (
                priority,
                item
            )
        )

    if not candidates:
        return None

    candidates.sort(
        key=lambda entry: (
            -entry[0],
            entry[1]["page"],
            entry[1]["y"],
            entry[1]["x"]
        )
    )

    return candidates[0][1]


def _provider_anchor(
    items: list[dict]
):
    """Priorise les libellés explicites d'émetteur/fournisseur."""
    priorities = [
        (r"EMIS\s+PAR", 340),
        (r"EMETTEUR", 330),
        (r"FOURNISSEUR", 320),
        (r"VENDEUR", 310),
        (r"RAISON\s+SOCIALE", 300),
        (r"SUPPLIER", 290),
        (r"SELLER", 280),
        (r"ISSUER", 270),
    ]

    candidates = []

    for item in items:
        for pattern, priority in priorities:
            if re.search(
                pattern,
                item["n"],
                re.IGNORECASE
            ):
                candidates.append(
                    (
                        priority,
                        item
                    )
                )
                break

    if not candidates:
        return None

    candidates.sort(
        key=lambda entry: (
            -entry[0],
            entry[1]["page"],
            entry[1]["y"],
            entry[1]["x"]
        )
    )

    return candidates[0][1]

def _inline_entity(
    text: str,
    patterns: list[str]
):

    normalized = norm(text)

    # Un libellé "Code client" / "Contact client" ne représente
    # jamais la raison sociale du client.
    if _matches(
        normalized,
        CLIENT_EXCLUDED_LABELS
    ):
        return None

    for pattern in patterns:

        match = re.search(
            rf"(?:{pattern})"
            rf"\s*[:\-]?\s*(.+)$",
            normalized,
            re.IGNORECASE
        )

        if not match:
            continue

        original_parts = re.split(
            r"[:\-]",
            text,
            maxsplit=1
        )

        candidate = clean(
            original_parts[1]
            if len(
                original_parts
            ) == 2
            else match.group(1)
        )

        # Si plusieurs champs OCR sont fusionnés sur la même ligne,
        # on coupe dès qu'un nouveau libellé commence.
        candidate = re.split(
            (
                r"\b(?:"
                r"ICE|IF|RC|CNSS|DATE|TEL|TELEPHONE|EMAIL|"
                r"CONTACT\s+CLIENT|CODE\s+CLIENT|REFERENCE\s+CLIENT|"
                r"DESTINATAIRE|ADRESSE\s+DE\s+FACTURATION|"
                r"ADRESSE\s+A|FACTURE|INVOICE"
                r")\b"
            ),
            candidate,
            maxsplit=1,
            flags=re.IGNORECASE
        )[0]

        if _entity_ok(
            candidate
        ):
            return candidate

    return None

def _near_entity(
    items: list[dict],
    anchor,
    patterns: list[str],
    role: str
):

    if not anchor:
        return None

    inline = _inline_entity(
        anchor["text"],
        patterns
    )

    if inline:
        return inline

    candidates = []

    normalized_counts = {}
    for item in items:
        key = norm(item["text"])
        normalized_counts[key] = (
            normalized_counts.get(key, 0) + 1
        )

    for item in items:

        if (
            item is anchor
            or item["page"]
            != anchor["page"]
            or not _entity_ok(
                item["text"]
            )
        ):
            continue

        delta_y = (
            item["y"]
            - anchor["y"]
        )

        delta_x = (
            item["x"]
            - anchor["x"]
        )

        score = None

        # Même ligne : le texte placé à droite du libellé est
        # le cas le plus fiable (ex. "Emis par EJ SOLUTIONS").
        if (
            -0.030 <= delta_y <= 0.030
            and -0.03 <= delta_x <= 0.58
        ):
            score = (
                130
                - int(
                    abs(delta_x)
                    * 100
                )
            )

        # Bloc situé juste sous le libellé.
        elif (
            0 < delta_y <= 0.17
            and abs(
                delta_x
            ) <= 0.28
        ):
            score = (
                95
                - int(
                    delta_y
                    * 210
                )
            )

        if score is None:
            continue

        normalized = item["n"]

        if re.search(
            (
                r"\b(?:"
                r"CAPITAL|TELEPHONE|TEL|ICE|IF|RC|CNSS|"
                r"ADRESSE|RIB|BANQUE|PATENTE|DATE|FACTURE|"
                r"CONTACT\s+CLIENT|CODE\s+CLIENT|REFERENCE\s+CLIENT"
                r")\b"
            ),
            normalized
        ):
            score -= 120

        if role == "provider":
            if re.search(
                ENTITY_COMPANY_MARKERS,
                normalized
            ):
                score += 45

        elif role == "client":
            if _looks_like_identifier_code(
                item["text"]
            ):
                score -= 150

        # Une raison sociale répétée dans l'en-tête et/ou le pied
        # de page est généralement une société réelle, pas un label.
        repeat_count = normalized_counts.get(
            norm(item["text"]),
            1
        )
        if repeat_count > 1:
            score += min(
                30,
                (repeat_count - 1) * 12
            )

        candidates.append(
            (
                score,
                item["text"]
            )
        )

    candidates.sort(
        reverse=True,
        key=lambda item:
            item[0]
    )

    if (
        candidates
        and candidates[0][0] > 0
    ):
        return candidates[0][1]

    return None

def extract_entities(
    items: list[dict],
    lines: list[dict]
):

    client_anchor = _client_anchor(
        items
    )

    provider_anchor = _provider_anchor(
        items
    )

    client = _near_entity(
        items,
        client_anchor,
        CLIENT_LABELS,
        "client"
    )

    provider = _near_entity(
        items,
        provider_anchor,
        PROVIDER_LABELS,
        "provider"
    )

    # Fallback client basé sur les lignes reconstruites.
    if not client:

        line_candidates = []

        for index, line in enumerate(lines):
            normalized = line["n"]

            if _matches(
                normalized,
                CLIENT_EXCLUDED_LABELS
            ):
                continue

            priority = 0
            if _matches(
                normalized,
                CLIENT_STRONG_LABELS
            ):
                priority = 200
            elif re.search(
                r"\bCL[IL]ENT\b",
                normalized
            ):
                priority = 80

            if priority <= 0:
                continue

            inline = _inline_entity(
                line["text"],
                CLIENT_LABELS
            )

            if inline:
                line_candidates.append(
                    (
                        priority + 60,
                        inline
                    )
                )

            for next_line in lines[
                index + 1:
                index + 4
            ]:
                if next_line["page"] != line["page"]:
                    break

                candidate = clean(
                    next_line["text"]
                )

                if _entity_ok(candidate):
                    line_candidates.append(
                        (
                            priority,
                            candidate
                        )
                    )
                    break

        if line_candidates:
            line_candidates.sort(
                reverse=True,
                key=lambda entry:
                    entry[0]
            )
            client = line_candidates[0][1]

    # Pas de libellé fournisseur exploitable : recherche d'une
    # raison sociale dans l'en-tête / les mentions légales.
    if not provider:

        candidates = []

        counts = {}
        for item in items:
            key = norm(item["text"])
            counts[key] = counts.get(key, 0) + 1

        for item in items:

            if not _entity_ok(
                item["text"]
            ):
                continue

            # Un nom d'entreprise ne contient (quasiment) jamais de
            # chiffres, contrairement aux numéros de référence, de
            # BL, de facture ou aux dates (ex. "BL N° : 001617/2025").
            if re.search(
                r"\d",
                item["text"]
            ):
                continue

            normalized = item["n"]

            # Filtre les fragments OCR trop courts (ex. bribe de logo
            # comme "space" au lieu de "Espace Caoutchouc &
            # Transmission") qui ne portent aucun signal de raison
            # sociale. Un vrai nom d'entreprise contient soit un
            # espace (plusieurs mots), soit un marqueur reconnu.
            if (
                " " not in item["text"]
                and len(item["text"]) < 8
                and not re.search(
                    ENTITY_COMPANY_MARKERS,
                    normalized
                )
            ):
                continue

            score = 0

            if item["y"] < 0.38:
                # Bonus proportionnel plutôt que binaire : plus l'élément
                # est haut dans la page, plus le score augmente. Cela
                # départage naturellement le vrai nom de l'entreprise
                # (généralement tout en haut) d'un sous-titre/slogan
                # situé juste en dessous, quand aucun autre signal ne
                # permet de trancher.
                score += 35 + int(
                    (0.38 - item["y"]) * 100
                )

            if item["y"] > 0.82:
                score += 20

            # Un vrai nom d'entreprise complet contient généralement
            # plusieurs mots ; les bribes OCR de logo (ex. "space",
            # "cdoutchouc", "& transmission") sont soit un seul mot,
            # soit un fragment partiel plus court que le nom complet.
            # Le bonus croît avec le nombre de mots afin que le nom
            # complet l'emporte nettement sur n'importe quelle bribe
            # partielle du même logo, quelle que soit sa position.
            word_count = len(
                item["text"].split()
            )
            if word_count > 1:
                score += 20 * min(
                    word_count,
                    5
                )

            # Un vrai nom d'entreprise est court ; un slogan ou une
            # description ("Importation et distribution de pièces
            # de transmission industrielle...") est en général
            # bien plus long qu'une raison sociale, même quand
            # celle-ci a plusieurs mots. Ce signal départage les
            # deux de façon plus fiable que le seul nombre de mots.
            if len(item["text"]) > 50:
                score -= 60

            if re.search(
                ENTITY_COMPANY_MARKERS,
                normalized
            ):
                score += 50

            if counts.get(
                norm(item["text"]),
                1
            ) > 1:
                score += 30

            if re.search(
                (
                    r"\b(?:"
                    r"CLIENT|DESTINATAIRE|NOM DU CLIENT|"
                    r"ADRESSE DE FACTURATION|CONTACT CLIENT|"
                    r"CODE CLIENT|CAPITAL|TELEPHONE|ADRESSE|"
                    r"FACTURE|ICE|IF|RC|CNSS"
                    r")\b"
                ),
                normalized
            ):
                score -= 100

            if (
                client_anchor
                and item["page"]
                == client_anchor["page"]
                # Un titre de page (logo, raison sociale en
                # en-tête) est toujours nettement AU-DESSUS du
                # tableau d'informations facture où se trouve
                # l'ancre client — jamais à côté ni dedans. On
                # exclut donc les éléments situés bien plus haut
                # que l'ancre, pour éviter qu'un texte large dont
                # le centre tombe par coïncidence dans la marge
                # de tolérance X soit pénalisé à tort.
                and item["y"]
                >= client_anchor["y"] - 0.05
                and abs(
                    item["x"]
                    - client_anchor["x"]
                ) < 0.30
                and abs(
                    item["y"]
                    - client_anchor["y"]
                ) < 0.18
            ):
                score -= 90

            if (
                client
                and norm(
                    item["text"]
                ) == norm(client)
            ):
                score -= 150

            candidates.append(
                (
                    score,
                    item["text"]
                )
            )

        candidates.sort(
            reverse=True,
            key=lambda item:
                item[0]
        )

        if (
            candidates
            and candidates[0][0] > 0
        ):
            provider = (
                candidates[0][1]
            )

    return (
        provider or MISSING,
        client or MISSING
    )

def extract_date(
    lines: list[dict]
):

    # Regex locale pour éviter toute dépendance
    # à une constante globale DATE_RE.
    date_re = re.compile(
        (
            r"\b("
            r"\d{1,2}[./\-]\d{1,2}"
            r"[./\-]\d{2,4}"
            r"|"
            r"\d{4}[./\-]\d{1,2}"
            r"[./\-]\d{1,2}"
            r")\b"
        )
    )

    candidates = []

    for index, line in enumerate(
        lines
    ):

        normalized = line["n"]

        if re.search(
            (
                r"ECHEANCE|PAIEMENT|"
                r"REGLEMENT|LIVRAISON|"
                r"ARRIVEE|DEPART|SEJOUR"
            ),
            normalized
        ):
            continue

        for date in date_re.findall(
            line["text"]
        ):

            score = (
                20
                if line["y"] < 0.40
                else 0
            )

            if re.search(
                (
                    r"DATE\s+(?:DE\s+LA\s+)?"
                    r"FACTURE|"
                    r"DATE\s+D.?EMISSION|"
                    r"FACTURE\s+DU"
                ),
                normalized
            ):
                score += 120

            elif re.search(
                r"^DATE\b",
                normalized
            ):
                score += 95

            elif re.search(
                r"\bLE\s+\d",
                normalized
            ):
                score += 70

            candidates.append(
                (
                    score,
                    date
                )
            )

        # Exemple OCR :
        # Date
        # 26/12/2019
        if re.fullmatch(
            r"DATE\s*:?",
            normalized
        ):

            for next_line in (
                lines[
                    index + 1:
                    index + 4
                ]
            ):

                if (
                    next_line["page"]
                    != line["page"]
                ):
                    break

                match = date_re.search(
                    next_line["text"]
                )

                if match:

                    candidates.append(
                        (
                            110,
                            match.group(1)
                        )
                    )

                    break

    candidates.sort(
        reverse=True,
        key=lambda value:
            value[0]
    )

    if candidates:
        return candidates[0][1]

    return MISSING_DATE


# =========================================================
# NUMERO FACTURE
# =========================================================

def detect_invoice_reference(
    text: str
):

    patterns = [
        (
            r"\bFACTURE\s*"
            r"(?:N[°ºO]|NO|NUMERO|#)?"
            r"\s*[:\-]?\s*"
            r"([A-Z0-9][A-Z0-9./_\-]{2,})"
        ),
        (
            r"\bN[°ºO]\s*FACTURE"
            r"\s*[:\-]?\s*"
            r"([A-Z0-9][A-Z0-9./_\-]{2,})"
        ),
        (
            r"\bREFERENCE\s+FACTURE"
            r"\s*[:\-]?\s*"
            r"([A-Z0-9][A-Z0-9./_\-]{2,})"
        ),
        (
            r"\bREF\.?\s*[:\-]\s*"
            r"([A-Z0-9][A-Z0-9./_\-]{2,})"
        ),
    ]

    raw_lines = (
        text
        or ""
    ).splitlines()[:40]

    for line in raw_lines:

        normalized = norm(line)

        for pattern in patterns:

            match = re.search(
                pattern,
                normalized
            )

            if match:
                return (
                    match
                    .group(1)
                    .strip(
                        " .,:;-"
                    )
                )

    # Fallback : libellé "Numéro" (ou variantes) seul sur sa ligne,
    # valeur trouvée quelques lignes plus bas — cas des tableaux OCR
    # où le libellé et la valeur sont sur des blocs séparés, ex. :
    #   Numéro
    #   Date
    #   Cllent
    #
    #   001614/2025
    #   EJ SOLUTIONS
    # N'est utilisé que si aucun des patterns ci-dessus n'a matché,
    # donc les formats déjà reconnus (FA1905-0002, 0005/2019, ...)
    # continuent de passer par les patterns existants.
    standalone_label = re.compile(
        r"^(?:NUMERO|N[°ºO]\.?\s*(?:DE\s+)?(?:LA\s+)?FACTURE)$"
    )

    for index, line in enumerate(raw_lines):

        normalized = norm(clean(line))

        if not standalone_label.match(normalized):
            continue

        for candidate in raw_lines[index + 1:index + 8]:

            candidate_clean = clean(candidate)

            if not candidate_clean:
                continue

            if not re.search(r"\d", candidate_clean):
                continue

            if re.fullmatch(
                r"[A-Z0-9][A-Z0-9./_\-]{2,}",
                norm(candidate_clean)
            ):
                return candidate_clean.strip(" .,:;-")

        break

    return None


# =========================================================
# ICE / IF / RC / CNSS
# =========================================================

def _numeric_neighbor(
    items,
    anchor,
    minimum,
    maximum
):

    candidates = []

    for item in items:

        if (
            item is anchor
            or item["page"]
            != anchor["page"]
        ):
            continue

        digits = re.sub(
            r"\D",
            "",
            item["text"]
        )

        if not (
            minimum
            <= len(digits)
            <= maximum
        ):
            continue

        delta_y = (
            item["y"]
            - anchor["y"]
        )

        delta_x = (
            item["x"]
            - anchor["x"]
        )

        if (
            -0.025 <= delta_y <= 0.025
            and 0 <= delta_x <= 0.45
        ):
            candidates.append(
                (
                    100
                    - int(
                        delta_x * 100
                    ),
                    digits,
                    item
                )
            )

        elif (
            0 < delta_y <= 0.08
            and abs(
                delta_x
            ) <= 0.12
        ):
            candidates.append(
                (
                    70
                    - int(
                        delta_y * 300
                    ),
                    digits,
                    item
                )
            )

    candidates.sort(
        reverse=True,
        key=lambda value:
            value[0]
    )

    if candidates:
        return (
            candidates[0][1],
            candidates[0][2]
        )

    return None


def identifier_candidates(
    items,
    kind
):

    config = {
        "ice": (
            r"[I1]\s*\.?\s*C\s*\.?\s*E\s*\.?",
            15,
            15
        ),

        "if": (
            (
                r"[I1]\s*\.?\s*F\s*\.?"
                r"|IDENTIFIANT\s+FISCAL"
            ),
            5,
            12
        ),

        "rc": (
            (
                r"R\s*\.?\s*C\s*\.?"
                r"|REGISTRE\s+"
                r"(?:DU|DE)?\s*COMMERCE"
            ),
            1,
            12
        ),

        "cnss": (
            r"C\s*\.?\s*N\s*\.?\s*S\s*\.?\s*S\s*\.?",
            4,
            12
        )
    }

    label, minimum, maximum = (
        config[kind]
    )

    result = []

    for item in items:

        if not re.search(
            label,
            item["n"],
            re.IGNORECASE
        ):
            continue

        match = re.search(
            (
                rf"(?:{label})"
                rf"\s*[:#Nn°º.\-]?\s*"
                rf"([0-9OoIlSsBbZz]"
                rf"[0-9 .OoIlSsBbZz]{{0,24}})"
            ),
            item["text"],
            re.IGNORECASE
        )

        if match:

            value = _digitize_ocr_value(
                match.group(1)
            )

            if len(value) > maximum:
                value = value[:maximum]

            if (
                minimum
                <= len(value)
                <= maximum
            ):

                result.append(
                    {
                        "value": value,
                        "item": item,
                        "source": "inline"
                    }
                )

                continue

        neighbor = _numeric_neighbor(
            items,
            item,
            minimum,
            maximum
        )

        if neighbor:

            value, value_item = (
                neighbor
            )

            result.append(
                {
                    "value": value,
                    "item": value_item,
                    "source": "neighbor"
                }
            )

    deduplicated = []

    seen = set()

    for candidate in result:

        key = (
            candidate["value"],
            candidate["item"]["page"],
            round(
                candidate["item"]["x"],
                2
            ),
            round(
                candidate["item"]["y"],
                2
            )
        )

        if key not in seen:

            seen.add(key)

            deduplicated.append(
                candidate
            )

    return deduplicated

def _context(
    items,
    anchor
):

    return " ".join(
        item["n"]
        for item in items
        if (
            item["page"]
            == anchor["page"]
            and abs(
                item["x"]
                - anchor["x"]
            ) <= 0.35
            and abs(
                item["y"]
                - anchor["y"]
            ) <= 0.13
        )
    )


def _client_zone_match(
    item,
    client_anchor
) -> bool:

    if not client_anchor:
        return False

    if (
        item["page"]
        != client_anchor["page"]
    ):
        return False

    delta_x = (
        item["x"]
        - client_anchor["x"]
    )

    delta_y = (
        item["y"]
        - client_anchor["y"]
    )

    return (
        abs(delta_y) <= 0.17
        and abs(delta_x) <= 0.30
    )


def _supplier_legal_context(
    context: str
) -> bool:

    return bool(
        re.search(
            (
                r"FOURNISSEUR|VENDEUR|EMETTEUR|"
                r"SIEGE SOCIAL|CAPITAL|PATENTE|"
                r"CNSS|REGISTRE|RC|IF|"
                r"SARL|S\.?A\.?R\.?L\.?|"
                r"SOCIETE|ETABLISSEMENT|ETS|"
                r"ENTREPRISE|SUPPLIER|SELLER"
            ),
            context
        )
    )


def _looks_like_compact_date_digits(
    value: str
) -> bool:
    """Détecte DDMMYYYY / YYYYMMDD uniquement pour pénaliser un voisin OCR."""
    digits = re.sub(r"\D", "", value or "")

    if len(digits) != 8:
        return False

    try:
        first4 = int(digits[:4])
        day = int(digits[:2])
        month = int(digits[2:4])
        year = int(digits[4:8])

        if 1 <= day <= 31 and 1 <= month <= 12 and 1900 <= year <= 2100:
            return True

        year2 = first4
        month2 = int(digits[4:6])
        day2 = int(digits[6:8])
        return (
            1900 <= year2 <= 2100
            and 1 <= month2 <= 12
            and 1 <= day2 <= 31
        )

    except ValueError:
        return False


def _id_score(
    candidate,
    items,
    role,
    client_anchor=None
):

    item = candidate["item"]

    context = _context(
        items,
        item
    )

    client_context = bool(
        re.search(
            (
                r"CL[IL]ENT|NOM DU CLIENT|"
                r"DESTINATAIRE|ADRESSE DE FACTURATION|"
                r"CUSTOMER|BILL TO"
            ),
            context
        )
    )

    supplier_context = (
        _supplier_legal_context(
            context
        )
    )

    in_client_zone = (
        _client_zone_match(
            item,
            client_anchor
        )
    )

    score = int(
        item.get(
            "score",
            0
        ) * 10
    )

    source = candidate.get(
        "source",
        "neighbor"
    )

    # Une valeur écrite dans le même bloc que son libellé est
    # beaucoup plus fiable qu'un nombre simplement voisin.
    if source == "inline":
        score += 180
    elif source == "line":
        score += 135
    else:
        score += 0

        # Une date proche de "IF"/"RC" ne doit pas gagner face à
        # l'identifiant réellement étiqueté ailleurs dans le document.
        if _looks_like_compact_date_digits(
            candidate.get("value", "")
        ):
            score -= 140

    if role == "client":

        if client_context:
            score += 130

        if in_client_zone:
            score += 100

        if supplier_context:
            score -= 35

    else:

        if supplier_context:
            score += 120

        if client_context:
            score -= 145

        if in_client_zone:
            score -= 125

        # Mentions légales en pied de facture.
        if item["y"] > 0.78:
            score += 40

    return score

def _identifier_candidates_from_lines(
    items,
    lines,
    kind
):

    config = {
        "ice": (
            r"[I1]\s*\.?\s*C\s*\.?\s*E\s*\.?",
            15,
            15
        ),
        "if": (
            (
                r"[I1]\s*\.?\s*F\s*\.?"
                r"|IDENTIFIANT\s+FISCAL"
            ),
            5,
            12
        ),
        "rc": (
            (
                r"R\s*\.?\s*C\s*\.?"
                r"|REGISTRE\s+"
                r"(?:DU|DE)?\s*COMMERCE"
            ),
            1,
            12
        ),
        "cnss": (
            r"C\s*\.?\s*N\s*\.?\s*S\s*\.?\s*S\s*\.?",
            4,
            12
        )
    }

    label, minimum, maximum = (
        config[kind]
    )

    result = []

    for line in lines:

        if not re.search(
            label,
            line["n"],
            re.IGNORECASE
        ):
            continue

        # finditer est important : une ligne légale peut contenir
        # RC + IF + CNSS + ICE simultanément.
        for match in re.finditer(
            (
                rf"(?:{label})"
                rf"\s*[:#Nn°º.\-]?\s*"
                rf"([0-9OoIlSsBbZz]"
                rf"[0-9 .OoIlSsBbZz]{{0,24}})"
            ),
            line["text"],
            re.IGNORECASE
        ):

            value = _digitize_ocr_value(
                match.group(1)
            )

            if len(value) > maximum:
                value = value[:maximum]

            if not (
                minimum
                <= len(value)
                <= maximum
            ):
                continue

            value_item = None

            for item in line.get(
                "items",
                []
            ):
                digits = _digitize_ocr_value(
                    item["text"]
                )

                if value and value in digits:
                    value_item = item
                    break

            if (
                value_item is None
                and line.get("items")
            ):
                # On préfère l'item le plus à droite de la ligne car
                # les valeurs suivent généralement leur libellé.
                value_item = sorted(
                    line["items"],
                    key=lambda item:
                        item["x"],
                    reverse=True
                )[0]

            if value_item is None:
                continue

            result.append(
                {
                    "value": value,
                    "item": value_item,
                    "source": "line"
                }
            )

    return result

def _merge_identifier_candidates(
    primary,
    secondary
):

    merged = []

    seen = set()

    for candidate in (
        list(primary)
        + list(secondary)
    ):

        key = (
            candidate["value"],
            candidate["item"]["page"],
            round(
                candidate["item"]["x"],
                2
            ),
            round(
                candidate["item"]["y"],
                2
            )
        )

        if key in seen:
            continue

        seen.add(key)

        merged.append(
            candidate
        )

    return merged


def extract_ids(
    items,
    lines
):

    result = {
        "supplier_ice": MISSING,
        "client_ice": MISSING,
        "if_number": MISSING,
        "rc": MISSING,
        "cnss": MISSING
    }

    client_anchor = _client_anchor(
        items
    )

    ice_candidates = (
        _merge_identifier_candidates(
            identifier_candidates(
                items,
                "ice"
            ),
            _identifier_candidates_from_lines(
                items,
                lines,
                "ice"
            )
        )
    )

    if ice_candidates:

        client_rank = sorted(
            ice_candidates,
            key=lambda candidate:
                _id_score(
                    candidate,
                    items,
                    "client",
                    client_anchor
                ),
            reverse=True
        )

        supplier_rank = sorted(
            ice_candidates,
            key=lambda candidate:
                _id_score(
                    candidate,
                    items,
                    "supplier",
                    client_anchor
                ),
            reverse=True
        )

        unique_ices = list(
            dict.fromkeys(
                candidate["value"]
                for candidate
                in ice_candidates
            )
        )

        best_client = client_rank[0]
        best_client_score = _id_score(
            best_client,
            items,
            "client",
            client_anchor
        )

        if best_client_score >= 80:
            result["client_ice"] = (
                best_client["value"]
            )

        # Dès que deux ICE différents sont présents, celui qui n'est
        # pas dans la zone client est un candidat fournisseur fort.
        if (
            len(unique_ices) >= 2
            and result["client_ice"] != MISSING
        ):
            remaining = [
                candidate
                for candidate in supplier_rank
                if candidate["value"]
                != result["client_ice"]
            ]

            if remaining:
                result["supplier_ice"] = (
                    remaining[0]["value"]
                )

        if result["supplier_ice"] == MISSING:
            for candidate in supplier_rank:

                if (
                    candidate["value"]
                    == result["client_ice"]
                    and len(unique_ices) > 1
                ):
                    continue

                supplier_score = _id_score(
                    candidate,
                    items,
                    "supplier",
                    client_anchor
                )

                if supplier_score >= 20:
                    result["supplier_ice"] = (
                        candidate["value"]
                    )
                    break

        # Un seul ICE clairement rattaché au client ne doit jamais
        # être copié artificiellement comme ICE fournisseur.
        if (
            len(unique_ices) == 1
            and result["client_ice"] != MISSING
        ):

            only = ice_candidates[0]

            client_score = _id_score(
                only,
                items,
                "client",
                client_anchor
            )

            supplier_score = _id_score(
                only,
                items,
                "supplier",
                client_anchor
            )

            if client_score > supplier_score + 30:
                result["supplier_ice"] = MISSING

    for kind, key in [
        ("if", "if_number"),
        ("rc", "rc"),
        ("cnss", "cnss")
    ]:

        candidates = _merge_identifier_candidates(
            identifier_candidates(
                items,
                kind
            ),
            _identifier_candidates_from_lines(
                items,
                lines,
                kind
            )
        )

        if not candidates:
            continue

        candidates.sort(
            key=lambda candidate:
                _id_score(
                    candidate,
                    items,
                    "supplier",
                    client_anchor
                ),
            reverse=True
        )

        top_candidate = candidates[0]

        # Une valeur qui ressemble à une date (DDMMYYYY) et qui n'a
        # été retrouvée que par proximité (jamais explicitement
        # étiquetée "IF"/"RC"/"CNSS" sur le document) est presque
        # toujours une date de facture ou de paiement mal captée en
        # l'absence du vrai numéro — mieux vaut "Non détecté" qu'un
        # identifiant clairement faux.
        if (
            top_candidate.get("source") == "neighbor"
            and _looks_like_compact_date_digits(
                top_candidate["value"]
            )
        ):
            continue

        # Les sources "inline" et "line" sont privilégiées par
        # _id_score. Cela empêche une date/quantité proche du libellé
        # d'être choisie devant un identifiant réellement étiqueté.
        result[key] = top_candidate["value"]

    return result

MONEY_RE = re.compile(
    (
        r"(?<!\d)"
        r"("
        r"\d{1,3}(?:[ .]\d{3})*"
        r"(?:[,.]\d{2})"
        r"|"
        r"\d+[,.]\d{2}"
        r")"
        r"(?!\d)"
    )
)


def money_values(
    text: str
):

    # Regex locale volontairement définie ici pour éviter
    # toute dépendance à une constante globale lors du rechargement.
    money_re = re.compile(
        (
            r"(?<!\d)"
            r"("
            r"\d{1,3}(?:[ .]\d{3})*"
            r"(?:[,.]\d{2})"
            r"|"
            r"\d+[,.]\d{2}"
            r")"
            r"(?!\d)"
        )
    )

    text = re.sub(
        (
            r"\d{1,2}"
            r"(?:[,.]\d+)?"
            r"\s*%"
        ),
        "",
        text or ""
    )

    result = []

    for token in money_re.findall(
        text
    ):

        value = parse_amount(
            token
        )

        if value is not None:
            result.append(
                value
            )

    return result


def amount_near_label(
    items,
    lines,
    patterns,
    bonus=0,
    min_y=None,
    prefer_bottom=False
):

    candidates = []

    def allowed_y(
        y_value
    ):
        return (
            min_y is None
            or y_value >= min_y
        )

    for line in lines:

        if not allowed_y(
            line["y"]
        ):
            continue

        if _matches(
            line["n"],
            patterns
        ):

            for value in money_values(
                line["text"]
            ):

                score = (
                    115
                    + bonus
                    + int(
                        line["y"]
                        * (
                            80
                            if prefer_bottom
                            else 30
                        )
                    )
                )

                candidates.append(
                    (
                        score,
                        value
                    )
                )

    for anchor in items:

        if not allowed_y(
            anchor["y"]
        ):
            continue

        if not _matches(
            anchor["n"],
            patterns
        ):
            continue

        for item in items:

            if (
                item["page"]
                != anchor["page"]
            ):
                continue

            values = money_values(
                item["text"]
            )

            if not values:
                continue

            delta_y = (
                item["y"]
                - anchor["y"]
            )

            delta_x = (
                item["x"]
                - anchor["x"]
            )

            score = None

            if item is anchor:

                score = (
                    145
                    + bonus
                )

            elif (
                -0.045
                <= delta_y
                <= 0.045
                and -0.08
                <= delta_x
                <= 0.72
            ):

                score = (
                    155
                    + bonus
                    - int(
                        abs(delta_x)
                        * 80
                    )
                    - int(
                        abs(delta_y)
                        * 1000
                    )
                )

                if delta_x >= 0:
                    score += 15

            elif (
                0 < delta_y <= 0.09
                and abs(
                    delta_x
                ) <= 0.28
            ):

                score = (
                    110
                    + bonus
                    - int(
                        delta_y
                        * 250
                    )
                )

            if score is None:
                continue

            score += int(
                item["y"]
                * (
                    80
                    if prefer_bottom
                    else 20
                )
            )

            for value in values:
                candidates.append(
                    (
                        score,
                        value
                    )
                )

    candidates.sort(
        reverse=True,
        key=lambda value:
            value[0]
    )

    if candidates:
        return candidates[0][1]

    return None


def column_total(
    items,
    header_patterns
):

    best_value = None
    best_y = -1

    for header in items:

        if (
            header["y"] < 0.50
            or not _matches(
                header["n"],
                header_patterns
            )
        ):
            continue

        for item in items:

            if (
                item["page"]
                != header["page"]
                or item["y"]
                <= header["y"]
            ):
                continue

            if (
                item["y"]
                - header["y"]
                > 0.22
                or abs(
                    item["x"]
                    - header["x"]
                ) > 0.08
            ):
                continue

            values = money_values(
                item["text"]
            )

            if (
                values
                and item["y"]
                > best_y
            ):

                best_y = item["y"]

                best_value = (
                    values[-1]
                )

    return best_value


def vat_percentage(
    items,
    lines
):

    rates = []

    def add_rates(
        text
    ):

        for token in re.findall(
            (
                r"(\d{1,2}"
                r"(?:[,.]\d+)?)"
                r"\s*%"
            ),
            text or ""
        ):

            try:
                rate = Decimal(
                    token.replace(
                        ",",
                        "."
                    )
                )

                if (
                    0
                    <= rate
                    < 100
                ):

                    value = format(
                        rate,
                        "f"
                    )

                    if "." in value:
                        value = (
                            value
                            .rstrip("0")
                            .rstrip(".")
                        )

                    if value not in rates:
                        rates.append(
                            value
                        )

            except InvalidOperation:
                pass

    # même ligne TVA
    for line in lines:

        if (
            "TVA" in line["n"]
            or "TAXE" in line["n"]
        ):
            add_rates(
                line["text"]
            )

    # colonne TVA
    headers = [
        item
        for item in items
        if (
            re.fullmatch(
                r"T\.?\s*V\.?\s*A\.?",
                item["n"]
            )
            or "TVA"
            in item["n"]
        )
    ]

    for header in headers:

        for item in items:

            if (
                item["page"]
                == header["page"]
                and -0.03
                <= (
                    item["y"]
                    - header["y"]
                )
                <= 0.22
                and abs(
                    item["x"]
                    - header["x"]
                ) <= 0.22
            ):
                add_rates(
                    item["text"]
                )

    if not rates:
        return MISSING

    non_zero = [
        rate
        for rate in rates
        if rate != "0"
    ]

    zero = [
        rate
        for rate in rates
        if rate == "0"
    ]

    return " / ".join(
        non_zero + zero
    )



# =========================================================
# DETECTION GENERIQUE DES LIBELLES DE TOTAUX
# =========================================================

def _label_text(value: str) -> str:
    """
    Normalise un libellé OCR avant comparaison.
    On retire les montants et la ponctuation afin de
    comparer le sens du libellé plutôt que sa mise en forme.
    """
    value = norm(value or "")
    value = re.sub(
        r"\d{1,3}(?:[ .]\d{3})*(?:[,.]\d{2})",
        " ",
        value,
    )
    value = re.sub(
        r"\d{1,2}(?:[,.]\d+)?\s*%",
        " ",
        value,
    )
    value = re.sub(r"[^A-Z0-9 ]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _similarity_to_aliases(value: str, aliases: list[str]) -> float:
    """
    Similarité tolérante aux erreurs OCR.
    Exemple : TOTAL TTO reste proche de TOTAL TTC.
    """
    candidate = _label_text(value)

    if not candidate:
        return 0.0

    best = 0.0

    for alias in aliases:
        target = _label_text(alias)

        if not target:
            continue

        if target in candidate or candidate in target:
            # Une inclusion exacte est très fiable.
            ratio = min(
                1.0,
                0.90 + (
                    min(len(candidate), len(target))
                    / max(len(candidate), len(target))
                ) * 0.10,
            )
        else:
            ratio = SequenceMatcher(
                None,
                candidate,
                target,
            ).ratio()

            # Compare aussi des fenêtres de mots afin qu'un
            # libellé OCR contenant du bruit reste exploitable.
            candidate_words = candidate.split()
            target_words = target.split()
            window_size = max(len(target_words), 1)

            if len(candidate_words) >= window_size:
                for start in range(
                    0,
                    len(candidate_words) - window_size + 1,
                ):
                    window = " ".join(
                        candidate_words[start:start + window_size]
                    )
                    ratio = max(
                        ratio,
                        SequenceMatcher(
                            None,
                            window,
                            target,
                        ).ratio(),
                    )

        best = max(best, ratio)

    return best


def _fuzzy_total_label_score(text: str, role: str) -> float:
    """
    Donne un score de ressemblance pour HT / TVA / TTC.
    Cette fonction ne dépend pas d'un modèle de facture précis.
    """
    normalized = _label_text(text)

    aliases = {
        "ttc": [
            "TOTAL TTC",
            "MONTANT TTC",
            "MONTANT TOTAL TTC",
            "NET A PAYER",
            "TOTAL A PAYER",
            "TOTAL GENERAL",
            "MONTANT TOTAL",
            "TOTAL FACTURE",
            "TOTAL A REGLER",
        ],
        "tva": [
            "TVA",
            "DONT TVA",
            "TOTAL TVA",
            "MONTANT TVA",
            "TAXE SUR LA VALEUR AJOUTEE",
        ],
        "ht": [
            "TOTAL HT",
            "MONTANT HT",
            "TOTAL HORS TAXE",
            "TOTAL HORS TAXES",
            "MONTANT HORS TAXE",
            "SOUS TOTAL HT",
        ],
    }

    score = _similarity_to_aliases(
        normalized,
        aliases[role],
    )

    # Evite qu'un libellé explicitement TVA soit pris pour TTC,
    # ou qu'un libellé explicitement HT soit pris pour TTC.
    if role == "ttc":
        if re.search(r"\bTVA\b", normalized):
            score -= 0.50
        if re.search(r"\bHT\b|HORS\s+TAX", normalized):
            score -= 0.50

        # Libellé générique rencontré sur beaucoup de factures.
        # Il n'est accepté que dans la zone des totaux et sera
        # renforcé plus bas par la présence d'un libellé TVA.
        if normalized == "MONTANT TOTAL":
            score = max(score, 0.86)

    elif role == "tva":
        # Pour TVA, on exige un signal lexical réel TVA/T V A/TAXE.
        # Cela évite qu'un simple TOTAL soit confondu avec la TVA.
        if re.search(
            r"\bTVA\b|\bT\s+V\s+A\b|TAXE\s+SUR\s+LA\s+VALEUR",
            normalized,
        ):
            score = max(score, 0.96)
        else:
            score = 0.0

    elif role == "ht":
        # HT est un libellé court : une similarité floue seule peut
        # confondre TOTAL TTC/TTO avec TOTAL HT. On exige donc un
        # véritable marqueur HT/H T/HORS TAXE.
        if re.search(
            r"\bHT\b|\bH\s+T\b|HORS\s+TAX",
            normalized,
        ):
            score = max(score, 0.95)
        else:
            score = 0.0

    return max(0.0, min(score, 1.0))


def fuzzy_summary_amount(
    lines,
    role: str,
    min_y: float = 0.45,
):
    """
    Fallback générique pour les factures dont le libellé est
    déformé par l'OCR ou séparé de son montant.

    Il analyse seulement la zone basse de la facture et cherche
    le montant autour d'un libellé probable, avant OU après lui.
    """
    candidates = []

    for index, line in enumerate(lines):
        y_value = float(line.get("y", 0) or 0)

        if y_value < min_y:
            continue

        label_score = _fuzzy_total_label_score(
            line.get("text", ""),
            role,
        )

        if label_score < 0.72:
            continue

        normalized = _label_text(
            line.get("text", "")
        )

        nearby_values = []

        # Même ligne + 3 lignes avant/après.
        for offset in range(-3, 4):
            neighbor_index = index + offset

            if not (0 <= neighbor_index < len(lines)):
                continue

            neighbor = lines[neighbor_index]

            if neighbor.get("page") != line.get("page"):
                continue

            values = money_values(
                neighbor.get("text", "")
            )

            for value in values:
                distance = abs(offset)
                proximity = {
                    0: 80,
                    1: 58,
                    2: 36,
                    3: 18,
                }[distance]

                # Un montant situé sur la même ligne ou juste à
                # côté du libellé est privilégié.
                score = (
                    label_score * 140
                    + proximity
                    + y_value * 45
                )

                nearby_values.append(
                    {
                        "value": value,
                        "score": score,
                        "distance": distance,
                    }
                )

        if not nearby_values:
            continue

        local_values = [
            entry["value"]
            for entry in nearby_values
        ]

        # Le TTC est généralement le montant principal du bloc
        # final. Le montant TVA est généralement inférieur au TTC.
        # Ceci n'est qu'un critère de score, jamais une invention.
        for entry in nearby_values:
            score = entry["score"]
            value = entry["value"]

            if role == "ttc":
                if value == max(local_values):
                    score += 28

                # "MONTANT TOTAL" sans TTC est accepté seulement
                # si un libellé de TVA existe à proximité, ce qui
                # indique un récapitulatif fiscal final.
                if normalized == "MONTANT TOTAL":
                    has_nearby_vat = any(
                        _fuzzy_total_label_score(
                            lines[j].get("text", ""),
                            "tva",
                        ) >= 0.80
                        for j in range(
                            max(0, index - 4),
                            min(len(lines), index + 5),
                        )
                        if lines[j].get("page") == line.get("page")
                    )

                    if has_nearby_vat:
                        score += 45
                    else:
                        score -= 35

            elif role == "tva":
                if len(local_values) > 1:
                    smaller_values = [
                        candidate
                        for candidate in local_values
                        if candidate >= Decimal("0")
                    ]
                    if smaller_values and value == min(smaller_values):
                        score += 18

            candidates.append(
                (
                    score,
                    value,
                )
            )

    candidates.sort(
        reverse=True,
        key=lambda item: item[0],
    )

    if candidates:
        return candidates[0][1]

    return None


def extract_totals(
    items,
    lines
):

    TTC_PATTERN = (
        r"T\s*\.?\s*T\s*\.?\s*C\s*\.?"
    )

    HT_PATTERN = (
        r"H\s*\.?\s*T\s*\.?"
    )

    TVA_PATTERN = (
        r"T\s*\.?\s*V\s*\.?\s*A\s*\.?"
    )

    ttc = amount_near_label(
        items,
        lines,
        [
            r"NET\s+A\s+PAYER",
            r"TOTAL\s+A\s+PAYER",
            (
                r"MONTANT\s+TOTAL\s+"
                + TTC_PATTERN
            ),
            (
                r"TOTAL\s+GENERAL\s*"
                + TTC_PATTERN
            ),
            (
                r"TOTAL\s+"
                + TTC_PATTERN
                + r"\s+A\s+PAYER"
            ),
        ],
        bonus=80,
        min_y=0.45,
        prefer_bottom=True
    )

    if ttc is None:

        ttc = amount_near_label(
            items,
            lines,
            [
                (
                    r"TOTAL\s+"
                    + TTC_PATTERN
                ),
                (
                    r"MONTANT\s+"
                    + TTC_PATTERN
                ),
                r"TOTAL\s+GENERAL"
            ],
            bonus=40,
            min_y=0.45,
            prefer_bottom=True
        )

    tva = amount_near_label(
        items,
        lines,
        [
            (
                r"DONT\s+"
                + TVA_PATTERN
            ),
            (
                r"TOTAL\s+"
                + TVA_PATTERN
            ),
            (
                r"MONTANT\s+"
                + TVA_PATTERN
            ),
            (
                TVA_PATTERN
                + r"\s*"
                r"\(?\s*"
                r"\d{1,2}"
                r"(?:[,.]\d+)?"
                r"\s*%"
            )
        ],
        bonus=50,
        min_y=0.35,
        prefer_bottom=True
    )

    ht = amount_near_label(
        items,
        lines,
        [
            (
                r"TOTAL\s+"
                + HT_PATTERN
            ),
            (
                r"MONTANT\s+"
                + HT_PATTERN
            ),
            r"TOTAL\s+HORS\s+TAX",
            r"TOTAL\s+HORS\s+TAXES",
            r"MONTANT\s+HORS\s+TAX"
        ],
        bonus=50,
        min_y=0.30,
        prefer_bottom=True
    )

    if ht is None:

        ht = column_total(
            items,
            [
                r"^H\.?\s*T\.?$",
                r"^H\.?\s*T\.?\s+DH$"
            ]
        )

    if tva is None:

        tva = column_total(
            items,
            [
                r"^T\.?\s*V\.?\s*A\.?$",
                (
                    r"^T\.?\s*V\.?"
                    r"\s*A\.?\s+DH$"
                )
            ]
        )

    # =====================================================
    # FALLBACK GENERIQUE TOLERANT AUX ERREURS OCR
    # =====================================================
    # Exemples d'erreurs courantes gérées sans dépendre d'un
    # modèle précis : TOTAL TTO -> TOTAL TTC, libellé et montant
    # séparés, montant placé avant le libellé, etc.

    if ttc is None:
        ttc = fuzzy_summary_amount(
            lines,
            role="ttc",
            min_y=0.45,
        )

    if tva is None:
        tva = fuzzy_summary_amount(
            lines,
            role="tva",
            min_y=0.35,
        )

    if ht is None:
        ht = fuzzy_summary_amount(
            lines,
            role="ht",
            min_y=0.30,
        )

    calculated_fields = []

    calculation_details = []

    warnings = []

    if (
        ht is None
        and tva is not None
        and ttc is not None
        and ttc >= tva
    ):

        ht = ttc - tva

        calculated_fields.append(
            "total_ht"
        )

        calculation_details.append(
            "Total HT calculé : TTC - TVA"
        )

    elif (
        tva is None
        and ht is not None
        and ttc is not None
        and ttc >= ht
    ):

        tva = ttc - ht

        calculated_fields.append(
            "tva"
        )

        calculation_details.append(
            "Montant TVA calculé : TTC - HT"
        )

    elif (
        ttc is None
        and ht is not None
        and tva is not None
    ):

        ttc = ht + tva

        calculated_fields.append(
            "total_ttc"
        )

        calculation_details.append(
            "Total TTC calculé : HT + TVA"
        )

    if (
        ht is not None
        and tva is not None
        and ttc is not None
    ):

        difference = abs(
            (
                ht
                + tva
            )
            - ttc
        )

        if (
            difference
            > Decimal("0.05")
            and not calculated_fields
        ):

            warnings.append(
                (
                    "Les montants HT, TVA et TTC "
                    "lus sur la facture sont "
                    "mathématiquement incohérents. "
                    "Les valeurs originales ont "
                    "été conservées."
                )
            )

    return {
        "total_ht": fmt(ht),

        "tva": fmt(tva),

        "total_ttc": fmt(
            ttc
        ),

        "calculated_fields":
            calculated_fields,

        "calculation_details":
            calculation_details,

        "warnings":
            warnings
    }


# =========================================================
# EXTRACTION COMPLETE
# =========================================================

def extract_invoice_fields(
    text: str,
    ocr_items: list[dict] | None = None
):

    items = prepare_items(
        ocr_items
    )

    lines = build_lines(
        items,
        text
    )

    provider, client = (
        extract_entities(
            items,
            lines
        )
    )

    if items:

        identifiers = extract_ids(
            items,
            lines
        )

        totals = extract_totals(
            items,
            lines
        )

    else:

        identifiers = {
            "supplier_ice": MISSING,
            "client_ice": MISSING,
            "if_number": MISSING,
            "rc": MISSING,
            "cnss": MISSING
        }

        totals = {
            "total_ht": MISSING,
            "tva": MISSING,
            "total_ttc": MISSING,
            "calculated_fields": [],
            "calculation_details": [],
            "warnings": []
        }

    return {
        "provider": provider,

        "client": client,

        "date": extract_date(
            lines
        ),

        "invoice_number":
            (
                detect_invoice_reference(
                    text
                )
                or MISSING
            ),

        # ICE fournisseur
        "supplier_ice":
            identifiers[
                "supplier_ice"
            ],

        # ICE client
        "client_ice":
            identifiers[
                "client_ice"
            ],

        # Compatibilité avec
        # ton application actuelle :
        # ice = fournisseur.
        "ice":
            identifiers[
                "supplier_ice"
            ],

        "rc":
            identifiers["rc"],

        "if_number":
            identifiers[
                "if_number"
            ],

        "cnss":
            identifiers[
                "cnss"
            ],

        "tva_percentage":
            vat_percentage(
                items,
                lines
            ),

        "tva":
            totals["tva"],

        "total_ht":
            totals[
                "total_ht"
            ],

        "total_ttc":
            totals[
                "total_ttc"
            ],

        "calculated_fields":
            totals[
                "calculated_fields"
            ],

        "calculation_details":
            totals[
                "calculation_details"
            ],

        "warnings":
            totals.get(
                "warnings",
                []
            )
    }


# =========================================================
# PDF MULTI-FACTURES
# =========================================================

def detect_page_sequence(
    text: str
):

    tail = "\n".join(
        (
            text
            or ""
        ).splitlines()[-15:]
    )

    match = re.search(
        (
            r"\b(?:PAGE\s*:?)?\s*"
            r"(\d{1,3})"
            r"\s*(?:/|SUR|OF)\s*"
            r"(\d{1,3})\b"
        ),
        norm(tail)
    )

    if not match:
        return None

    current = int(
        match.group(1)
    )

    total = int(
        match.group(2)
    )

    if (
        1
        <= current
        <= total
    ):
        return (
            current,
            total
        )

    return None


def looks_like_invoice_start(
    text: str
):

    normalized = norm(text)

    signals = 0

    if re.search(
        r"\bFACTURE\b|\bINVOICE\b",
        normalized
    ):
        signals += 1

    if re.search(
        (
            r"\bCLIENT\b|"
            r"DESTINATAIRE|"
            r"NOM DU CLIENT|"
            r"ADRESSE DE FACTURATION"
        ),
        normalized
    ):
        signals += 1

    if re.search(
        (
            r"FOURNISSEUR|"
            r"EMETTEUR|"
            r"EMIS PAR|"
            r"VENDEUR"
        ),
        normalized
    ):
        signals += 1

    if re.search(
        r"\bDATE\b",
        normalized
    ):
        signals += 1

    return signals >= 2


def has_final_total(
    text: str
):

    return bool(
        re.search(
            (
                r"TOTAL\s+T\.?\s*T\.?\s*C\.?"
                r"|MONTANT\s+TOTAL\s+TTC"
                r"|NET\s+A\s+PAYER"
            ),
            norm(text)
        )
    )


def group_pdf_pages(
    page_records: list[dict]
):

    groups = []

    for page in page_records:

        text = (
            page.get(
                "text"
            )
            or ""
        ).strip()

        if not text:
            continue

        reference = (
            detect_invoice_reference(
                text
            )
        )

        sequence = (
            detect_page_sequence(
                text
            )
        )

        page_items = []

        for raw_item in (
            page.get(
                "items"
            )
            or []
        ):

            item = dict(
                raw_item
            )

            item["page"] = int(
                page.get(
                    "page_number"
                )
                or 1
            )

            page_items.append(
                item
            )

        if not groups:

            groups.append(
                {
                    "reference":
                        reference,

                    "pages": [
                        page[
                            "page_number"
                        ]
                    ],

                    "texts": [
                        text
                    ],

                    "items":
                        page_items
                }
            )

            continue

        current = groups[-1]

        current_reference = (
            current.get(
                "reference"
            )
        )

        same_reference = bool(
            reference
            and current_reference
            and norm(
                reference
            ) == norm(
                current_reference
            )
        )

        different_reference = bool(
            reference
            and current_reference
            and norm(
                reference
            ) != norm(
                current_reference
            )
        )

        continuation = bool(
            sequence
            and sequence[0] > 1
        )

        new_invoice = (
            different_reference
            or (
                not continuation
                and not same_reference
                and looks_like_invoice_start(
                    text
                )
                and has_final_total(
                    current["texts"][-1]
                )
            )
        )

        if new_invoice:

            groups.append(
                {
                    "reference":
                        reference,

                    "pages": [
                        page[
                            "page_number"
                        ]
                    ],

                    "texts": [
                        text
                    ],

                    "items":
                        page_items
                }
            )

        else:

            current[
                "pages"
            ].append(
                page[
                    "page_number"
                ]
            )

            current[
                "texts"
            ].append(
                text
            )

            current[
                "items"
            ].extend(
                page_items
            )

            if (
                not current_reference
                and reference
            ):
                current[
                    "reference"
                ] = reference

    for group in groups:

        texts = group.pop(
            "texts"
        )

        group["text"] = "\n".join(
            (
                f"--- PAGE {page_number} ---\n"
                f"{page_text}"
            )
            for (
                page_number,
                page_text
            )
            in zip(
                group["pages"],
                texts
            )
        )

    return groups
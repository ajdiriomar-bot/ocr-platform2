from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from PIL import Image
import io
import re
import traceback
from .database import get_db
from . import models, schemas, auth,  notifications
from .services.ice_verification import verify_ice
from pathlib import Path
from .services.invoice_parser import (
    extract_invoice_fields,
    group_pdf_pages,
)


router = APIRouter(
    prefix="/ocr",
    tags=["OCR Extraction"]
)

_ocr_instance = None


def get_ocr_engine():
    global _ocr_instance

    if _ocr_instance is None:
        try:
            from paddleocr import PaddleOCR

            _ocr_instance = PaddleOCR(
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
                text_detection_model_name="PP-OCRv5_mobile_det",
                text_recognition_model_name="latin_PP-OCRv5_mobile_rec",
                enable_mkldnn=False
            )

        except ImportError:
            _ocr_instance = False

    return _ocr_instance if _ocr_instance else None


def pdf_to_images(pdf_bytes: bytes):
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(
        pdf_bytes
    )

    images = []

    try:
        for page_index in range(
            len(pdf)
        ):
            page = pdf[
                page_index
            ]

            try:
                # Anciennement : scale=1.5
                #
                # 2.5 donne une image beaucoup
                # plus nette pour les factures
                # scannées.
                bitmap = page.render(
                    scale=2.5
                )

                pil_image = (
                    bitmap
                    .to_pil()
                    .convert("RGB")
                )

                images.append(
                    pil_image
                )

            finally:
                page.close()

    finally:
        pdf.close()

    print(
        "Nombre de pages PDF converties :",
        len(images)
    )

    return images


def run_ocr_on_image(
    ocr_engine,
    image_pil
):
    import numpy as np
    import cv2

    image_np = np.array(
        image_pil.convert(
            "RGB"
        )
    )

    image_cv = cv2.cvtColor(
        image_np,
        cv2.COLOR_RGB2BGR
    )

    height, width = (
        image_cv.shape[:2]
    )

    # Agrandissement des petits scans
    if width < 1800:

        scale = (
            1800 / width
        )

        image_cv = cv2.resize(
            image_cv,
            None,
            fx=scale,
            fy=scale,
            interpolation=cv2.INTER_CUBIC
        )

    # Gris + nettoyage
    gray = cv2.cvtColor(
        image_cv,
        cv2.COLOR_BGR2GRAY
    )

    gray = cv2.fastNlMeansDenoising(
        gray,
        None,
        8,
        7,
        21
    )

    clahe = cv2.createCLAHE(
        clipLimit=2.0,
        tileGridSize=(8, 8)
    )

    gray = clahe.apply(
        gray
    )

    prepared = cv2.cvtColor(
        gray,
        cv2.COLOR_GRAY2BGR
    )

    full_height, full_width = (
        prepared.shape[:2]
    )

    # =====================================================
    # CONVERSION RESULTAT PADDLE
    # =====================================================

    def result_to_dict(
        result
    ):

        if isinstance(
            result,
            dict
        ):
            data = result

        else:
            try:
                data = result.json

                if callable(data):
                    data = data()

            except Exception:
                data = {}

        if (
            isinstance(
                data,
                dict
            )
            and isinstance(
                data.get("res"),
                dict
            )
        ):
            data = data[
                "res"
            ]

        if not isinstance(
            data,
            dict
        ):
            return {}

        return data

    # =====================================================
    # OCR D'UNE ZONE
    # =====================================================

    def predict_region(
        region,
        offset_x=0,
        offset_y=0,
        zoom=1.0
    ):
        source = region

        # =============================================
        # ZOOM DE LA ZONE
        # =============================================

        if zoom != 1.0:
            source = cv2.resize(
                region,
                None,
                fx=zoom,
                fy=zoom,
                interpolation=cv2.INTER_CUBIC
            )

        # =============================================
        # PADDLEOCR
        # =============================================

        prediction = (
            ocr_engine.predict(
                source
            )
        )

        collected = []

        if prediction is None:
            return collected

        # =============================================
        # PARCOURIR LES RÉSULTATS
        # =============================================

        for result in prediction:
            data = result_to_dict(
                result
            )

            if not data:
                continue

            # =========================================
            # RÉCUPÉRER LES DONNÉES BRUTES
            # =========================================

            texts_raw = data.get(
                "rec_texts"
            )

            scores_raw = data.get(
                "rec_scores"
            )

            boxes_raw = data.get(
                "rec_boxes"
            )

            # =========================================
            # CONVERSION TEXTES
            # =========================================

            if texts_raw is None:
                texts = []
            elif hasattr(
                texts_raw,
                "tolist"
            ):
                texts = texts_raw.tolist()
            else:
                texts = list(
                    texts_raw
                )

            # =========================================
            # CONVERSION SCORES
            # =========================================

            if scores_raw is None:
                scores = []
            elif hasattr(
                scores_raw,
                "tolist"
            ):
                scores = scores_raw.tolist()
            else:
                scores = list(
                    scores_raw
                )

            # =========================================
            # CONVERSION BOXES
            # =========================================

            if boxes_raw is None:
                boxes = []
            elif hasattr(
                boxes_raw,
                "tolist"
            ):
                boxes = boxes_raw.tolist()
            else:
                boxes = list(
                    boxes_raw
                )

            # PaddleOCR peut parfois renvoyer
            # un texte unique au lieu d'une liste.
            if isinstance(
                texts,
                str
            ):
                texts = [texts]

            # =========================================
            # CHAQUE TEXTE OCR
            # =========================================

            for index, text_value in enumerate(
                texts
            ):
                text_value = str(
                    text_value
                ).strip()

                if not text_value:
                    continue

                # =====================================
                # SCORE
                # =====================================

                if index < len(
                    scores
                ):
                    try:
                        score = float(
                            scores[index]
                        )
                    except (
                        TypeError,
                        ValueError
                    ):
                        score = 0.0
                else:
                    score = 0.0

                # =====================================
                # POSITION
                # =====================================

                if (
                    index < len(
                        boxes
                    )
                    and boxes[index] is not None
                    and len(
                        boxes[index]
                    ) >= 4
                ):
                    (
                        x1,
                        y1,
                        x2,
                        y2
                    ) = [
                        float(value)
                        for value
                        in boxes[index][:4]
                    ]

                    # Les coordonnées ont été
                    # multipliées par le zoom.
                    # On les remet dans les coordonnées
                    # de la page complète.

                    x1 = (
                        x1 / zoom
                        + offset_x
                    )

                    x2 = (
                        x2 / zoom
                        + offset_x
                    )

                    y1 = (
                        y1 / zoom
                        + offset_y
                    )

                    y2 = (
                        y2 / zoom
                        + offset_y
                    )

                else:
                    x1 = 0.0
                    y1 = 0.0
                    x2 = 0.0
                    y2 = 0.0

                # =====================================
                # AJOUT DU RÉSULTAT
                # =====================================

                collected.append(
                    {
                        "text":
                            text_value,

                        "score":
                            score,

                        "box": [
                            x1,
                            y1,
                            x2,
                            y2
                        ],

                        "page_width":
                            full_width,

                        "page_height":
                            full_height
                    }
                )

        return collected

    # =====================================================
    # PREMIER PASSAGE : PAGE COMPLETE
    # =====================================================

    items = predict_region(
        prepared
    )

    full_text_upper = " ".join(
        item["text"].upper()
        for item in items
    )

    # =====================================================
    # SECOND PASSAGE : PIED DE PAGE
    #
    # Très utile pour :
    # IF / RC / CNSS / ICE fournisseur
    # =====================================================

    if not all(
        token in full_text_upper
        for token in (
            "IF",
            "RC",
            "CNSS"
        )
    ):

        footer_y = int(
            full_height * 0.70
        )

        footer = prepared[
            footer_y:
            full_height,
            0:
            full_width
        ]

        items.extend(
            predict_region(
                footer,
                offset_x=0,
                offset_y=footer_y,
                zoom=1.7
            )
        )

    # =====================================================
    # SECOND PASSAGE ENTETE SI NECESSAIRE
    # =====================================================

    full_text_upper = " ".join(
        item["text"].upper()
        for item in items
    )

    header_signals = sum(
        1
        for token in (
            "FACTURE",
            "CLIENT",
            "DESTINATAIRE",
            "DATE"
        )
        if token
        in full_text_upper
    )

    if header_signals < 2:

        header_height = int(
            full_height * 0.48
        )

        header = prepared[
            0:
            header_height,
            0:
            full_width
        ]

        items.extend(
            predict_region(
                header,
                offset_x=0,
                offset_y=0,
                zoom=1.45
            )
        )

    # =====================================================
    # SUPPRIMER LES DOUBLONS
    # =====================================================

    deduplicated = []

    seen = set()

    for item in items:

        (
            x1,
            y1,
            x2,
            y2
        ) = item["box"]

        key = (
            item[
                "text"
            ].strip().upper(),

            round(
                (
                    (x1 + x2) / 2
                )
                / max(
                    full_width,
                    1
                ),
                2
            ),

            round(
                (
                    (y1 + y2) / 2
                )
                / max(
                    full_height,
                    1
                ),
                2
            )
        )

        if key in seen:
            continue

        seen.add(key)

        deduplicated.append(
            item
        )

    # ordre visuel
    deduplicated.sort(
        key=lambda item: (
            (
                item["box"][1]
                + item["box"][3]
            ) / 2,
            item["box"][0]
        )
    )

    text = "\n".join(
        item["text"]
        for item in deduplicated
    )

    print(
        "Nombre de zones OCR détectées :",
        len(
            deduplicated
        )
    )

    return {
        "text": text,
        "items": deduplicated,
        "width": full_width,
        "height": full_height
    }

def extract_structured_fields(text: str):
    MISSING = "Non détecté"

    data = {
        "provider": MISSING,
        "client": MISSING,
        "date": "Non détectée",
        "ice": MISSING,
        "if_number": MISSING,
        "rc": MISSING,
        "total_ht": MISSING,
        "tva": MISSING,
        "total_ttc": MISSING,

        # Permet de savoir ce qui vient réellement
        # de la facture et ce qui a été calculé.
        "calculated_fields": [],
        "calculation_details": [],
        "warnings": []
    }

    normalized_text = (
        text
        .replace("\r\n", "\n")
        .replace("\r", "\n")
    )

    normalized_text = re.sub(
        r"[ \t]+",
        " ",
        normalized_text
    )

    lines = [
        re.sub(r"\s+", " ", line).strip()
        for line in normalized_text.split("\n")
        if line.strip()
        and not re.fullmatch(
            r"---\s*PAGE\s+\d+\s*---",
            line.strip(),
            re.IGNORECASE
        )
    ]

    # =========================================================
    # OUTILS
    # =========================================================

    def contains_letters(value):
        return bool(
            re.search(
                r"[A-Za-zÀ-ÿ]",
                value or ""
            )
        )

    def is_numeric_only(value):
        return bool(
            re.fullmatch(
                r"[\d\s.,/:%+\-]+",
                (value or "").strip()
            )
        )

    def clean_entity(value):
        value = re.sub(
            r"\s+",
            " ",
            value or ""
        ).strip(" :-|,")

        # Exemple :
        # 011298 EJ SOLUTIONS
        # devient :
        # EJ SOLUTIONS
        value = re.sub(
            r"^\d{3,}\s+(?=[A-Za-zÀ-ÿ])",
            "",
            value
        )

        return value.strip(" :-|,")

    def valid_entity(value):
        value = clean_entity(value)

        if len(value) < 3:
            return False

        if not contains_letters(value):
            return False

        if is_numeric_only(value):
            return False

        if re.search(
            r"\b(?:"
            r"facture|invoice|date|ice|if|rc|"
            r"cnss|total|tva|ttc|ht|"
            r"adresse|t[ée]l|telephone|"
            r"email|e-mail|www\.|page"
            r")\b",
            value,
            re.IGNORECASE
        ):
            return False

        return True

    structural_label = re.compile(
        r"^\s*(?:"
        r"client|destinataire|acheteur|"
        r"fournisseur|vendeur|émetteur|emetteur|"
        r"date|facture|invoice|ice|if|rc|cnss|"
        r"total|montant|tva|net\s+[àa]\s+payer|"
        r"désignation|designation|article|"
        r"quantité|quantite|qt[ée]|qte|"
        r"pu|prix|référence|reference"
        r")\b",
        re.IGNORECASE
    )

    def find_labeled_text(
        label_patterns,
        lookahead=4
    ):
        for index, line in enumerate(lines):

            for label_pattern in label_patterns:

                match = re.match(
                    rf"^\s*(?:{label_pattern})"
                    rf"\s*(?:[:\-]|\s)\s*(.*)$",
                    line,
                    re.IGNORECASE
                )

                if not match:
                    continue

                inline = clean_entity(
                    match.group(1)
                )

                if valid_entity(inline):
                    return inline

                for offset in range(
                    1,
                    lookahead + 1
                ):
                    next_index = index + offset

                    if next_index >= len(lines):
                        break

                    candidate = lines[
                        next_index
                    ].strip()

                    if structural_label.search(
                        candidate
                    ):
                        break

                    candidate = clean_entity(
                        candidate
                    )

                    if valid_entity(candidate):
                        return candidate

        return None

    # =========================================================
    # FOURNISSEUR
    # =========================================================

    provider = find_labeled_text([
        r"fournisseur",
        r"vendeur",
        r"émetteur",
        r"emetteur",
        r"raison\s+sociale"
    ])

    # Si aucun libellé Fournisseur/Vendeur n'existe,
    # on recherche uniquement une société dans l'en-tête.
    # On ne prend plus une ligne arbitraire.
    if not provider:

        header_lines = []

        for line in lines[:15]:

            if re.search(
                r"^\s*(?:"
                r"client|destinataire|acheteur"
                r")\b",
                line,
                re.IGNORECASE
            ):
                break

            header_lines.append(line)

        company_marker = re.compile(
            r"\b(?:"
            r"sarl|s\.a\.r\.l|sa|s\.a|sas|"
            r"sasu|eurl|société|societe|"
            r"company|entreprise|"
            r"solutions|services|industrie|"
            r"distribution|commerce|"
            r"transmission|caoutchouc"
            r")\b",
            re.IGNORECASE
        )

        candidates = []

        for position, line in enumerate(
            header_lines
        ):
            candidate = clean_entity(line)

            if not valid_entity(candidate):
                continue

            if not company_marker.search(
                candidate
            ):
                continue

            candidates.append(
                (
                    position,
                    candidate
                )
            )

        if candidates:

            candidates.sort(
                key=lambda item: item[0]
            )

            provider = candidates[0][1]

    if provider:
        data["provider"] = provider[:150]

    # =========================================================
    # CLIENT
    # =========================================================

    client = find_labeled_text(
        [
            r"client",
            r"destinataire",
            r"acheteur",
            r"facturé\s+[àa]",
            r"facture\s+[àa]"
        ],
        lookahead=6
    )

    if client:
        data["client"] = client[:150]

    # =========================================================
    # DATE DE FACTURE
    # =========================================================

    date_value = None

    date_patterns = [
        (
            r"(?:"
            r"date\s+(?:de\s+la\s+)?facture|"
            r"date\s+facture|"
            r"facture\s+du|"
            r"date\s+d['’]émission|"
            r"date\s+emission|"
            r"émise\s+le|"
            r"emise\s+le|"
            r"date"
            r")"
            r"\s*[:\-]?\s*"
            r"("
            r"\d{1,2}[./\-]\d{1,2}"
            r"[./\-]\d{2,4}"
            r"|"
            r"\d{4}[./\-]\d{1,2}"
            r"[./\-]\d{1,2}"
            r")"
        )
    ]

    for pattern in date_patterns:

        match = re.search(
            pattern,
            normalized_text,
            re.IGNORECASE
        )

        if match:
            date_value = match.group(1)
            break

    # Si plusieurs dates existent et qu'aucune
    # n'est clairement indiquée comme date facture,
    # le système ne devine pas.
    if not date_value:

        all_dates = re.findall(
            r"\b(?:"
            r"\d{1,2}[./\-]\d{1,2}"
            r"[./\-]\d{2,4}"
            r"|"
            r"\d{4}[./\-]\d{1,2}"
            r"[./\-]\d{1,2}"
            r")\b",
            normalized_text
        )

        unique_dates = list(
            dict.fromkeys(all_dates)
        )

        if len(unique_dates) == 1:

            date_value = unique_dates[0]

        elif len(unique_dates) > 1:

            data["warnings"].append(
                (
                    "Plusieurs dates ont été "
                    "détectées. La date de facture "
                    "n'a pas été devinée."
                )
            )

    if date_value:
        data["date"] = date_value

    # =========================================================
    # ICE / IF / RC
    # =========================================================

    def extract_identifier(
        patterns,
        minimum,
        maximum
    ):
        for pattern in patterns:

            match = re.search(
                pattern,
                normalized_text,
                re.IGNORECASE
            )

            if not match:
                continue

            value = re.sub(
                r"\D",
                "",
                match.group(1)
            )

            if minimum <= len(value) <= maximum:
                return value

        return None

    # ICE
    ice = extract_identifier(
        [
            (
                r"\bI\s*\.?\s*C\s*\.?\s*E\s*\.?"
                r"(?:\s*(?:n[°o]|numéro|numero))?"
                r"\s*[:\-]?\s*"
                r"([\d\s.\-]{15,25})"
            ),
            (
                r"identifiant\s+commun\s+de\s+"
                r"l['’]entreprise"
                r"\s*[:\-]?\s*"
                r"([\d\s.\-]{15,25})"
            )
        ],
        15,
        15
    )

    if ice:
        data["ice"] = ice

    # IF
    if_number = extract_identifier(
        [
            (
                r"\bI\s*\.?\s*F\s*\.?"
                r"(?:\s*(?:n[°o]|numéro|numero))?"
                r"\s*[:\-]?\s*"
                r"([\d\s.\-]{5,15})"
            ),
            (
                r"identifiant\s+fiscal"
                r"\s*[:\-]?\s*"
                r"([\d\s.\-]{5,15})"
            )
        ],
        5,
        10
    )

    if if_number:
        data["if_number"] = if_number

    # RC
    rc = extract_identifier(
        [
            (
                r"\bR\s*\.?\s*C\s*\.?\s*"
                r"(?:n[°o]|numéro|numero)?"
                r"\s*[:\-]?\s*"
                r"([\d\s.\-]{1,15})"
            ),
            (
                r"registre\s+(?:du|de)?"
                r"\s*commerce"
                r"\s*[:\-]?\s*"
                r"([\d\s.\-]{1,15})"
            )
        ],
        1,
        10
    )

    if rc:
        data["rc"] = rc

    # =========================================================
    # MONTANTS
    # =========================================================

    decimal_amount_regex = re.compile(
        r"(?<!\d)"
        r"("
        r"\d{1,3}(?:[ .]\d{3})*[,.]\d{2}"
        r"|"
        r"\d+[,.]\d{2}"
        r")"
        r"(?!\d)"
    )

    integer_amount_regex = re.compile(
        r"(?<![\d.,])"
        r"(\d{1,9})"
        r"(?![\d.,\s]*%)"
    )

    def amount_to_decimal(value):

        if value is None:
            return None

        value = (
            str(value)
            .strip()
            .replace(" ", "")
        )

        if not value:
            return None

        try:

            # Exemple européen :
            # 18.624,00
            if "," in value and "." in value:

                if value.rfind(",") > value.rfind("."):

                    value = (
                        value
                        .replace(".", "")
                        .replace(",", ".")
                    )

                else:

                    value = value.replace(",", "")

            elif "," in value:

                value = value.replace(",", ".")

            return Decimal(value)

        except (
            InvalidOperation,
            ValueError,
            TypeError
        ):
            return None

    def format_amount(value):

        return str(
            value.quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP
            )
        )

    def extract_amount_from_line(line):

        decimal_matches = (
            decimal_amount_regex.findall(line)
        )

        if decimal_matches:

            value = amount_to_decimal(
                decimal_matches[-1]
            )

            if value is not None:
                return format_amount(value)

        integer_matches = (
            integer_amount_regex.findall(line)
        )

        if integer_matches:

            value = amount_to_decimal(
                integer_matches[-1]
            )

            if value is not None:
                return format_amount(value)

        return None

    amount_label = re.compile(
        r"^\s*(?:"
        r"total\s+h\.?\s*t\.?|"
        r"montant\s+ht|"
        r"sous[- ]?total\s+ht|"
        r"t\.?\s*v\.?\s*a\.?|"
        r"taxe\s+sur\s+la\s+valeur\s+ajoutée|"
        r"total\s+t\.?\s*t\.?\s*c\.?|"
        r"montant\s+ttc|"
        r"net\s+[àa]\s+payer|"
        r"total\s+général"
        r")\b",
        re.IGNORECASE
    )

    def find_labeled_amount(
        label_patterns,
        search_distance=2
    ):

        for index in range(
            len(lines) - 1,
            -1,
            -1
        ):
            line = lines[index]

            if not any(
                re.search(
                    pattern,
                    line,
                    re.IGNORECASE
                )
                for pattern in label_patterns
            ):
                continue

            value = extract_amount_from_line(
                line
            )

            if value is not None:
                return value

            # Le libellé et le montant peuvent
            # être séparés par l'OCR.
            for offset in range(
                1,
                search_distance + 1
            ):
                next_index = index + offset

                if next_index >= len(lines):
                    break

                next_line = lines[next_index]

                if amount_label.search(
                    next_line
                ):
                    break

                value = extract_amount_from_line(
                    next_line
                )

                if value is not None:
                    return value

        return None

    total_ht = find_labeled_amount([
        r"\btotal\s+h\.?\s*t\.?\b",
        r"\bmontant\s+h\.?\s*t\.?\b",
        r"\bmontant\s+hors\s+taxe[s]?\b",
        r"\bsous[- ]?total\s+h\.?\s*t\.?\b"
    ])

    tva = find_labeled_amount([
        r"\bt\.?\s*v\.?\s*a\.?\b",
        r"\btaxe\s+sur\s+la\s+valeur\s+ajoutée\b"
    ])

    total_ttc = find_labeled_amount([
        r"\btotal\s+t\.?\s*t\.?\s*c\.?\b",
        r"\bmontant\s+t\.?\s*t\.?\s*c\.?\b",
        r"\bnet\s+[àa]\s+payer\b",
        r"\btotal\s+général\b"
    ])

    if total_ht is not None:
        data["total_ht"] = total_ht

    if tva is not None:
        data["tva"] = tva

    if total_ttc is not None:
        data["total_ttc"] = total_ttc

    # =========================================================
    # RECHERCHE DU TAUX TVA
    # =========================================================

    vat_rates = set()

    for line in lines:

        if not re.search(
            (
                r"\bt\.?\s*v\.?\s*a\.?\b"
                r"|"
                r"taxe\s+sur\s+la\s+"
                r"valeur\s+ajoutée"
            ),
            line,
            re.IGNORECASE
        ):
            continue

        for match in re.finditer(
            r"(\d{1,2}(?:[,.]\d+)?)\s*%",
            line
        ):
            try:

                rate = Decimal(
                    match.group(1).replace(
                        ",",
                        "."
                    )
                )

                if (
                    Decimal("0")
                    < rate
                    < Decimal("100")
                ):
                    vat_rates.add(rate)

            except InvalidOperation:
                pass

    # Le taux n'est utilisé que si la facture
    # contient un seul taux de TVA.
    vat_rate = (
        next(iter(vat_rates))
        if len(vat_rates) == 1
        else None
    )

    if len(vat_rates) > 1:

        data["warnings"].append(
            (
                "Plusieurs taux de TVA ont été "
                "détectés. Aucun taux unique "
                "n'a été utilisé pour calculer "
                "les montants."
            )
        )

    # =========================================================
    # CALCUL DES DONNEES MANQUANTES
    # =========================================================

    ht_value = amount_to_decimal(
        total_ht
    )

    tva_value = amount_to_decimal(
        tva
    )

    ttc_value = amount_to_decimal(
        total_ttc
    )

    def set_calculated(
        field,
        value,
        detail
    ):

        formatted = format_amount(value)

        data[field] = formatted

        data["calculated_fields"].append(
            field
        )

        data[
            "calculation_details"
        ].append(detail)

        return value

    # ---------------------------------------------------------
    # 2 valeurs présentes -> calcul de la 3e
    # ---------------------------------------------------------

    if (
        ht_value is None
        and tva_value is not None
        and ttc_value is not None
    ):

        result = ttc_value - tva_value

        if result >= 0:

            ht_value = set_calculated(
                "total_ht",
                result,
                "Total HT calculé : TTC - TVA"
            )

    elif (
        tva_value is None
        and ht_value is not None
        and ttc_value is not None
    ):

        result = ttc_value - ht_value

        if result >= 0:

            tva_value = set_calculated(
                "tva",
                result,
                "TVA calculée : TTC - HT"
            )

    elif (
        ttc_value is None
        and ht_value is not None
        and tva_value is not None
    ):

        ttc_value = set_calculated(
            "total_ttc",
            ht_value + tva_value,
            "Total TTC calculé : HT + TVA"
        )

    # ---------------------------------------------------------
    # Utilisation du taux de TVA UNIQUEMENT
    # s'il est réellement écrit sur la facture.
    # ---------------------------------------------------------

    if vat_rate is not None:

        rate = (
            vat_rate / Decimal("100")
        )

        # HT présent + taux TVA
        if (
            ht_value is not None
            and tva_value is None
        ):

            tva_value = set_calculated(
                "tva",
                ht_value * rate,
                (
                    "TVA calculée avec le taux "
                    f"affiché : {vat_rate} %"
                )
            )

        if (
            ht_value is not None
            and ttc_value is None
            and tva_value is not None
        ):

            ttc_value = set_calculated(
                "total_ttc",
                ht_value + tva_value,
                "Total TTC calculé : HT + TVA"
            )

        # TTC présent + taux TVA
        if (
            ttc_value is not None
            and ht_value is None
        ):

            denominator = (
                Decimal("1") + rate
            )

            ht_value = set_calculated(
                "total_ht",
                ttc_value / denominator,
                (
                    "Total HT calculé avec "
                    f"le taux affiché : "
                    f"{vat_rate} %"
                )
            )

        if (
            ttc_value is not None
            and tva_value is None
            and ht_value is not None
        ):

            tva_value = set_calculated(
                "tva",
                ttc_value - ht_value,
                "TVA calculée : TTC - HT"
            )

    # =========================================================
    # CONTROLE DE COHERENCE
    # =========================================================

    # IMPORTANT :
    # si HT, TVA et TTC sont réellement présents
    # sur la facture, on ne modifie AUCUNE valeur.
    # On signale simplement une incohérence.

    original_ht = amount_to_decimal(
        total_ht
    )

    original_tva = amount_to_decimal(
        tva
    )

    original_ttc = amount_to_decimal(
        total_ttc
    )

    if (
        original_ht is not None
        and original_tva is not None
        and original_ttc is not None
    ):

        difference = abs(
            (
                original_ht
                + original_tva
            )
            - original_ttc
        )

        if difference > Decimal("0.05"):

            data["warnings"].append(
                (
                    "Les montants HT, TVA et TTC "
                    "lus sur la facture sont "
                    "mathématiquement incohérents. "
                    "Les valeurs originales ont "
                    "été conservées."
                )
            )

    return data



def build_invoice_filename(
    original_filename: str | None,
    index: int,
    invoice_count: int,
    reference: str | None,
):
    original = Path(
        original_filename
        or "document.pdf"
    )

    # Si le fichier ne contient
    # qu'une seule facture,
    # on conserve son nom.
    if invoice_count == 1:
        return original.name

    extension = (
        original.suffix
        or ".pdf"
    )

    label = (
        reference
        or f"facture_{index:02d}"
    )

    safe_label = re.sub(
        r"[^A-Za-z0-9._-]+",
        "_",
        label,
    ).strip(
        "_.-"
    )

    if not safe_label:
        safe_label = (
            f"facture_{index:02d}"
        )

    return (
        f"{original.stem}"
        f" - "
        f"{safe_label}"
        f"{extension}"
    )
@router.post("/extract")
async def extract_text(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        auth.get_current_user
    ),
):
    content_type = (
        file.content_type
        or ""
    )

    is_image = (
        content_type.startswith(
            "image/"
        )
    )

    is_pdf = (
        content_type
        == "application/pdf"
    )

    # =====================================================
    # VÉRIFICATION DU TYPE DE FICHIER
    # =====================================================

    if not (
        is_image
        or is_pdf
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "Le fichier fourni doit être "
                "une image ou un PDF."
            ),
        )

    try:
        # =================================================
        # LECTURE DU FICHIER
        # =================================================

        file_data = await file.read()

        if not file_data:
            raise HTTPException(
                status_code=400,
                detail="Le fichier fourni est vide.",
            )

        # =================================================
        # CHARGEMENT DU MOTEUR OCR
        # =================================================

        ocr_engine = get_ocr_engine()

        if ocr_engine is None:
            raise HTTPException(
                status_code=503,
                detail=(
                    "PaddleOCR n'est pas installé "
                    "ou n'a pas pu être chargé."
                ),
            )

        invoice_groups = []

        # =================================================
        # TRAITEMENT PDF
        # =================================================

        if is_pdf:
            pages = pdf_to_images(
                file_data
            )

            if not pages:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Le PDF ne contient aucune "
                        "page exploitable."
                    ),
                )

            page_records = []

            for (
                page_number,
                page_image,
            ) in enumerate(
                pages,
                start=1,
            ):
                try:
                    print(
                        "\n"
                        "================================"
                    )

                    print(
                        f"OCR DE LA PAGE {page_number}"
                    )

                    print(
                        "================================"
                    )

                    # Nouveau run_ocr_on_image()
                    # retourne :
                    #
                    # {
                    #   "text": "...",
                    #   "items": [...],
                    #   "width": ...,
                    #   "height": ...
                    # }

                    page_ocr = run_ocr_on_image(
                        ocr_engine,
                        page_image,
                    )

                    page_text = (
                        page_ocr.get(
                            "text",
                            ""
                        )
                    )

                    page_items = (
                        page_ocr.get(
                            "items",
                            []
                        )
                    )

                    print(
                        (
                            f"Page {page_number} : "
                            f"{len(page_text)} "
                            "caractères détectés"
                        )
                    )

                    print(
                        (
                            f"Page {page_number} : "
                            f"{len(page_items)} "
                            "zones OCR détectées"
                        )
                    )

                    if page_text.strip():
                        page_records.append(
                            {
                                "page_number":
                                    page_number,

                                "text":
                                    page_text,

                                "items":
                                    page_items,
                            }
                        )

                finally:
                    page_image.close()

            if not page_records:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "Le PDF contient bien des "
                        "pages, mais PaddleOCR "
                        "n'a détecté aucun texte."
                    ),
                )

            # =================================================
            # SÉPARATION DU PDF EN FACTURES
            # =================================================

            invoice_groups = (
                group_pdf_pages(
                    page_records
                )
            )

        # =================================================
        # TRAITEMENT IMAGE
        # =================================================

        else:
            with Image.open(
                io.BytesIO(
                    file_data
                )
            ) as source_image:

                image_pil = (
                    source_image.convert(
                        "RGB"
                    )
                )

                try:
                    image_ocr = (
                        run_ocr_on_image(
                            ocr_engine,
                            image_pil,
                        )
                    )

                finally:
                    image_pil.close()

            cleaned_text = (
                image_ocr.get(
                    "text",
                    ""
                )
            )

            image_items = (
                image_ocr.get(
                    "items",
                    []
                )
            )

            if not cleaned_text.strip():
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "Aucun texte n'a été "
                        "détecté dans l'image."
                    ),
                )

            invoice_groups = [
                {
                    "reference": None,
                    "pages": [1],
                    "text": cleaned_text,
                    "items": image_items,
                }
            ]

        # =================================================
        # AUCUNE FACTURE DÉTECTÉE
        # =================================================

        if not invoice_groups:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Aucune facture n'a pu être "
                    "identifiée dans le document."
                ),
            )

        invoice_count = len(
            invoice_groups
        )

        print(
            "\n"
            "================================"
        )

        print(
            (
                "NOMBRE DE FACTURES "
                f"DÉTECTÉES : {invoice_count}"
            )
        )

        print(
            "================================"
        )

        saved_documents = []
        extraction_errors = []

        # =================================================
        # TRAITEMENT FACTURE PAR FACTURE
        # =================================================

        for (
            invoice_index,
            invoice_group,
        ) in enumerate(
            invoice_groups,
            start=1,
        ):
            try:
                invoice_text = (
                    invoice_group.get(
                        "text",
                        ""
                    )
                )

                invoice_items = (
                    invoice_group.get(
                        "items",
                        []
                    )
                )

                pages_numbers = (
                    invoice_group.get(
                        "pages",
                        []
                    )
                )

                reference = (
                    invoice_group.get(
                        "reference"
                    )
                )

                print(
                    "\n"
                    "================================"
                )

                print(
                    (
                        f"TRAITEMENT FACTURE "
                        f"{invoice_index}/"
                        f"{invoice_count}"
                    )
                )

                print(
                    f"Pages : {pages_numbers}"
                )

                print(
                    f"Référence : {reference}"
                )

                print(
                    "================================"
                )

                # =========================================
                # EXTRACTION CONTEXTUELLE
                # =========================================

                structured_data = (
                    extract_invoice_fields(
                        invoice_text,
                        invoice_items,
                    )
                )

                # Si group_pdf_pages() avait déjà
                # trouvé un numéro de facture,
                # on l'utilise uniquement si le parser
                # n'en a pas trouvé.
                if (
                    structured_data.get(
                        "invoice_number"
                    )
                    in (
                        None,
                        "",
                        "Non détecté",
                    )
                    and reference
                ):
                    structured_data[
                        "invoice_number"
                    ] = reference

                print(
                    "\n"
                    "======= DONNÉES EXTRAITES ======="
                )

                print(
                    structured_data
                )

                print(
                    "================================="
                )

                # =========================================
                # ICE FOURNISSEUR
                # =========================================

                supplier_ice = (
                    structured_data.get(
                        "supplier_ice"
                    )
                    or structured_data.get(
                        "ice"
                    )
                    or "Non détecté"
                )

                # =========================================
                # VÉRIFICATION ICE FOURNISSEUR
                # =========================================

                ice_result = verify_ice(
                    supplier_ice
                )

                # =========================================
                # NOM DU DOCUMENT
                # =========================================

                invoice_filename = (
                    build_invoice_filename(
                        file.filename,
                        invoice_index,
                        invoice_count,
                        structured_data.get(
                            "invoice_number"
                        )
                        or reference,
                    )
                )

                # =========================================
                # CRÉATION DU DOCUMENT
                # =========================================

                db_document = (
                    models.Document(

                        # =================================
                        # FICHIER
                        # =================================

                        filename=
                            invoice_filename,

                        extracted_text=
                            invoice_text,

                        user_id=
                            current_user.id,

                        # =================================
                        # FOURNISSEUR / CLIENT
                        # =================================

                        provider=
                            structured_data.get(
                                "provider",
                                "Non détecté",
                            ),

                        client=
                            structured_data.get(
                                "client",
                                "Non détecté",
                            ),

                        # =================================
                        # FACTURE
                        # =================================

                        invoice_date=
                            structured_data.get(
                                "date",
                                "Non détectée",
                            ),

                        invoice_number=
                            structured_data.get(
                                "invoice_number",
                                "Non détecté",
                            ),

                        # =================================
                        # ICE FOURNISSEUR
                        # =================================

                        ice=
                            supplier_ice,

                        # =================================
                        # ICE CLIENT
                        # =================================

                        client_ice=
                            structured_data.get(
                                "client_ice",
                                "Non détecté",
                            ),

                        # =================================
                        # IDENTIFIANTS FOURNISSEUR
                        # =================================

                        rc=
                            structured_data.get(
                                "rc",
                                "Non détecté",
                            ),

                        if_number=
                            structured_data.get(
                                "if_number",
                                "Non détecté",
                            ),

                        cnss=
                            structured_data.get(
                                "cnss",
                                "Non détecté",
                            ),

                        # =================================
                        # TVA
                        # =================================

                        tva_percentage=
                            structured_data.get(
                                "tva_percentage",
                                "Non détecté",
                            ),

                        tva=
                            structured_data.get(
                                "tva",
                                "Non détecté",
                            ),

                        # =================================
                        # MONTANTS
                        # =================================

                        total_ht=
                            structured_data.get(
                                "total_ht",
                                "Non détecté",
                            ),

                        total_ttc=
                            structured_data.get(
                                "total_ttc",
                                "Non détecté",
                            ),

                        # =================================
                        # VÉRIFICATION ICE
                        # =================================

                        ice_verification_status=
                            ice_result.status,

                        verified_company_name=
                            ice_result.company_name,

                        ice_verification_message=
                            ice_result.message,

                        ice_verification_url=
                            ice_result.verification_url,

                        # =================================
                        # VALIDATION
                        # =================================

                        is_validated=False,
                    )
                )

                # =========================================
                # ENREGISTREMENT POSTGRESQL
                # =========================================

                db.add(
                    db_document
                )

                db.commit()

                db.refresh(
                    db_document
                )

                # =========================================
                # NOTIFICATION
                # =========================================

                if (
                    current_user.role
                    == models.UserRole.user
                ):
                    notifications.create_notifications_for_roles(
                        db=db,

                        roles=[
                            models.UserRole.admin,
                            models.UserRole.comptable,
                        ],

                        title=(
                            "Nouvelle facture "
                            "à valider"
                        ),

                        message=(
                            f"{current_user.first_name} "
                            f"{current_user.last_name} "
                            "a extrait la facture "
                            f"{db_document.filename}. "
                            "Elle doit être vérifiée "
                            "et validée."
                        ),

                        notification_type=(
                            "invoice_to_validate"
                        ),

                        related_user_id=
                            current_user.id,

                        document_id=
                            db_document.id,
                    )

                # =========================================
                # RÉSULTAT À RENVOYER AU FRONTEND
                # =========================================

                saved_documents.append(
                    {
                        "id":
                            db_document.id,

                        "filename":
                            db_document.filename,

                        "source_filename":
                            file.filename,

                        "source_pages":
                            pages_numbers,

                        "invoice_index":
                            invoice_index,

                        # =============================
                        # FOURNISSEUR / CLIENT
                        # =============================

                        "provider":
                            db_document.provider,

                        "client":
                            db_document.client,

                        # =============================
                        # FACTURE
                        # =============================

                        "invoice_date":
                            db_document.invoice_date,

                        "invoice_number":
                            db_document.invoice_number,

                        # =============================
                        # IDENTIFIANTS
                        # =============================

                        "supplier_ice":
                            db_document.ice,

                        "client_ice":
                            db_document.client_ice,

                        "rc":
                            db_document.rc,

                        "if_number":
                            db_document.if_number,

                        "cnss":
                            db_document.cnss,

                        # =============================
                        # TVA / MONTANTS
                        # =============================

                        "tva_percentage":
                            db_document.tva_percentage,

                        "tva":
                            db_document.tva,

                        "total_ht":
                            db_document.total_ht,

                        "total_ttc":
                            db_document.total_ttc,

                        # =============================
                        # TEXTE OCR
                        # =============================

                        "extracted_text":
                            db_document.extracted_text,

                        # =============================
                        # STRUCTURED DATA
                        # =============================

                        "structured_data":
                            structured_data,

                        # =============================
                        # VÉRIFICATION ICE
                        # =============================

                        "ice_verification": {
                            "status":
                                db_document
                                .ice_verification_status,

                            "company_name":
                                db_document
                                .verified_company_name,

                            "message":
                                db_document
                                .ice_verification_message,

                            "verification_url":
                                db_document
                                .ice_verification_url,
                        },

                        # =============================
                        # VALIDATION
                        # =============================

                        "is_validated":
                            db_document.is_validated,

                        "created_at":
                            db_document.created_at,

                        "user_id":
                            db_document.user_id,

                        # =============================
                        # VALEURS CALCULÉES
                        # =============================

                        "calculated_fields":
                            structured_data.get(
                                "calculated_fields",
                                [],
                            ),

                        "calculation_details":
                            structured_data.get(
                                "calculation_details",
                                [],
                            ),

                        "warnings":
                            structured_data.get(
                                "warnings",
                                [],
                            ),
                    }
                )

            # =================================================
            # UNE FACTURE ÉCHOUE
            # =================================================

            except Exception as invoice_error:
                db.rollback()

                print(
                    "\n"
                    "================================"
                )

                print(
                    (
                        "ERREUR FACTURE "
                        f"{invoice_index}"
                    )
                )

                traceback.print_exc()

                print(
                    "================================"
                )

                extraction_errors.append(
                    {
                        "invoice_index":
                            invoice_index,

                        "pages":
                            invoice_group.get(
                                "pages",
                                [],
                            ),

                        "reference":
                            invoice_group.get(
                                "reference"
                            ),

                        "message":
                            (
                                f"{type(invoice_error).__name__}: "
                                f"{str(invoice_error)}"
                            ),
                    }
                )

        # =================================================
        # AUCUNE FACTURE ENREGISTRÉE
        # =================================================

        if not saved_documents:
            raise HTTPException(
                status_code=500,
                detail=(
                    "Le fichier a été analysé, "
                    "mais aucune facture n'a "
                    "pu être enregistrée."
                ),
            )

        # =================================================
        # RÉPONSE FINALE
        # =================================================

        return {
            "source_filename":
                file.filename,

            "invoice_count":
                len(
                    saved_documents
                ),

            "detected_invoice_count":
                invoice_count,

            "documents":
                saved_documents,

            "errors":
                extraction_errors,
        }

    # =====================================================
    # ERREUR HTTP CONNUE
    # =====================================================

    except HTTPException:
        db.rollback()
        raise

    # =====================================================
    # ERREUR GÉNÉRALE
    # =====================================================

    except Exception as error:
        db.rollback()

        print(
            "\n"
            "========== ERREUR OCR =========="
        )

        traceback.print_exc()

        print(
            "================================"
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "Erreur d'extraction OCR : "
                f"{type(error).__name__}: "
                f"{str(error)}"
            ),
        )

@router.put(
    "/documents/{document_id}/validate",
    response_model=schemas.Document
)
def validate_document(
    document_id: int,
    payload: schemas.DocumentValidate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        auth.require_role(
            "admin",
            "comptable"
        )
    )
):
    # =====================================================
    # RECHERCHE DU DOCUMENT
    # =====================================================

    doc = (
        db.query(
            models.Document
        )
        .filter(
            models.Document.id
            == document_id
        )
        .first()
    )

    if not doc:
        raise HTTPException(
            status_code=404,
            detail="Document introuvable."
        )

    # =====================================================
    # VÉRIFICATION ICE FOURNISSEUR
    # =====================================================

    # payload.ice représente toujours
    # l'ICE DU FOURNISSEUR.
    ice_result = verify_ice(
        payload.ice
    )

    # =====================================================
    # FOURNISSEUR / CLIENT
    # =====================================================

    doc.provider = (
        payload.provider
    )

    doc.client = (
        payload.client
    )

    # =====================================================
    # INFORMATIONS FACTURE
    # =====================================================

    doc.invoice_date = (
        payload.date
    )

    doc.invoice_number = (
        payload.invoice_number
    )

    # =====================================================
    # IDENTIFIANTS
    # =====================================================

    # ICE FOURNISSEUR
    doc.ice = (
        payload.ice
    )

    # ICE CLIENT
    doc.client_ice = (
        payload.client_ice
    )

    # Registre de Commerce
    doc.rc = (
        payload.rc
    )

    # Identifiant Fiscal
    doc.if_number = (
        payload.if_number
    )

    # CNSS
    doc.cnss = (
        payload.cnss
    )

    # =====================================================
    # TVA
    # =====================================================

    # Exemple :
    # 20
    # 10
    # 20 / 0
    doc.tva_percentage = (
        payload.tva_percentage
    )

    # Montant TVA
    doc.tva = (
        payload.tva
    )

    # =====================================================
    # MONTANTS
    # =====================================================

    doc.total_ht = (
        payload.total_ht
    )

    doc.total_ttc = (
        payload.total_ttc
    )

    # =====================================================
    # MISE À JOUR DU RÉSULTAT ICE
    # =====================================================

    doc.ice_verification_status = (
        ice_result.status
    )

    doc.verified_company_name = (
        ice_result.company_name
    )

    doc.ice_verification_message = (
        ice_result.message
    )

    doc.ice_verification_url = (
        ice_result.verification_url
    )

    # =====================================================
    # VALIDATION
    # =====================================================

    doc.is_validated = True

    doc.validated_by_id = (
        current_user.id
    )

    doc.validated_at = (
        datetime.utcnow()
    )

    # =====================================================
    # ENREGISTREMENT
    # =====================================================

    try:
        db.commit()

        db.refresh(
            doc
        )

    except Exception as error:
        db.rollback()

        print(
            "\n"
            "ERREUR VALIDATION DOCUMENT"
        )

        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail=(
                "Erreur lors de la validation "
                f"du document : {str(error)}"
            )
        )

    # =====================================================
    # RETOUR
    # =====================================================

    return doc


@router.get(
    "/history",
    response_model=list[schemas.Document]
)
def get_user_history(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        auth.get_current_user
    ),
    sort_by: str | None = Query(
        None,
        description=(
            "Champ de tri : 'provider', 'client', "
            "ou par défaut la date"
        )
    ),
    order: str = Query(
        "desc",
        description="'asc' ou 'desc'"
    ),
):
    # =====================================================
    # CHAMP DE TRI
    # =====================================================

    sortable_fields = {
        "provider": models.Document.provider,
        "client": models.Document.client,
    }

    sort_column = sortable_fields.get(
        sort_by,
        models.Document.created_at
    )

    # Un tri secondaire par date garde un ordre stable
    # entre les documents qui partagent le même
    # fournisseur/client.
    if order == "asc":
        ordering = (
            sort_column.asc(),
            models.Document.created_at.desc(),
        )
    else:
        ordering = (
            sort_column.desc(),
            models.Document.created_at.desc(),
        )

    query = db.query(
        models.Document
    ).order_by(*ordering)

    if current_user.role.value in (
        "admin",
        "comptable"
    ):
        return query.all()

    return query.filter(
        models.Document.user_id == current_user.id
    ).all()


@router.put(
    "/documents/{document_id}/lot",
    response_model=schemas.Document
)
def assign_document_to_lot(
    document_id: int,
    payload: schemas.DocumentAssignLot,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    document = (
        db.query(models.Document)
        .filter(models.Document.id == document_id)
        .first()
    )

    if not document:
        raise HTTPException(
            status_code=404,
            detail="Document introuvable."
        )

    is_privileged = current_user.role.value in (
        "admin",
        "comptable"
    )

    if (
        not is_privileged
        and document.user_id != current_user.id
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                "Vous ne pouvez modifier que vos propres documents."
            )
        )

    if payload.lot_id is not None:
        lot = (
            db.query(models.Lot)
            .filter(models.Lot.id == payload.lot_id)
            .first()
        )

        if not lot:
            raise HTTPException(
                status_code=404,
                detail="Lot introuvable."
            )

        if (
            not is_privileged
            and lot.created_by_id != current_user.id
        ):
            raise HTTPException(
                status_code=403,
                detail=(
                    "Vous ne pouvez utiliser que les lots "
                    "que vous avez créés."
                )
            )

    document.lot_id = payload.lot_id

    db.commit()
    db.refresh(document)

    return document
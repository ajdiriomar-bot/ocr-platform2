from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from sqlalchemy.orm import Session
from datetime import datetime
from decimal import Decimal, InvalidOperation
from PIL import Image

import io
import re
import traceback

from .database import get_db
from . import models, schemas, auth
from .services.ice_verification import verify_ice


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

    pdf = pdfium.PdfDocument(pdf_bytes)
    images = []

    try:
        for page_index in range(len(pdf)):
            page = pdf[page_index]

            try:
                bitmap = page.render(scale=1.5)
                pil_image = bitmap.to_pil().convert("RGB")
                images.append(pil_image)

            finally:
                page.close()

    finally:
        pdf.close()

    return images


def run_ocr_on_image(ocr_engine, image_pil):
    import numpy as np
    import cv2

    image_np = np.array(image_pil)
    image_cv = image_np[:, :, ::-1].copy()

    _, width = image_cv.shape[:2]

    if width < 1200:
        scale = 1200 / width

        image_cv = cv2.resize(
            image_cv,
            None,
            fx=scale,
            fy=scale,
            interpolation=cv2.INTER_CUBIC
        )

    gray = cv2.cvtColor(
        image_cv,
        cv2.COLOR_BGR2GRAY
    )

    gray = cv2.convertScaleAbs(
        gray,
        alpha=1.15,
        beta=5
    )

    image_cv = cv2.cvtColor(
        gray,
        cv2.COLOR_GRAY2BGR
    )

    print("\nLancement de PaddleOCR...")

    result = ocr_engine.predict(image_cv)

    print("PaddleOCR terminé.")
    print("Type du résultat :", type(result))

    text_lines = []

    if result is None:
        return ""

    for index, res in enumerate(result):
        print(
            f"Type du résultat numéro {index} :",
            type(res)
        )

        rec_texts = []

        if isinstance(res, dict):
            rec_texts = res.get("rec_texts", [])

        elif hasattr(res, "json"):
            try:
                result_json = res.json

                if callable(result_json):
                    result_json = result_json()

                if isinstance(result_json, dict):
                    inner_result = result_json.get(
                        "res",
                        result_json
                    )

                    if isinstance(inner_result, dict):
                        rec_texts = inner_result.get(
                            "rec_texts",
                            []
                        )

            except Exception as json_error:
                print(
                    "Impossible de lire res.json :",
                    str(json_error)
                )

        if not rec_texts:
            try:
                rec_texts = res["rec_texts"]

            except (
                KeyError,
                TypeError,
                AttributeError
            ):
                rec_texts = []

        if rec_texts is None:
            rec_texts = []

        for item in rec_texts:
            value = str(item).strip()

            if value:
                text_lines.append(value)

    print(
        "Nombre de lignes OCR détectées :",
        len(text_lines)
    )

    if text_lines:
        print("\n========== LIGNES OCR ==========")

        for line in text_lines:
            print(line)

        print("================================")

    return "\n".join(text_lines)


def extract_structured_fields(text: str):
    data = {
        "provider": "Inconnu",
        "client": "Inconnu",
        "date": "Non détectée",
        "ice": "Non détecté",
        "if_number": "Non détecté",
        "rc": "Non détecté",
        "total_ht": "0.00",
        "tva": "0.00",
        "total_ttc": "0.00"
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
    ]

    amount_regex = re.compile(
        r"(?<!\d)"
        r"(\d{1,3}(?:[ .]\d{3})+(?:[,.]\d{2})|\d+[,.]\d{2})"
        r"(?!\d)"
    )

    def normalize_amount(value: str):
        return (
            str(value)
            .replace(",", ".")
            .strip()
        )

    def amount_to_decimal(value):
        try:
            cleaned_value = (
                str(value)
                .replace(" ", "")
                .replace(",", ".")
            )

            return Decimal(cleaned_value)

        except (
            InvalidOperation,
            ValueError,
            TypeError
        ):
            return None

    def is_page_marker(value: str):
        cleaned_value = value.lower().strip(" :-")

        return bool(
            re.fullmatch(
                r"(?:page\s*)?\d+",
                cleaned_value,
                re.IGNORECASE
            )
            or re.search(
                r"page\s+\d+",
                cleaned_value,
                re.IGNORECASE
            )
        )

    def is_numeric_value(value: str):
        return bool(
            re.fullmatch(
                r"[\d\s./,:;\-]+",
                value.strip()
            )
        )

    def find_amount_near_label(
        label_pattern: str,
        search_distance: int = 5
    ):
        for index in range(len(lines) - 1, -1, -1):
            line = lines[index]

            if not re.search(
                label_pattern,
                line,
                re.IGNORECASE
            ):
                continue

            same_line_amounts = amount_regex.findall(line)

            if same_line_amounts:
                return normalize_amount(
                    same_line_amounts[-1]
                )

            for offset in range(1, search_distance + 1):
                next_index = index + offset

                if next_index >= len(lines):
                    break

                next_line = lines[next_index]

                if re.search(
                    r"\b(?:"
                    r"total\s*h\.?\s*t\.?|"
                    r"t\.?\s*v\.?\s*a\.?|"
                    r"total\s*t\.?\s*t\.?\s*c\.?|"
                    r"net\s+[àa]\s+payer"
                    r")\b",
                    next_line,
                    re.IGNORECASE
                ):
                    break

                amounts = amount_regex.findall(next_line)

                if amounts:
                    return normalize_amount(
                        amounts[-1]
                    )

            for offset in range(1, search_distance + 1):
                previous_index = index - offset

                if previous_index < 0:
                    break

                previous_line = lines[previous_index]

                if re.search(
                    r"\b(?:"
                    r"total\s*h\.?\s*t\.?|"
                    r"t\.?\s*v\.?\s*a\.?|"
                    r"total\s*t\.?\s*t\.?\s*c\.?|"
                    r"net\s+[àa]\s+payer"
                    r")\b",
                    previous_line,
                    re.IGNORECASE
                ):
                    break

                amounts = amount_regex.findall(previous_line)

                if amounts:
                    return normalize_amount(
                        amounts[-1]
                    )

        return None

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

    # =========================================================
    # FOURNISSEUR
    # =========================================================

    provider = None

    ignored_provider_lines = {
        "facture",
        "invoice",
        "devis",
        "bon de commande",
        "numéro",
        "numero",
        "date",
        "client",
        "référence",
        "reference",
        "space",
        "ea eo",
        "cocutehoue",
        "& transmission"
    }

    company_keywords = re.compile(
        r"\b(?:"
        r"sarl|s\.a\.r\.l|sa|s\.a|"
        r"société|societe|entreprise|"
        r"transmission|caoutchouc|"
        r"solutions|services|industrie|"
        r"commerce|distribution|espace"
        r")\b",
        re.IGNORECASE
    )

    provider_candidates = []

    for line in lines[:20]:
        cleaned_line = line.strip()
        lowered = cleaned_line.lower().strip(" :-")

        if not cleaned_line:
            continue

        if is_page_marker(cleaned_line):
            continue

        if lowered in ignored_provider_lines:
            continue

        if is_numeric_value(cleaned_line):
            continue

        if re.search(
            r"\b(?:"
            r"ice|if|rc|cnss|date|client|"
            r"numéro|numero|référence|reference"
            r")\b",
            cleaned_line,
            re.IGNORECASE
        ):
            continue

        if not re.search(
            r"[A-Za-zÀ-ÿ]",
            cleaned_line
        ):
            continue

        if company_keywords.search(cleaned_line):
            provider_candidates.append(cleaned_line)

    if provider_candidates:
        provider = max(
            provider_candidates,
            key=len
        )

    if not provider:
        for line in lines[:20]:
            cleaned_line = line.strip()
            lowered = cleaned_line.lower().strip(" :-")

            if not cleaned_line:
                continue

            if is_page_marker(cleaned_line):
                continue

            if lowered in ignored_provider_lines:
                continue

            if is_numeric_value(cleaned_line):
                continue

            if len(cleaned_line) < 5:
                continue

            if re.search(
                r"\b(?:"
                r"facture|client|date|numéro|numero|"
                r"référence|reference|ice|if|rc"
                r")\b",
                cleaned_line,
                re.IGNORECASE
            ):
                continue

            provider = cleaned_line
            break

    if provider:
        data["provider"] = provider[:100]

    # =========================================================
    # CLIENT
    # =========================================================

    client = None

    for index, line in enumerate(lines):
        client_match = re.search(
            r"^\s*(?:client|destinataire|acheteur)"
            r"(?:\s*[:\-])?\s*(.*)$",
            line,
            re.IGNORECASE
        )

        if not client_match:
            continue

        inline_value = client_match.group(1).strip()

        if (
            inline_value
            and not is_numeric_value(inline_value)
            and not is_page_marker(inline_value)
        ):
            client = inline_value
            break

        candidates = lines[
            index + 1:
            min(index + 10, len(lines))
        ]

        for candidate in candidates:
            cleaned_candidate = candidate.strip()

            if not cleaned_candidate:
                continue

            if is_page_marker(cleaned_candidate):
                continue

            if is_numeric_value(cleaned_candidate):
                continue

            if re.search(
                r"\b(?:"
                r"ice|if|rc|cnss|date|numéro|numero|"
                r"référence|reference|facture|"
                r"désignation|designation|qté|qte|"
                r"quantité|quantite|pu|pt"
                r")\b",
                cleaned_candidate,
                re.IGNORECASE
            ):
                continue

            if not re.search(
                r"[A-Za-zÀ-ÿ]",
                cleaned_candidate
            ):
                continue

            client = cleaned_candidate
            break

        if client:
            break

    if client:
        data["client"] = client[:100]

    # =========================================================
    # DATE
    # =========================================================

    date_patterns = [
        r"(?:date\s*(?:de\s*)?(?:facture)?"
        r"\s*[:\-]?\s*)"
        r"(\d{1,2}[./\-]\d{1,2}[./\-]\d{2,4})",

        r"(?:fait\s+[àa]\s+[A-Za-zÀ-ÿ'\- ]+"
        r"\s*(?:le)?\s*[:\-]?\s*)"
        r"(\d{1,2}[./\-]\d{1,2}[./\-]\d{2,4})",

        r"\b(\d{1,2}[./\-]\d{1,2}[./\-]\d{4})\b",

        r"\b(\d{4}[./\-]\d{1,2}[./\-]\d{1,2})\b"
    ]

    for pattern in date_patterns:
        date_match = re.search(
            pattern,
            normalized_text,
            re.IGNORECASE
        )

        if date_match:
            data["date"] = date_match.group(1)
            break

    # =========================================================
    # ICE
    # =========================================================

    ice = extract_identifier([
        r"\bI\s*\.?\s*C\s*\.?\s*E\s*\.?"
        r"(?:\s*(?:n[°o]|numéro|numero))?"
        r"\s*[:\-]?\s*"
        r"([\d\s.\-]{9,25})",

        r"identifiant\s+commun\s+de\s+l['’]entreprise"
        r"\s*[:\-]?\s*"
        r"([\d\s.\-]{9,25})"
    ], 15, 15)

    if ice:
        data["ice"] = ice

    # =========================================================
    # IF
    # =========================================================

    if_number = extract_identifier([
        r"\bI\s*\.?\s*F\s*\.?"
        r"(?:\s*(?:n[°o]|numéro|numero))?"
        r"\s*[:\-]?\s*"
        r"([\d\s.\-]{5,15})",

        r"identifiant\s+fiscal"
        r"\s*[:\-]?\s*"
        r"([\d\s.\-]{5,15})"
    ], 5, 10)

    if if_number:
        data["if_number"] = if_number

    # =========================================================
    # RC
    # =========================================================

    rc = extract_identifier([
        r"\bR\s*\.?\s*C\s*\.?\s*"
        r"(?:n[°o]|numéro|numero)?"
        r"\s*[:\-]?\s*"
        r"([\d\s.\-]{1,15})",

        r"registre\s+(?:du|de)?\s*commerce"
        r"\s*[:\-]?\s*"
        r"([\d\s.\-]{1,15})"
    ], 1, 10)

    if rc:
        data["rc"] = rc

    # =========================================================
    # MONTANTS
    # =========================================================

    total_ht = find_amount_near_label(
        r"^\s*total\s+h\.?\s*t\.?\s*$"
        r"|"
        r"^\s*montant\s+hors\s+taxe[s]?\s*$"
    )

    tva = find_amount_near_label(
        r"^\s*t\.?\s*v\.?\s*a\.?"
        r"(?:\s*\d{1,2}\s*%)?\s*$"
        r"|"
        r"^\s*taxe\s+sur\s+la\s+valeur\s+ajoutée\s*$"
    )

    total_ttc = find_amount_near_label(
        r"^\s*total\s+t\.?\s*t\.?\s*c\.?\s*$"
        r"|"
        r"^\s*net\s+[àa]\s+payer\s*$"
        r"|"
        r"^\s*total\s+général\s*$"
    )

    if total_ht:
        data["total_ht"] = total_ht

    if tva:
        data["tva"] = tva

    if total_ttc:
        data["total_ttc"] = total_ttc

    # =========================================================
    # VÉRIFICATION MATHÉMATIQUE
    # =========================================================

    ht_value = amount_to_decimal(
        data["total_ht"]
    )

    tva_value = amount_to_decimal(
        data["tva"]
    )

    ttc_value = amount_to_decimal(
        data["total_ttc"]
    )

    if (
        tva_value is not None
        and ttc_value is not None
    ):
        expected_ht = ttc_value - tva_value

        totals_are_inconsistent = (
            ht_value is None
            or abs(
                (ht_value + tva_value) - ttc_value
            ) > Decimal("0.01")
        )

        if (
            totals_are_inconsistent
            and expected_ht >= Decimal("0")
        ):
            data["total_ht"] = f"{expected_ht:.2f}"

    return data


@router.post("/extract")
async def extract_text(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        auth.get_current_user
    )
):
    content_type = file.content_type or ""

    is_image = content_type.startswith("image/")
    is_pdf = content_type == "application/pdf"

    if not (is_image or is_pdf):
        raise HTTPException(
            status_code=400,
            detail=(
                "Le fichier fourni doit être "
                "une image ou un PDF."
            )
        )

    try:
        file_data = await file.read()

        if not file_data:
            raise HTTPException(
                status_code=400,
                detail="Le fichier fourni est vide."
            )

        ocr_engine = get_ocr_engine()

        if ocr_engine is None:
            raise HTTPException(
                status_code=503,
                detail=(
                    "PaddleOCR n'est pas installé "
                    "ou n'a pas pu être chargé."
                )
            )

        if is_pdf:
            pages = pdf_to_images(file_data)

            if not pages:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Le PDF ne contient aucune "
                        "page exploitable."
                    )
                )

            all_text = []

            for page_number, page_image in enumerate(
                pages,
                start=1
            ):
                try:
                    page_text = run_ocr_on_image(
                        ocr_engine,
                        page_image
                    )

                    if page_text:
                        all_text.append(
                            f"--- PAGE {page_number} ---\n"
                            f"{page_text}"
                        )

                finally:
                    page_image.close()

            cleaned_text = "\n".join(all_text)

        else:
            with Image.open(
                io.BytesIO(file_data)
            ) as source_image:
                image_pil = source_image.convert("RGB")

                try:
                    cleaned_text = run_ocr_on_image(
                        ocr_engine,
                        image_pil
                    )

                finally:
                    image_pil.close()

        if not cleaned_text.strip():
            raise HTTPException(
                status_code=422,
                detail=(
                    "Aucun texte n'a été détecté "
                    "dans le document."
                )
            )

        print("\n========== TEXTE OCR COMPLET ==========")
        print(cleaned_text)
        print("========================================")

        structured_data = extract_structured_fields(
            cleaned_text
        )
        ice_result = verify_ice(
            structured_data["ice"]
        )

        print("\n======= DONNÉES EXTRAITES =======")
        print(structured_data)
        print("=================================")

        db_document = models.Document(
            filename=file.filename,
            extracted_text=cleaned_text,
            user_id=current_user.id,
            provider=structured_data["provider"],
            client=structured_data["client"],
            invoice_date=structured_data["date"],
            ice=structured_data["ice"],
            if_number=structured_data["if_number"],
            rc=structured_data["rc"],
            total_ht=structured_data["total_ht"],
            tva=structured_data["tva"],
            total_ttc=structured_data["total_ttc"],
            ice_verification_status=ice_result.status,
            verified_company_name=ice_result.company_name,
            ice_verification_message=ice_result.message,
            ice_verification_url=ice_result.verification_url,
            is_validated=False
        )

        db.add(db_document)
        db.commit()
        db.refresh(db_document)

        return {
            "id": db_document.id,
            "filename": db_document.filename,
            "extracted_text": db_document.extracted_text,
            "structured_data": structured_data,

            "ice_verification": {
                "status": db_document.ice_verification_status,
                "company_name": db_document.verified_company_name,
                "message": db_document.ice_verification_message,
                "verification_url": db_document.ice_verification_url
            },

            "is_validated": db_document.is_validated,
            "created_at": db_document.created_at,
            "user_id": db_document.user_id
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception as e:
        db.rollback()

        print("\n========== ERREUR OCR ==========")
        traceback.print_exc()
        print("================================")

        raise HTTPException(
            status_code=500,
            detail=(
                "Erreur d'extraction OCR : "
                f"{type(e).__name__}: {str(e)}"
            )
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
    doc = (
        db.query(models.Document)
        .filter(models.Document.id == document_id)
        .first()
    )

    if not doc:
        raise HTTPException(
            status_code=404,
            detail="Document introuvable."
        )

    doc.provider = payload.provider
    doc.client = payload.client
    doc.invoice_date = payload.date
    doc.ice = payload.ice
    doc.if_number = payload.if_number
    doc.rc = payload.rc
    doc.total_ht = payload.total_ht
    doc.tva = payload.tva
    doc.total_ttc = payload.total_ttc
    doc.is_validated = True
    doc.validated_by_id = current_user.id
    doc.validated_at = datetime.utcnow()

    db.commit()
    db.refresh(doc)

    return doc


@router.get(
    "/history",
    response_model=list[schemas.Document]
)
def get_user_history(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        auth.get_current_user
    )
):
    query = db.query(
        models.Document
    ).order_by(
        models.Document.created_at.desc()
    )

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
    current_user: models.User = Depends(
        auth.require_role(
            "admin",
            "comptable"
        )
    )
):
    doc = (
        db.query(models.Document)
        .filter(models.Document.id == document_id)
        .first()
    )

    if not doc:
        raise HTTPException(
            status_code=404,
            detail="Document introuvable."
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

    doc.lot_id = payload.lot_id

    db.commit()
    db.refresh(doc)

    return doc
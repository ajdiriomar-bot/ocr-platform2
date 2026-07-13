from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from sqlalchemy.orm import Session
from datetime import datetime
import io
import re
from PIL import Image
from .database import get_db
from . import models, schemas, auth

router = APIRouter(
    prefix="/ocr",
    tags=["OCR Extraction"]
)

_ocr_instance = None

def get_ocr_engine():
    global _ocr_instance
    if _ocr_instance is None:
        try:
            import numpy as np
            import cv2
            from paddleocr import PaddleOCR
            _ocr_instance = PaddleOCR(
                use_angle_cls=True,
                lang='fr',
                enable_mkldnn=False
            )
        except ImportError:
            _ocr_instance = False
    return _ocr_instance if _ocr_instance else None


def pdf_to_images(pdf_bytes: bytes):
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(pdf_bytes)
    images = []
    for page_index in range(len(pdf)):
        page = pdf[page_index]
        bitmap = page.render(scale=1.5)
        pil_image = bitmap.to_pil()
        images.append(pil_image.convert("RGB"))
        page.close()
    pdf.close()
    return images


def run_ocr_on_image(ocr_engine, image_pil):
    import numpy as np
    image_np = np.array(image_pil)
    image_cv = image_np[:, :, ::-1].copy()

    result = ocr_engine.predict(image_cv)
    text_lines = []
    if result:
        for res in result:
            rec_texts = res.get("rec_texts", [])
            text_lines.extend(rec_texts)
    return "\n".join(text_lines)


def extract_structured_fields(text: str):
    data = {
        "provider": "Inconnu",
        "date": "Non détectée",
        "total_ht": "0.00 €",
        "tva": "0.00 €",
        "total_ttc": "0.00 €"
    }

    date_match = re.search(r'(\d{2}[/-]\d{2}[/-]\d{4})', text)
    if date_match:
        data["date"] = date_match.group(1)

    lines = [line.strip() for line in text.split('\n') if line.strip()]
    if lines:
        data["provider"] = lines[0][:30]

    ht_match = re.search(r'(?:total\s+ht|ht)[:\s]+([\d\s,.]+\s?€?)', text, re.IGNORECASE)
    tva_match = re.search(r'(?:tva|taxe)[:\s]+([\d\s,.]+\s?€?)', text, re.IGNORECASE)
    ttc_match = re.search(r'(?:total\s+ttc|net\s+a\s+payer|total)[:\s]+([\d\s,.]+\s?€?)', text, re.IGNORECASE)

    if ht_match: data["total_ht"] = ht_match.group(1).strip()
    if tva_match: data["tva"] = tva_match.group(1).strip()
    if ttc_match: data["total_ttc"] = ttc_match.group(1).strip()

    return data


@router.post("/extract")
async def extract_text(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    is_image = file.content_type.startswith("image/")
    is_pdf = file.content_type == "application/pdf"

    if not (is_image or is_pdf):
        raise HTTPException(status_code=400, detail="Le fichier fourni doit être une image ou un PDF.")

    try:
        file_data = await file.read()
        ocr_engine = get_ocr_engine()

        if ocr_engine is not None:
            if is_pdf:
                pages = pdf_to_images(file_data)
                all_text = []
                for page_image in pages:
                    page_text = run_ocr_on_image(ocr_engine, page_image)
                    all_text.append(page_text)
                cleaned_text = "\n".join(all_text)
            else:
                image_pil = Image.open(io.BytesIO(file_data)).convert('RGB')
                cleaned_text = run_ocr_on_image(ocr_engine, image_pil)
        else:
            cleaned_text = "PaddleOCR n'est pas encore installé.\nTOTAL HT: 150.00 EUR\nTVA: 30.00 EUR\nTOTAL TTC: 180.00 EUR\nDate: 07/07/2026"

        structured_data = extract_structured_fields(cleaned_text)

        db_document = models.Document(
            filename=file.filename,
            extracted_text=cleaned_text,
            user_id=current_user.id,
            provider=structured_data["provider"],
            invoice_date=structured_data["date"],
            total_ht=structured_data["total_ht"],
            tva=structured_data["tva"],
            total_ttc=structured_data["total_ttc"],
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
            "is_validated": db_document.is_validated,
            "created_at": db_document.created_at,
            "user_id": db_document.user_id
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Erreur d'extraction OCR : {str(e)}")


@router.put("/documents/{document_id}/validate", response_model=schemas.Document)
def validate_document(
    document_id: int,
    payload: schemas.DocumentValidate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role("admin", "comptable"))
):
    
    doc = db.query(models.Document).filter(models.Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document introuvable.")

    doc.provider = payload.provider
    doc.invoice_date = payload.date
    doc.total_ht = payload.total_ht
    doc.tva = payload.tva
    doc.total_ttc = payload.total_ttc
    doc.is_validated = True
    doc.validated_by_id = current_user.id
    doc.validated_at = datetime.utcnow()

    db.commit()
    db.refresh(doc)
    return doc


@router.get("/history", response_model=list[schemas.Document])
def get_user_history(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    
    if current_user.role.value in ("admin", "comptable"):
        return db.query(models.Document).all()
    return db.query(models.Document).filter(models.Document.user_id == current_user.id).all()


@router.put("/documents/{document_id}/lot", response_model=schemas.Document)
def assign_document_to_lot(
    document_id: int,
    payload: schemas.DocumentAssignLot,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role("admin", "comptable"))
):
    """
    Assigne (ou retire, si lot_id=null) un document à un lot.
    Réservé aux comptables et administrateurs.
    """
    doc = db.query(models.Document).filter(models.Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document introuvable.")

    if payload.lot_id is not None:
        lot = db.query(models.Lot).filter(models.Lot.id == payload.lot_id).first()
        if not lot:
            raise HTTPException(status_code=404, detail="Lot introuvable.")

    doc.lot_id = payload.lot_id
    db.commit()
    db.refresh(doc)
    return doc
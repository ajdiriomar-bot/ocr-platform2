from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from . import auth, models, schemas
from .database import get_db


router = APIRouter(
    prefix="/lots",
    tags=["Lots de factures"]
)


@router.post("", response_model=schemas.Lot)
def create_lot(
    payload: schemas.LotCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    if payload.reference:
        existing_lot = (
            db.query(models.Lot)
            .filter(models.Lot.reference == payload.reference)
            .first()
        )

        if existing_lot:
            raise HTTPException(
                status_code=400,
                detail="Cette référence de lot existe déjà."
            )

    # Une référence temporaire unique est utilisée jusqu'à ce que
    # l'identifiant du lot soit généré par la base de données.
    temporary_reference = (
        payload.reference
        or f"PENDING-{uuid4().hex}"
    )

    new_lot = models.Lot(
        reference=temporary_reference,
        created_by_id=current_user.id
    )

    db.add(new_lot)
    db.commit()
    db.refresh(new_lot)

    # Si aucune référence n'a été fournie, on génère LOT-00001,
    # LOT-00002, etc.
    if not payload.reference:
        new_lot.reference = f"LOT-{new_lot.id:05d}"

        db.commit()
        db.refresh(new_lot)

    result = schemas.Lot.model_validate(new_lot)
    result.document_count = 0

    return result


@router.get("", response_model=list[schemas.Lot])
def list_lots(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        auth.require_role("admin", "comptable")
    )
):
    lots = (
        db.query(models.Lot)
        .order_by(models.Lot.created_at.desc())
        .all()
    )

    results = []

    for lot in lots:
        item = schemas.Lot.model_validate(lot)
        item.document_count = len(lot.documents)
        results.append(item)

    return results


@router.get("/{lot_id}", response_model=schemas.LotDetail)
def get_lot(
    lot_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        auth.require_role("admin", "comptable")
    )
):
    lot = (
        db.query(models.Lot)
        .filter(models.Lot.id == lot_id)
        .first()
    )

    if not lot:
        raise HTTPException(
            status_code=404,
            detail="Lot introuvable."
        )

    result = schemas.LotDetail.model_validate(lot)
    result.document_count = len(lot.documents)
    result.documents = [
        schemas.Document.model_validate(document)
        for document in lot.documents
    ]

    return result


@router.delete("/{lot_id}")
def delete_lot(
    lot_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        auth.require_role("admin", "comptable")
    )
):
    lot = (
        db.query(models.Lot)
        .filter(models.Lot.id == lot_id)
        .first()
    )

    if not lot:
        raise HTTPException(
            status_code=404,
            detail="Lot introuvable."
        )

    # Les factures sont détachées du lot, mais ne sont pas supprimées.
    for document in lot.documents:
        document.lot_id = None

    reference = lot.reference

    db.delete(lot)
    db.commit()

    return {
        "message": (
            f"Lot {reference} supprimé. "
            "Les documents associés ont été détachés."
        )
    }
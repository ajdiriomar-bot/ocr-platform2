from collections.abc import Iterable

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query
)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from . import auth, models, schemas
from .database import get_db


router = APIRouter(
    prefix="/notifications",
    tags=["Notifications"]
)


def create_notifications_for_roles(
    db: Session,
    roles: Iterable[models.UserRole | str],
    title: str,
    message: str,
    notification_type: str,
    related_user_id: int | None = None,
    document_id: int | None = None
) -> None:
    """
    Crée une notification pour tous les utilisateurs actifs
    possédant l'un des rôles demandés.
    """

    normalized_roles = [
        role
        if isinstance(role, models.UserRole)
        else models.UserRole(role)
        for role in roles
    ]

    recipients = (
        db.query(models.User)
        .filter(
            models.User.role.in_(normalized_roles),
            models.User.status
            == models.AccountStatus.active
        )
        .all()
    )

    if not recipients:
        return

    new_notifications = [
        models.Notification(
            recipient_id=recipient.id,
            title=title,
            message=message,
            notification_type=notification_type,
            related_user_id=related_user_id,
            document_id=document_id
        )
        for recipient in recipients
    ]

    try:
        db.add_all(new_notifications)
        db.commit()

    except SQLAlchemyError as error:
        db.rollback()

        print(
            "Erreur pendant la création "
            f"des notifications : {error}"
        )


@router.get(
    "",
    response_model=list[schemas.Notification]
)
def list_notifications(
    limit: int = Query(
        default=50,
        ge=1,
        le=100
    ),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        auth.get_current_user
    )
):
    return (
        db.query(models.Notification)
        .filter(
            models.Notification.recipient_id
            == current_user.id
        )
        .order_by(
            models.Notification.created_at.desc()
        )
        .limit(limit)
        .all()
    )


@router.patch("/read-all")
def mark_all_notifications_as_read(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        auth.get_current_user
    )
):
    updated_count = (
        db.query(models.Notification)
        .filter(
            models.Notification.recipient_id
            == current_user.id,
            models.Notification.is_read.is_(False)
        )
        .update(
            {
                models.Notification.is_read: True
            },
            synchronize_session=False
        )
    )

    db.commit()

    return {
        "message": (
            "Toutes les notifications ont été "
            "marquées comme lues."
        ),
        "updated_count": updated_count
    }


@router.patch(
    "/{notification_id}/read",
    response_model=schemas.Notification
)
def mark_notification_as_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        auth.get_current_user
    )
):
    notification = (
        db.query(models.Notification)
        .filter(
            models.Notification.id
            == notification_id,
            models.Notification.recipient_id
            == current_user.id
        )
        .first()
    )

    if not notification:
        raise HTTPException(
            status_code=404,
            detail="Notification introuvable."
        )

    notification.is_read = True

    db.commit()
    db.refresh(notification)

    return notification
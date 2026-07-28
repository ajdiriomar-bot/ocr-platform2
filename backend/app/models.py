from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    Text,
    DateTime,
    ForeignKey,
    Enum
)
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

from .database import Base


class UserRole(str, enum.Enum):
    admin = "admin"
    comptable = "comptable"
    user = "user"


class AccountStatus(str, enum.Enum):
    pending = "pending"
    active = "active"
    suspended = "suspended"


class User(Base):
    __tablename__ = "users"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    first_name = Column(
        String,
        nullable=False
    )

    last_name = Column(
        String,
        nullable=False
    )

    phone_number = Column(
        String,
        nullable=False
    )

    email = Column(
        String,
        unique=True,
        index=True,
        nullable=False
    )

    hashed_password = Column(
        String,
        nullable=False
    )

    role = Column(
        Enum(UserRole),
        default=UserRole.user,
        nullable=False
    )

    status = Column(
        Enum(AccountStatus),
        default=AccountStatus.pending,
        nullable=False
    )

    documents = relationship(
        "Document",
        foreign_keys="[Document.user_id]",
        back_populates="owner",
        cascade="all, delete-orphan"
    )


class Lot(Base):
    __tablename__ = "lots"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    reference = Column(
        String,
        unique=True,
        nullable=False
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )

    created_by_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False
    )

    creator = relationship(
        "User",
        foreign_keys=[created_by_id]
    )

    documents = relationship(
        "Document",
        back_populates="lot"
    )


class Document(Base):
    __tablename__ = "documents"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    filename = Column(
        String,
        nullable=False
    )

    extracted_text = Column(
        Text,
        nullable=True
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )

    provider = Column(
        String,
        nullable=True
    )

    client = Column(
        String,
        nullable=True
    )

    invoice_date = Column(
        String,
        nullable=True
    )

    ice = Column(
        String,
        nullable=True
    )

    if_number = Column(
        String,
        nullable=True
    )

    rc = Column(
        String,
        nullable=True
    )

    total_ht = Column(
        String,
        nullable=True
    )

    tva = Column(
        String,
        nullable=True
    )

    total_ttc = Column(
        String,
        nullable=True
    )

    # =========================================================
    # VÉRIFICATION ICE
    # =========================================================

    ice_verification_status = Column(
        String(30),
        nullable=False,
        default="non_verifie"
    )

    verified_company_name = Column(
        String(255),
        nullable=True
    )

    ice_verification_message = Column(
        String(500),
        nullable=True
    )

    ice_verification_url = Column(
        String(500),
        nullable=True
    )

    # =========================================================
    # VALIDATION DU DOCUMENT
    # =========================================================

    is_validated = Column(
        Boolean,
        default=False,
        nullable=False
    )

    validated_by_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=True
    )

    validated_at = Column(
        DateTime,
        nullable=True
    )

    # =========================================================
    # LOT
    # =========================================================

    lot_id = Column(
        Integer,
        ForeignKey("lots.id"),
        nullable=True
    )

    # =========================================================
    # PROPRIÉTAIRE DU DOCUMENT
    # =========================================================

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False
    )

    owner = relationship(
        "User",
        foreign_keys=[user_id],
        back_populates="documents"
    )

    validator = relationship(
        "User",
        foreign_keys=[validated_by_id]
    )

    lot = relationship(
        "Lot",
        back_populates="documents"
    )
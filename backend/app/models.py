from sqlalchemy import Column, Integer, String, Boolean, Text, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from .database import Base


class UserRole(str, enum.Enum):
    admin = "admin"
    comptable = "comptable"
    user = "user"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    role = Column(Enum(UserRole), default=UserRole.user, nullable=False)

    documents = relationship(
        "Document",
        foreign_keys="[Document.user_id]",
        back_populates="owner",
        cascade="all, delete-orphan"
    )


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    extracted_text = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Champs structurés (Étape 6/7)
    provider = Column(String, nullable=True)
    invoice_date = Column(String, nullable=True)
    total_ht = Column(String, nullable=True)
    tva = Column(String, nullable=True)
    total_ttc = Column(String, nullable=True)

    # Validation (réservée à comptable/admin)
    is_validated = Column(Boolean, default=False, nullable=False)
    validated_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    validated_at = Column(DateTime, nullable=True)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    owner = relationship("User", foreign_keys=[user_id], back_populates="documents")
    validator = relationship("User", foreign_keys=[validated_by_id])
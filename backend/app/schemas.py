from pydantic import BaseModel, EmailStr
from datetime import datetime
from .models import UserRole, AccountStatus


class UserCreate(BaseModel):
    first_name: str
    last_name: str
    phone_number: str
    email: EmailStr
    password: str


class User(BaseModel):
    id: int
    first_name: str
    last_name: str
    phone_number: str
    email: EmailStr
    role: UserRole
    status: AccountStatus

    class Config:
        from_attributes = True


class UserRoleUpdate(BaseModel):
    role: UserRole


class UserStatusUpdate(BaseModel):
    status: AccountStatus


class DocumentBase(BaseModel):
    filename: str
    extracted_text: str | None = None


class DocumentCreate(DocumentBase):
    pass


class Document(DocumentBase):
    id: int
    created_at: datetime
    user_id: int
    provider: str | None = None
    client: str | None = None
    invoice_date: str | None = None
    total_ht: str | None = None
    tva: str | None = None
    total_ttc: str | None = None
    is_validated: bool
    validated_by_id: int | None = None
    validated_at: datetime | None = None
    lot_id: int | None = None

    class Config:
        from_attributes = True


class DocumentValidate(BaseModel):
    provider: str
    client: str
    date: str
    total_ht: str
    tva: str
    total_ttc: str


class DocumentAssignLot(BaseModel):
    lot_id: int | None  # None pour retirer un document d'un lot


class LotCreate(BaseModel):
    reference: str | None = None  # optionnel, auto-généré si absent


class Lot(BaseModel):
    id: int
    reference: str
    created_at: datetime
    created_by_id: int
    document_count: int = 0

    class Config:
        from_attributes = True


class LotDetail(Lot):
    documents: list[Document] = []
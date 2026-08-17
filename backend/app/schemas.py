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


class Document(BaseModel):
    id: int
    filename: str
    extracted_text: str | None = None

    created_at: datetime
    user_id: int

    provider: str | None = None
    client: str | None = None
    invoice_date: str | None = None
    invoice_number: str | None = None
    client_ice: str | None = None
    tva_percentage: str | None = None
    cnss: str | None = None

    ice: str | None = None
    if_number: str | None = None
    rc: str | None = None

    total_ht: str | None = None
    tva: str | None = None
    total_ttc: str | None = None

    

    ice_verification_status: str
    verified_company_name: str | None = None
    ice_verification_message: str | None = None
    ice_verification_url: str | None = None

    # ================================

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

    invoice_number: str = "Non détecté"

    # ICE fournisseur
    ice: str

    # ICE client
    client_ice: str = "Non détecté"

    if_number: str
    rc: str
    cnss: str = "Non détecté"

    tva_percentage: str = "Non détecté"

    total_ht: str
    tva: str
    total_ttc: str


class DocumentAssignLot(BaseModel):
    lot_id: int | None

class Notification(BaseModel):
    id: int
    title: str
    message: str
    notification_type: str
    is_read: bool
    created_at: datetime
    related_user_id: int | None = None
    document_id: int | None = None

    class Config:
        from_attributes = True


class LotCreate(BaseModel):
    reference: str | None = None


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
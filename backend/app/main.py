from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session
from . import crud, models, schemas, auth
from .database import engine, get_db
from fastapi.security import OAuth2PasswordRequestForm
from datetime import timedelta
from .auth import create_access_token, get_current_user, require_role
from fastapi.middleware.cors import CORSMiddleware
from . import ocr
from . import ocr, lots

models.Base.metadata.create_all(bind=engine)

app = FastAPI()

app.include_router(ocr.router)
app.include_router(lots.router)


origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "OCR Platform est opérationnel"}

@app.post("/register", response_model=schemas.User)
def register_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = crud.get_user_by_email(db, email=user.email)
    if db_user:
        raise HTTPException(status_code=400, detail="Email déjà enregistré")

    hashed_password = auth.get_password_hash(user.password)
    return crud.create_user(db, user, hashed_password)

@app.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = crud.get_user_by_email(db, email=form_data.username)
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou mot de passe incorrect"
        )

    if user.status == models.AccountStatus.pending:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Votre compte est en cours de vérification. Un administrateur doit l'activer avant que vous puissiez vous connecter."
        )

    if user.status == models.AccountStatus.suspended:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Votre compte a été suspendu. Veuillez contacter un administrateur."
        )

    access_token_expires = timedelta(minutes=30)
    access_token = create_access_token(data={"sub": user.email}, expires_delta=access_token_expires)

    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/users/me", response_model=schemas.User)
def read_users_me(current_user: schemas.User = Depends(get_current_user)):
    return current_user


@app.get("/users", response_model=list[schemas.User])
def list_users(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin"))
):
    """Liste tous les utilisateurs. Réservé aux administrateurs."""
    return db.query(models.User).all()


@app.patch("/users/{user_id}/role", response_model=schemas.User)
def update_user_role(
    user_id: int,
    role_update: schemas.UserRoleUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin"))
):
    """Change le rôle d'un utilisateur. Réservé aux administrateurs."""
    target_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable.")

    if target_user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Vous ne pouvez pas modifier votre propre rôle.")

    target_user.role = role_update.role
    db.commit()
    db.refresh(target_user)
    return target_user


@app.patch("/users/{user_id}/status", response_model=schemas.User)
def update_user_status(
    user_id: int,
    status_update: schemas.UserStatusUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin"))
):
    """
    Change le statut d'un utilisateur (pending/active/suspended).
    Réservé aux administrateurs. Permet de valider une inscription,
    activer, ou suspendre un compte.
    """
    target_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable.")

    if target_user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Vous ne pouvez pas modifier le statut de votre propre compte.")

    target_user.status = status_update.status
    db.commit()
    db.refresh(target_user)
    return target_user


@app.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin"))
):
    """Supprime un utilisateur. Réservé aux administrateurs."""
    target_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable.")

    if target_user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Vous ne pouvez pas supprimer votre propre compte.")

    db.delete(target_user)
    db.commit()
    return {"message": f"Utilisateur {target_user.email} supprimé avec succès."}
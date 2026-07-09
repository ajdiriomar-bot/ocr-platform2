from app.database import engine, Base
from app.models import User  
print("Création des tables dans la base de données...")

Base.metadata.create_all(bind=engine)

print("Tables créées avec succès !")
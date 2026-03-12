# backend/create_tables.py
import importlib
import pkgutil
import app.models
from app.database import Base, engine

# Auto-import all modules in app.models
for _, module_name, _ in pkgutil.iter_modules(app.models.__path__):
    importlib.import_module(f"app.models.{module_name}")

Base.metadata.create_all(bind=engine)
print("✅ Tables created successfully")
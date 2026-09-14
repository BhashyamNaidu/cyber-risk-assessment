"""Shared absolute paths — every ml/ module imports DATA_DIR from here
instead of hardcoding relative paths, so the modules work identically
whether run directly, imported by the backend, or imported by tests."""
from pathlib import Path

ML_DIR = Path(__file__).resolve().parent
REPO_ROOT = ML_DIR.parent
DATA_DIR = REPO_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

DATASET_PATH = DATA_DIR / "synthetic_dataset.csv"
MODEL_PATH = DATA_DIR / "rf_model.joblib"
OBSERVABLE_MODEL_PATH = DATA_DIR / "rf_observable_model.joblib"
ENCODER_PATH = DATA_DIR / "os_type_encoder.joblib"
SCHEMA_PATH = DATA_DIR / "model_schema.json"

from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql://dealmind:dealmind@localhost:5432/dealmind"

    # JWT
    JWT_SECRET_KEY: str = "dealmind-hackathon-secret-key-2026"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 480

    # LLM (OpenRouter — free models)
    OPENROUTER_API_KEY: str = ""
    LLM_MODEL: str = "deepseek/deepseek-r1-0528:free"

    # File Storage
    UPLOAD_DIR: str = "./uploads"
    CHROMA_PERSIST_DIR: str = "./chroma_data"

    # Embedding
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"

    # Google OAuth (Gmail + Calendar)
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/integrations/google/callback"
    GOOGLE_FRONTEND_REDIRECT: str = "http://localhost:5173/settings"

    # Twilio WhatsApp (for deal risk alerts)
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_WHATSAPP_FROM: str = ""       # e.g. "+14155238886" (Twilio sandbox number)
    ADMIN_WHATSAPP_NUMBER: str = ""       # e.g. "+94771234567" (your WhatsApp number)

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = True

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @property
    def upload_path(self) -> Path:
        path = Path(self.UPLOAD_DIR)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def chroma_path(self) -> Path:
        path = Path(self.CHROMA_PERSIST_DIR)
        path.mkdir(parents=True, exist_ok=True)
        return path


settings = Settings()

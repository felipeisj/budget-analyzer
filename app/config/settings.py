"""
Configuración del sistema para el analizador de PDFs MOP.
Maneja todas las variables de entorno y configuración de la aplicación.
"""

from typing import Optional, List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, validator
import os
from pathlib import Path


class Settings(BaseSettings):
    """Configuración principal del sistema MOP PDF Analyzer."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )
    
    # === CONFIGURACIÓN API ===
    ANTHROPIC_API_KEY: str = Field(..., description="API Key de Anthropic Claude")
    ENVIRONMENT: str = Field(default="development", description="Entorno de ejecución")
    DEBUG: bool = Field(default=False, description="Modo debug")
    
    # === CONFIGURACIÓN DE ARCHIVOS ===
    MAX_FILE_SIZE: int = Field(
        default=20971520,  # 20MB
        description="Tamaño máximo de archivo en bytes"
    )
    PROCESSING_TIMEOUT: int = Field(
        default=300,  # 5 minutos
        description="Timeout de procesamiento en segundos"
    )
    MAX_CHUNKS_PER_PDF: int = Field(
        default=50,
        description="Máximo número de chunks por PDF"
    )
    
    # === CONFIGURACIÓN CLAUDE API ===
    CLAUDE_MODEL: str = Field(
        default="claude-3-5-haiku-20241022",
        description="Modelo de Claude a utilizar"
    )
    CLAUDE_MAX_TOKENS: int = Field(
        default=8000,
        description="Máximo tokens por request a Claude"
    )
    CLAUDE_TEMPERATURE: float = Field(
        default=0.1,
        description="Temperatura para Claude (0.0 = determinístico)"
    )
    
    # === RATE LIMITING ===
    REQUESTS_PER_MINUTE: int = Field(
        default=60,
        description="Requests por minuto permitidos"
    )
    BURST_SIZE: int = Field(
        default=10,
        description="Tamaño del burst para rate limiting"
    )
    
    # === RUTAS DE ALMACENAMIENTO ===
    TEMP_STORAGE_PATH: str = Field(
        default="storage/temp",
        description="Ruta para archivos temporales"
    )
    PROCESSED_STORAGE_PATH: str = Field(
        default="storage/processed",
        description="Ruta para archivos procesados"
    )
    RESULTS_STORAGE_PATH: str = Field(
        default="storage/results",
        description="Ruta para resultados de análisis"
    )
    
    # === CONFIGURACIÓN DE LOGGING ===
    LOG_LEVEL: str = Field(
        default="INFO",
        description="Nivel de logging"
    )
    LOG_FORMAT: str = Field(
        default="json",
        description="Formato de logs (json|text)"
    )
    
    # === CONFIGURACIÓN PDF PROCESSING ===
    PDF_DPI: int = Field(
        default=300,
        description="DPI para conversión de imágenes"
    )
    OCR_LANGUAGE: str = Field(
        default="spa",
        description="Idioma para OCR (español)"
    )
    TEXT_CHUNK_SIZE: int = Field(
        default=8000,
        description="Tamaño máximo de chunk de texto para Claude"
    )
    TEXT_CHUNK_OVERLAP: int = Field(
        default=500,
        description="Overlap entre chunks de texto"
    )
    
    # === VALIDACIONES MOP ===
    IVA_RATE: float = Field(
        default=0.19,
        description="Tasa de IVA en Chile"
    )
    MAX_UNIT_PRICE: int = Field(
        default=10000000,  # 10M CLP
        description="Precio unitario máximo permitido"
    )
    
    # === CONFIGURACIÓN CORS ===
    CORS_ORIGINS: List[str] = Field(
        default=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "https://localhost:3000"
        ],
        description="Orígenes permitidos para CORS"
    )
    
    @validator("ANTHROPIC_API_KEY")
    def validate_anthropic_key(cls, v):
        if not v or not v.startswith("sk-ant-"):
            raise ValueError("ANTHROPIC_API_KEY debe comenzar con 'sk-ant-'")
        return v
    
    @validator("LOG_LEVEL")
    def validate_log_level(cls, v):
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"LOG_LEVEL debe ser uno de: {valid_levels}")
        return v.upper()
    
    @validator("ENVIRONMENT")
    def validate_environment(cls, v):
        valid_envs = ["development", "staging", "production"]
        if v not in valid_envs:
            raise ValueError(f"ENVIRONMENT debe ser uno de: {valid_envs}")
        return v
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.ensure_storage_paths()
    
    def ensure_storage_paths(self):
        """Crea las carpetas de almacenamiento si no existen."""
        paths = [
            self.TEMP_STORAGE_PATH,
            self.PROCESSED_STORAGE_PATH,
            self.RESULTS_STORAGE_PATH
        ]
        
        for path_str in paths:
            path = Path(path_str)
            path.mkdir(parents=True, exist_ok=True)
    
    @property
    def is_development(self) -> bool:
        """Retorna True si estamos en modo desarrollo."""
        return self.ENVIRONMENT == "development"
    
    @property
    def is_production(self) -> bool:
        """Retorna True si estamos en modo producción."""
        return self.ENVIRONMENT == "production"
    
    @property
    def max_file_size_mb(self) -> float:
        """Retorna el tamaño máximo de archivo en MB."""
        return self.MAX_FILE_SIZE / (1024 * 1024)


# Instancia global de configuración
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """
    Retorna la instancia singleton de configuración.
    Patrón singleton para evitar recrear la configuración múltiples veces.
    """
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


# Configuración específica para diferentes entornos
class DevelopmentSettings(Settings):
    """Configuración para desarrollo."""
    DEBUG: bool = True
    LOG_LEVEL: str = "DEBUG"
    PROCESSING_TIMEOUT: int = 600  # 10 minutos en desarrollo


class ProductionSettings(Settings):
    """Configuración para producción."""
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    PROCESSING_TIMEOUT: int = 300  # 5 minutos en producción
    MAX_FILE_SIZE: int = 20971520  # Límite estricto en producción


def get_settings_for_env(environment: str) -> Settings:
    """Retorna la configuración específica para un entorno."""
    if environment == "development":
        return DevelopmentSettings()
    elif environment == "production":
        return ProductionSettings()
    else:
        return Settings()


if __name__ == "__main__":
    # Test básico de configuración
    settings = get_settings()
    print(f"Entorno: {settings.ENVIRONMENT}")
    print(f"Debug: {settings.DEBUG}")
    print(f"Max file size: {settings.max_file_size_mb:.1f}MB")
    print(f"Storage paths creados: OK")
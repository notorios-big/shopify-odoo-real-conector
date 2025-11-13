"""
Configuración del conector Odoo-Shopify.

Carga las variables de entorno necesarias para la operación del conector.
"""
import os
from pydantic_settings import BaseSettings
from pydantic import Field, validator


class Settings(BaseSettings):
    """
    Configuración de la aplicación cargada desde variables de entorno.
    """
    # Configuración de Shopify
    SHOPIFY_STORE_URL: str = Field(
        ...,
        description="URL de la tienda Shopify (ej: https://mi-tienda.myshopify.com)"
    )
    SHOPIFY_ACCESS_TOKEN: str = Field(
        ...,
        description="Token de acceso a la Admin API de Shopify"
    )
    SHOPIFY_API_VERSION: str = Field(
        default="2025-10",
        description="Versión de la API de Shopify"
    )

    # Configuración del servidor
    HOST: str = Field(
        default="0.0.0.0",
        description="Host donde escuchará el servidor FastAPI"
    )
    PORT: int = Field(
        default=8000,
        description="Puerto donde escuchará el servidor FastAPI"
    )

    # Configuración de logging
    LOG_LEVEL: str = Field(
        default="INFO",
        description="Nivel de logging (DEBUG, INFO, WARNING, ERROR)"
    )

    @validator('SHOPIFY_STORE_URL')
    def validate_store_url(cls, v):
        """Valida que la URL de Shopify tenga el formato correcto"""
        if not v.startswith('https://'):
            raise ValueError("SHOPIFY_STORE_URL debe comenzar con https://")
        if v.endswith('/'):
            v = v[:-1]  # Remover trailing slash
        return v

    @validator('LOG_LEVEL')
    def validate_log_level(cls, v):
        """Valida que el nivel de log sea válido"""
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in valid_levels:
            raise ValueError(f"LOG_LEVEL debe ser uno de: {valid_levels}")
        return v.upper()

    class Config:
        """Configuración de Pydantic Settings"""
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


# Instancia global de configuración
settings = Settings()

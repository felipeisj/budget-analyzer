"""
Aplicación principal FastAPI para MOP PDF Analyzer.
"""

import logging
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

# Configurar logging
from loguru import logger
from app.config.settings import get_settings

# Configurar loguru
logger.remove()  # Remover handler por defecto
logger.add(sys.stderr, level="INFO", format="{time} | {level} | {message}")

# Importar endpoints
from app.api.endpoints import budget_analysis
from app.utils.file_utils import ensure_directories


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestión del ciclo de vida de la aplicación."""
    # Startup
    logger.info("Iniciando MOP PDF Analyzer...")
    
    # Configurar directorios
    await ensure_directories()
    logger.info("Directorios de almacenamiento configurados")
    
    # Validar configuración
    settings = get_settings()
    logger.info(f"Configuración cargada - Entorno: {settings.ENVIRONMENT}")
    
    if not settings.ANTHROPIC_API_KEY or settings.ANTHROPIC_API_KEY == "your_anthropic_api_key_here":
        logger.error("ANTHROPIC_API_KEY no configurada correctamente")
        raise ValueError("ANTHROPIC_API_KEY requerida")
    
    logger.info("✓ Aplicación iniciada correctamente")
    
    yield
    
    # Shutdown
    logger.info("Cerrando aplicación...")


# Crear aplicación FastAPI
app = FastAPI(
    title="MOP PDF Analyzer",
    version="1.0.0",
    description="Microservicio para análisis de PDFs de licitaciones MOP usando IA",
    lifespan=lifespan
)

# Configurar CORS
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# === ENDPOINTS PRINCIPALES ===

@app.get("/")
async def root():
    """Endpoint raíz con información de la API."""
    return {
        "service": "MOP PDF Analyzer",
        "version": "1.0.0",
        "status": "operational",
        "description": "Análisis inteligente de PDFs de licitaciones MOP",
        "endpoints": {
            "analyze_pdf": "/api/budget-analysis/pdf",
            "get_result": "/api/budget-analysis/pdf/{analysis_id}",
            "health": "/health",
            "status": "/api/budget-analysis/status"
        }
    }


@app.get("/health")
async def health_check():
    """Health check detallado del servicio."""
    settings = get_settings()
    
    # Verificaciones básicas
    checks = {
        "api_key_configured": bool(settings.ANTHROPIC_API_KEY and settings.ANTHROPIC_API_KEY != "your_anthropic_api_key_here"),
        "storage_writable": True,  # TODO: Verificar escritura en storage
        "claude_api_reachable": True  # TODO: Ping a Claude API
    }
    
    all_healthy = all(checks.values())
    
    return JSONResponse(
        status_code=200 if all_healthy else 503,
        content={
            "status": "healthy" if all_healthy else "unhealthy",
            "service": "mop-pdf-analyzer",
            "environment": settings.ENVIRONMENT,
            "timestamp": "2024-01-01T00:00:00Z",  # TODO: Usar timestamp real
            "checks": checks,
            "configuration": {
                "max_file_size_mb": settings.max_file_size_mb,
                "processing_timeout_seconds": settings.PROCESSING_TIMEOUT,
                "cors_origins": len(settings.CORS_ORIGINS)
            }
        }
    )


# === INCLUIR ROUTERS ===
app.include_router(budget_analysis.router)


# === MANEJO GLOBAL DE ERRORES ===

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Manejo centralizado de excepciones HTTP."""
    logger.warning(f"HTTP {exc.status_code}: {exc.detail}")
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": True,
            "status_code": exc.status_code,
            "message": exc.detail,
            "timestamp": "2024-01-01T00:00:00Z"  # TODO: Timestamp real
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Manejo de excepciones generales."""
    logger.error(f"Error no manejado: {exc}", exc_info=True)
    
    settings = get_settings()
    
    response_content = {
        "error": True,
        "status_code": 500,
        "message": "Error interno del servidor",
        "timestamp": "2024-01-01T00:00:00Z"
    }
    
    # En desarrollo, incluir detalles del error
    if settings.DEBUG:
        response_content["details"] = str(exc)
        response_content["type"] = exc.__class__.__name__
    
    return JSONResponse(
        status_code=500,
        content=response_content
    )


# === MIDDLEWARE PERSONALIZADO ===

@app.middleware("http")
async def log_requests(request, call_next):
    """Log de todas las requests."""
    start_time = request.state.start_time = None  # TODO: Timestamp real
    
    # Log request
    logger.info(f"{request.method} {request.url.path}")
    
    # Procesar request
    response = await call_next(request)
    
    # Log response
    process_time = 0  # TODO: Calcular tiempo real
    logger.info(f"Response: {response.status_code} - {process_time:.3f}s")
    
    return response


if __name__ == "__main__":
    # Configuración para desarrollo
    settings = get_settings()
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.is_development,
        log_level="info",
        access_log=True
    )
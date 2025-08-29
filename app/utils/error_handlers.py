"""
Manejo centralizado de errores para el sistema MOP PDF Analyzer.
"""

import logging
import traceback
from typing import Dict, Any, Optional, List
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class ErrorType(Enum):
    """Tipos de errores del sistema."""
    VALIDATION_ERROR = "validation_error"
    FILE_ERROR = "file_error"
    PDF_PROCESSING_ERROR = "pdf_processing_error"
    AI_ANALYSIS_ERROR = "ai_analysis_error"
    RATE_LIMIT_ERROR = "rate_limit_error"
    SYSTEM_ERROR = "system_error"
    TIMEOUT_ERROR = "timeout_error"


class MOPAnalysisError(Exception):
    """Excepción personalizada para errores de análisis MOP."""
    
    def __init__(
        self,
        message: str,
        error_type: ErrorType = ErrorType.SYSTEM_ERROR,
        details: Optional[Dict[str, Any]] = None,
        user_message: Optional[str] = None
    ):
        super().__init__(message)
        self.error_type = error_type
        self.details = details or {}
        self.user_message = user_message or message
        self.timestamp = datetime.now()


# === CÓDIGOS DE ERROR ESTÁNDAR ===
ERROR_CODES = {
    "INVALID_FORMAT": {
        "code": "E001",
        "message": "Solo archivos PDF válidos son aceptados",
        "user_message": "Por favor, suba un archivo PDF válido"
    },
    "FILE_TOO_LARGE": {
        "code": "E002",  
        "message": "Archivo excede el tamaño máximo permitido",
        "user_message": "El archivo es demasiado grande. Máximo permitido: 20MB"
    },
    "FILE_CORRUPTED": {
        "code": "E003",
        "message": "El archivo PDF está corrupto o no se puede leer",
        "user_message": "El archivo PDF parece estar dañado. Intente con otro archivo"
    },
    "NO_EXTRACTABLE_CONTENT": {
        "code": "E004",
        "message": "No se pudo extraer contenido del PDF",
        "user_message": "No se encontró contenido extraíble en el PDF. Verifique que no sea solo imágenes"
    },
    "NO_BUDGET_DATA": {
        "code": "E005",
        "message": "No se encontraron datos presupuestarios en el documento",
        "user_message": "El documento no contiene información presupuestaria reconocible"
    },
    "AI_API_ERROR": {
        "code": "E006",
        "message": "Error en el servicio de análisis de IA", 
        "user_message": "Error temporal en el análisis. Intente nuevamente en unos minutos"
    },
    "RATE_LIMIT": {
        "code": "E007",
        "message": "Límite de solicitudes alcanzado",
        "user_message": "Ha alcanzado el límite de análisis por minuto. Intente nuevamente en unos momentos"
    },
    "PROCESSING_TIMEOUT": {
        "code": "E008",
        "message": "El procesamiento del documento excedió el tiempo límite",
        "user_message": "El documento es demasiado complejo. Intente con un archivo más pequeño"
    },
    "INVALID_MOP_DOCUMENT": {
        "code": "E009",
        "message": "El documento no parece ser una licitación MOP válida",
        "user_message": "El documento no contiene el formato esperado de licitación MOP"
    },
    "SYSTEM_OVERLOAD": {
        "code": "E010",
        "message": "Sistema temporalmente sobrecargado",
        "user_message": "El sistema está ocupado. Intente nuevamente en unos minutos"
    }
}


def get_error_info(error_code: str) -> Dict[str, str]:
    """Obtiene información de un código de error."""
    return ERROR_CODES.get(error_code, {
        "code": "E999",
        "message": "Error desconocido",
        "user_message": "Ha ocurrido un error inesperado"
    })


def handle_processing_error(
    error: Exception,
    context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Maneja errores durante el procesamiento y retorna respuesta estructurada.
    
    Args:
        error: Excepción ocurrida
        context: Contexto adicional del error
        
    Returns:
        Dict con información estructurada del error
    """
    context = context or {}
    
    # Log del error completo
    logger.error(f"Error en procesamiento: {error}", exc_info=True)
    
    # Determinar tipo de error y código
    if isinstance(error, MOPAnalysisError):
        error_info = {
            "error_type": error.error_type.value,
            "code": f"CUSTOM_{error.error_type.value.upper()}",
            "message": error.user_message,
            "details": error.details,
            "timestamp": error.timestamp.isoformat()
        }
    else:
        # Mapear errores comunes a códigos específicos
        error_code = _classify_error(error)
        error_info_data = get_error_info(error_code)
        
        error_info = {
            "error_type": "system_error",
            "code": error_info_data["code"],
            "message": error_info_data["user_message"],
            "details": {
                "internal_message": str(error),
                "error_class": error.__class__.__name__,
                "traceback": traceback.format_exc() if context.get("include_traceback", False) else None
            },
            "timestamp": datetime.now().isoformat()
        }
    
    # Añadir contexto
    if context:
        error_info["context"] = context
    
    return error_info


def _classify_error(error: Exception) -> str:
    """Clasifica una excepción en un código de error conocido."""
    error_str = str(error).lower()
    error_class = error.__class__.__name__.lower()
    
    # Errores de archivo
    if "file" in error_str and ("not found" in error_str or "no such file" in error_str):
        return "FILE_CORRUPTED"
    
    if "too large" in error_str or "size" in error_str:
        return "FILE_TOO_LARGE"
        
    if "pdf" in error_str and ("invalid" in error_str or "corrupt" in error_str):
        return "FILE_CORRUPTED"
    
    # Errores de contenido
    if "no content" in error_str or "empty" in error_str:
        return "NO_EXTRACTABLE_CONTENT"
        
    if "budget" in error_str or "presupuesto" in error_str:
        return "NO_BUDGET_DATA"
    
    # Errores de API
    if "anthropic" in error_str or "api" in error_str:
        return "AI_API_ERROR"
        
    if "rate" in error_str and "limit" in error_str:
        return "RATE_LIMIT"
    
    # Errores de tiempo
    if "timeout" in error_str or "timed out" in error_str:
        return "PROCESSING_TIMEOUT"
    
    # Errores de validación
    if "validation" in error_str or "invalid" in error_str:
        return "INVALID_FORMAT"
    
    # Error genérico
    return "SYSTEM_ERROR"


def create_error_response(
    error: Exception,
    analysis_id: Optional[str] = None,
    include_details: bool = False
) -> Dict[str, Any]:
    """
    Crea una respuesta de error estructurada para la API.
    
    Args:
        error: Excepción ocurrida
        analysis_id: ID del análisis si aplica
        include_details: Si incluir detalles técnicos
        
    Returns:
        Dict con respuesta de error para la API
    """
    error_info = handle_processing_error(
        error, 
        {"include_traceback": include_details}
    )
    
    response = {
        "error": True,
        "error_code": error_info["code"],
        "message": error_info["message"],
        "timestamp": error_info["timestamp"]
    }
    
    if analysis_id:
        response["analysisId"] = analysis_id
    
    if include_details and error_info.get("details"):
        response["details"] = error_info["details"]
    
    return response


class ErrorTracker:
    """Rastreador de errores para estadísticas y monitoreo."""
    
    def __init__(self):
        self.error_counts = {}
        self.recent_errors = []
        self.max_recent_errors = 100
    
    def track_error(self, error: Exception, context: Optional[Dict] = None):
        """Registra un error para estadísticas."""
        error_code = _classify_error(error)
        
        # Contar errores por tipo
        self.error_counts[error_code] = self.error_counts.get(error_code, 0) + 1
        
        # Mantener errores recientes
        error_entry = {
            "timestamp": datetime.now().isoformat(),
            "error_code": error_code,
            "message": str(error),
            "context": context
        }
        
        self.recent_errors.append(error_entry)
        
        # Mantener solo los más recientes
        if len(self.recent_errors) > self.max_recent_errors:
            self.recent_errors = self.recent_errors[-self.max_recent_errors:]
    
    def get_error_stats(self) -> Dict[str, Any]:
        """Obtiene estadísticas de errores."""
        return {
            "error_counts": self.error_counts.copy(),
            "total_errors": sum(self.error_counts.values()),
            "recent_error_count": len(self.recent_errors),
            "most_common_errors": sorted(
                self.error_counts.items(), 
                key=lambda x: x[1], 
                reverse=True
            )[:5]
        }
    
    def get_recent_errors(self, limit: int = 10) -> List[Dict]:
        """Obtiene errores recientes."""
        return self.recent_errors[-limit:]


# Instancia global del tracker
error_tracker = ErrorTracker()


def log_analysis_error(
    error: Exception,
    analysis_id: str,
    stage: str,
    additional_context: Optional[Dict] = None
):
    """
    Log específico para errores de análisis con contexto completo.
    
    Args:
        error: Excepción ocurrida
        analysis_id: ID del análisis
        stage: Etapa donde ocurrió el error
        additional_context: Contexto adicional
    """
    context = {
        "analysis_id": analysis_id,
        "stage": stage,
        "timestamp": datetime.now().isoformat()
    }
    
    if additional_context:
        context.update(additional_context)
    
    # Registrar en el tracker
    error_tracker.track_error(error, context)
    
    # Log detallado
    logger.error(
        f"Error en análisis {analysis_id} durante {stage}: {error}",
        extra={"context": context},
        exc_info=True
    )


def validate_analysis_input(
    file_content: bytes,
    filename: str,
    max_size: int
) -> Optional[MOPAnalysisError]:
    """
    Valida la entrada de un análisis y retorna error si hay problemas.
    
    Args:
        file_content: Contenido del archivo
        filename: Nombre del archivo
        max_size: Tamaño máximo permitido
        
    Returns:
        MOPAnalysisError si hay error, None si está OK
    """
    # Validar extensión
    if not filename.lower().endswith('.pdf'):
        return MOPAnalysisError(
            "Solo archivos PDF son aceptados",
            ErrorType.VALIDATION_ERROR,
            {"filename": filename},
            "Por favor, suba un archivo PDF válido"
        )
    
    # Validar tamaño
    if len(file_content) > max_size:
        return MOPAnalysisError(
            f"Archivo excede tamaño máximo: {len(file_content)} > {max_size}",
            ErrorType.FILE_ERROR,
            {"file_size": len(file_content), "max_size": max_size},
            f"El archivo es demasiado grande. Máximo: {max_size // (1024*1024)}MB"
        )
    
    # Validar que no esté vacío
    if len(file_content) == 0:
        return MOPAnalysisError(
            "El archivo está vacío",
            ErrorType.FILE_ERROR,
            {"file_size": 0},
            "El archivo está vacío o no se pudo leer"
        )
    
    # Validar header PDF básico
    if not file_content.startswith(b'%PDF-'):
        return MOPAnalysisError(
            "El archivo no tiene formato PDF válido",
            ErrorType.FILE_ERROR,
            {"header": file_content[:10].hex()},
            "El archivo no parece ser un PDF válido"
        )
    
    return None


# Decorador para manejo automático de errores
def handle_errors(include_traceback: bool = False):
    """
    Decorador para manejo automático de errores en funciones.
    
    Args:
        include_traceback: Si incluir traceback en la respuesta
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                # Log del error
                logger.error(f"Error en {func.__name__}: {e}", exc_info=True)
                
                # Retornar respuesta de error
                return create_error_response(e, include_details=include_traceback)
        
        return wrapper
    return decorator


if __name__ == "__main__":
    # Test básico del sistema de errores
    print("Testing error handling system...")
    
    # Test clasificación de errores
    test_errors = [
        FileNotFoundError("File not found"),
        ValueError("Invalid PDF format"),
        Exception("Anthropic API error"),
        TimeoutError("Request timed out")
    ]
    
    for error in test_errors:
        code = _classify_error(error)
        info = get_error_info(code)
        print(f"Error: {error} -> Code: {code} -> Message: {info['user_message']}")
    
    # Test tracker
    for error in test_errors:
        error_tracker.track_error(error)
    
    stats = error_tracker.get_error_stats()
    print(f"Error stats: {stats}")
    
    print("✓ Error handling system working correctly!")
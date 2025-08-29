"""
Utilidades para manejo de archivos en el sistema MOP PDF Analyzer.
"""

import os
import aiofiles
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any
import hashlib
import magic
import logging

from app.config.settings import get_settings

logger = logging.getLogger(__name__)


async def save_temp_file(content: bytes, analysis_id: str, extension: str = ".pdf") -> str:
    """
    Guarda un archivo en el directorio temporal.
    
    Args:
        content: Contenido del archivo en bytes
        analysis_id: ID único para el archivo
        extension: Extensión del archivo
        
    Returns:
        str: Ruta completa del archivo guardado
    """
    settings = get_settings()
    
    # Crear directorio temporal si no existe
    temp_dir = Path(settings.TEMP_STORAGE_PATH)
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    # Nombre del archivo con timestamp para evitar conflictos
    filename = f"{analysis_id}{extension}"
    file_path = temp_dir / filename
    
    try:
        async with aiofiles.open(file_path, 'wb') as f:
            await f.write(content)
        
        logger.info(f"Archivo temporal guardado: {file_path}")
        return str(file_path)
        
    except Exception as e:
        logger.error(f"Error guardando archivo temporal: {e}")
        raise


async def cleanup_temp_file(analysis_id: str) -> bool:
    """
    Limpia archivos temporales asociados a un análisis.
    
    Args:
        analysis_id: ID del análisis
        
    Returns:
        bool: True si se limpiaron archivos, False si no había nada que limpiar
    """
    settings = get_settings()
    temp_dir = Path(settings.TEMP_STORAGE_PATH)
    
    cleaned = False
    
    # Buscar archivos que empiecen con el analysis_id
    if temp_dir.exists():
        for file_path in temp_dir.glob(f"{analysis_id}*"):
            try:
                file_path.unlink()
                logger.info(f"Archivo temporal eliminado: {file_path}")
                cleaned = True
            except Exception as e:
                logger.warning(f"Error eliminando archivo temporal {file_path}: {e}")
    
    return cleaned


async def validate_pdf_file(content: bytes) -> bool:
    """
    Valida que el contenido sea un PDF válido.
    
    Args:
        content: Contenido del archivo en bytes
        
    Returns:
        bool: True si es un PDF válido
    """
    try:
        # Verificar header PDF
        if not content.startswith(b'%PDF-'):
            return False
        
        # Verificar que tenga contenido mínimo
        if len(content) < 1024:  # PDF mínimo debe tener al menos 1KB
            return False
        
        # Intentar detectar tipo MIME si python-magic está disponible
        try:
            mime_type = magic.from_buffer(content, mime=True)
            if mime_type != 'application/pdf':
                logger.warning(f"MIME type detectado: {mime_type}, esperado: application/pdf")
                return False
        except Exception:
            # Si python-magic no está disponible, continuar con validación básica
            pass
        
        return True
        
    except Exception as e:
        logger.error(f"Error validando PDF: {e}")
        return False


def calculate_file_hash(content: bytes) -> str:
    """
    Calcula hash SHA-256 de un archivo.
    
    Args:
        content: Contenido del archivo
        
    Returns:
        str: Hash SHA-256 en hexadecimal
    """
    return hashlib.sha256(content).hexdigest()


async def save_processed_file(
    content: bytes, 
    analysis_id: str, 
    filename: str,
    metadata: Optional[Dict[str, Any]] = None
) -> str:
    """
    Guarda un archivo procesado en el directorio de archivos procesados.
    
    Args:
        content: Contenido del archivo
        analysis_id: ID del análisis
        filename: Nombre original del archivo
        metadata: Metadatos adicionales
        
    Returns:
        str: Ruta del archivo guardado
    """
    settings = get_settings()
    
    # Crear directorio si no existe
    processed_dir = Path(settings.PROCESSED_STORAGE_PATH)
    processed_dir.mkdir(parents=True, exist_ok=True)
    
    # Estructura: processed/YYYY/MM/analysis_id_filename
    from datetime import datetime
    now = datetime.now()
    date_dir = processed_dir / str(now.year) / f"{now.month:02d}"
    date_dir.mkdir(parents=True, exist_ok=True)
    
    # Limpiar nombre de archivo
    safe_filename = "".join(c for c in filename if c.isalnum() or c in "._-")
    file_path = date_dir / f"{analysis_id}_{safe_filename}"
    
    try:
        async with aiofiles.open(file_path, 'wb') as f:
            await f.write(content)
        
        # Guardar metadata si se proporciona
        if metadata:
            metadata_path = file_path.with_suffix('.meta.json')
            import json
            async with aiofiles.open(metadata_path, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(metadata, ensure_ascii=False, indent=2))
        
        logger.info(f"Archivo procesado guardado: {file_path}")
        return str(file_path)
        
    except Exception as e:
        logger.error(f"Error guardando archivo procesado: {e}")
        raise


async def save_analysis_result(analysis_id: str, result: Dict[str, Any]) -> str:
    """
    Guarda el resultado de un análisis en formato JSON.
    
    Args:
        analysis_id: ID del análisis
        result: Resultado del análisis
        
    Returns:
        str: Ruta del archivo de resultado
    """
    settings = get_settings()
    
    # Crear directorio si no existe
    results_dir = Path(settings.RESULTS_STORAGE_PATH)
    results_dir.mkdir(parents=True, exist_ok=True)
    
    # Estructura por fecha
    from datetime import datetime
    now = datetime.now()
    date_dir = results_dir / str(now.year) / f"{now.month:02d}"
    date_dir.mkdir(parents=True, exist_ok=True)
    
    result_path = date_dir / f"{analysis_id}_result.json"
    
    try:
        import json
        async with aiofiles.open(result_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(result, ensure_ascii=False, indent=2))
        
        logger.info(f"Resultado guardado: {result_path}")
        return str(result_path)
        
    except Exception as e:
        logger.error(f"Error guardando resultado: {e}")
        raise


async def load_analysis_result(analysis_id: str) -> Optional[Dict[str, Any]]:
    """
    Carga el resultado de un análisis desde archivo.
    
    Args:
        analysis_id: ID del análisis
        
    Returns:
        Dict con el resultado o None si no se encuentra
    """
    settings = get_settings()
    results_dir = Path(settings.RESULTS_STORAGE_PATH)
    
    # Buscar en directorios de fecha (últimos 6 meses)
    from datetime import datetime, timedelta
    now = datetime.now()
    
    for months_back in range(6):
        check_date = now - timedelta(days=months_back * 30)
        date_dir = results_dir / str(check_date.year) / f"{check_date.month:02d}"
        result_path = date_dir / f"{analysis_id}_result.json"
        
        if result_path.exists():
            try:
                import json
                async with aiofiles.open(result_path, 'r', encoding='utf-8') as f:
                    content = await f.read()
                    return json.loads(content)
            except Exception as e:
                logger.error(f"Error cargando resultado {result_path}: {e}")
                continue
    
    return None


async def cleanup_old_files(days_old: int = 7) -> Dict[str, int]:
    """
    Limpia archivos antiguos del sistema.
    
    Args:
        days_old: Edad en días para considerar archivos como antiguos
        
    Returns:
        Dict con estadísticas de limpieza
    """
    settings = get_settings()
    
    from datetime import datetime, timedelta
    cutoff_date = datetime.now() - timedelta(days=days_old)
    
    stats = {
        "temp_files_deleted": 0,
        "processed_files_deleted": 0,
        "result_files_deleted": 0,
        "errors": 0
    }
    
    # Limpiar archivos temporales
    temp_dir = Path(settings.TEMP_STORAGE_PATH)
    if temp_dir.exists():
        for file_path in temp_dir.iterdir():
            try:
                if file_path.is_file() and file_path.stat().st_mtime < cutoff_date.timestamp():
                    file_path.unlink()
                    stats["temp_files_deleted"] += 1
            except Exception as e:
                logger.warning(f"Error eliminando archivo temporal {file_path}: {e}")
                stats["errors"] += 1
    
    # Limpiar archivos procesados antiguos
    processed_dir = Path(settings.PROCESSED_STORAGE_PATH)
    if processed_dir.exists():
        for file_path in processed_dir.rglob("*"):
            try:
                if (file_path.is_file() and 
                    file_path.stat().st_mtime < cutoff_date.timestamp() and
                    not file_path.name.startswith(".")):
                    file_path.unlink()
                    stats["processed_files_deleted"] += 1
            except Exception as e:
                logger.warning(f"Error eliminando archivo procesado {file_path}: {e}")
                stats["errors"] += 1
    
    # Limpiar resultados antiguos
    results_dir = Path(settings.RESULTS_STORAGE_PATH)
    if results_dir.exists():
        for file_path in results_dir.rglob("*.json"):
            try:
                if file_path.stat().st_mtime < cutoff_date.timestamp():
                    file_path.unlink()
                    stats["result_files_deleted"] += 1
            except Exception as e:
                logger.warning(f"Error eliminando resultado {file_path}: {e}")
                stats["errors"] += 1
    
    logger.info(f"Limpieza completada: {stats}")
    return stats


def get_file_info(file_path: str) -> Dict[str, Any]:
    """
    Obtiene información detallada de un archivo.
    
    Args:
        file_path: Ruta al archivo
        
    Returns:
        Dict con información del archivo
    """
    try:
        path = Path(file_path)
        if not path.exists():
            return {"exists": False}
        
        stat = path.stat()
        
        return {
            "exists": True,
            "size_bytes": stat.st_size,
            "size_mb": round(stat.st_size / (1024 * 1024), 2),
            "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "extension": path.suffix,
            "name": path.name,
            "parent": str(path.parent)
        }
        
    except Exception as e:
        logger.error(f"Error obteniendo info de archivo {file_path}: {e}")
        return {"exists": False, "error": str(e)}


async def ensure_directories():
    """
    Asegura que todos los directorios necesarios existan.
    """
    settings = get_settings()
    
    directories = [
        settings.TEMP_STORAGE_PATH,
        settings.PROCESSED_STORAGE_PATH,
        settings.RESULTS_STORAGE_PATH
    ]
    
    for dir_path in directories:
        Path(dir_path).mkdir(parents=True, exist_ok=True)
        logger.debug(f"Directorio asegurado: {dir_path}")


if __name__ == "__main__":
    # Test básico
    import asyncio
    
    async def test_file_utils():
        print("Testing file utilities...")
        
        # Asegurar directorios
        await ensure_directories()
        print("✓ Directories ensured")
        
        # Test archivo temporal
        test_content = b"Test PDF content"
        temp_path = await save_temp_file(test_content, "test123", ".pdf")
        print(f"✓ Temp file saved: {temp_path}")
        
        # Test info archivo
        info = get_file_info(temp_path)
        print(f"✓ File info: {info['size_bytes']} bytes")
        
        # Test limpieza
        cleaned = await cleanup_temp_file("test123")
        print(f"✓ Cleanup: {cleaned}")
        
        print("All tests passed!")
    
    asyncio.run(test_file_utils())
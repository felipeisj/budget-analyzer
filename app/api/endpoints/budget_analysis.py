"""
Endpoints principales para análisis de presupuestos MOP.
"""

import asyncio
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

import aiofiles
from fastapi import APIRouter, File, UploadFile, HTTPException, Form, BackgroundTasks
from fastapi.responses import JSONResponse

from app.config.settings import get_settings
from app.services.pdf_extractor import extract_pdf_content
from app.services.claude_analyzer import analyze_mop_document
from app.utils.file_utils import save_temp_file, cleanup_temp_file, validate_pdf_file
from app.utils.error_handlers import handle_processing_error

import logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/budget-analysis", tags=["Budget Analysis"])

# Store para resultados (en producción usar Redis/DB)
analysis_results = {}


@router.post("/pdf")
async def analyze_pdf(
    background_tasks: BackgroundTasks,
    pdfFile: UploadFile = File(...),
    analysisDepth: str = Form("full"),
    projectType: Optional[str] = Form(None), 
    projectLocation: Optional[str] = Form(None)
):
    """
    Endpoint principal para análisis de PDFs MOP.
    
    Args:
        pdfFile: Archivo PDF a analizar
        analysisDepth: Profundidad del análisis ("full", "quick", "budget_only")
        projectType: Tipo de proyecto (opcional)
        projectLocation: Ubicación del proyecto (opcional)
    
    Returns:
        JSON con analysisId y estado del procesamiento
    """
    settings = get_settings()
    analysis_id = str(uuid.uuid4())
    
    logger.info(f"Iniciando análisis PDF - ID: {analysis_id}")
    
    try:
        # 1. Validaciones iniciales
        if not pdfFile.filename.lower().endswith('.pdf'):
            raise HTTPException(
                status_code=400,
                detail="Solo se aceptan archivos PDF"
            )
        
        # Leer contenido del archivo
        content = await pdfFile.read()
        
        if len(content) > settings.MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"Archivo demasiado grande. Máximo: {settings.max_file_size_mb:.1f}MB"
            )
        
        if len(content) == 0:
            raise HTTPException(
                status_code=400,
                detail="El archivo está vacío"
            )
        
        # 2. Validar que es un PDF válido
        if not await validate_pdf_file(content):
            raise HTTPException(
                status_code=400,
                detail="El archivo no es un PDF válido o está corrupto"
            )
        
        # 3. Guardar archivo temporal
        temp_file_path = await save_temp_file(content, analysis_id, ".pdf")
        
        # 4. Registrar análisis como "procesando"
        analysis_results[analysis_id] = {
            "status": "processing",
            "created_at": datetime.now().isoformat(),
            "filename": pdfFile.filename,
            "file_size": len(content),
            "analysis_depth": analysisDepth,
            "project_type": projectType,
            "project_location": projectLocation,
            "progress": 0
        }
        
        # 5. Procesar en background
        background_tasks.add_task(
            process_pdf_analysis,
            analysis_id,
            temp_file_path,
            analysisDepth,
            {
                "filename": pdfFile.filename,
                "file_size": len(content),
                "project_type": projectType,
                "project_location": projectLocation
            }
        )
        
        logger.info(f"Análisis {analysis_id} iniciado en background")
        
        return JSONResponse(
            status_code=202,
            content={
                "analysisId": analysis_id,
                "status": "processing",
                "message": "Análisis iniciado. Use el analysisId para consultar el estado.",
                "estimatedTime": "2-5 minutos"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error iniciando análisis: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error interno del servidor: {str(e)}"
        )


@router.get("/pdf/{analysis_id}")
async def get_analysis_result(analysis_id: str):
    """
    Obtiene el resultado de un análisis por ID.
    
    Args:
        analysis_id: ID del análisis
        
    Returns:
        JSON con el resultado del análisis o estado actual
    """
    if analysis_id not in analysis_results:
        raise HTTPException(
            status_code=404,
            detail="Análisis no encontrado"
        )
    
    result = analysis_results[analysis_id]
    
    if result["status"] == "processing":
        return JSONResponse(
            status_code=202,
            content={
                "analysisId": analysis_id,
                "status": "processing",
                "progress": result.get("progress", 0),
                "message": "Análisis en progreso..."
            }
        )
    
    elif result["status"] == "completed":
        return JSONResponse(
            status_code=200,
            content=result["data"]
        )
    
    elif result["status"] == "error":
        return JSONResponse(
            status_code=500,
            content={
                "analysisId": analysis_id,
                "status": "error",
                "error": result.get("error", "Error desconocido"),
                "message": "Error durante el procesamiento"
            }
        )
    
    else:
        raise HTTPException(
            status_code=500,
            detail="Estado de análisis desconocido"
        )


@router.delete("/pdf/{analysis_id}")
async def delete_analysis_result(analysis_id: str):
    """
    Elimina un resultado de análisis.
    
    Args:
        analysis_id: ID del análisis a eliminar
        
    Returns:
        JSON confirmando eliminación
    """
    if analysis_id not in analysis_results:
        raise HTTPException(
            status_code=404,
            detail="Análisis no encontrado"
        )
    
    # Limpiar archivos temporales si existen
    try:
        await cleanup_temp_file(analysis_id)
    except Exception as e:
        logger.warning(f"Error limpiando archivos temporales: {e}")
    
    # Eliminar del store
    del analysis_results[analysis_id]
    
    return JSONResponse(
        status_code=200,
        content={
            "message": "Análisis eliminado correctamente",
            "analysisId": analysis_id
        }
    )


@router.get("/status")
async def get_service_status():
    """
    Estado general del servicio de análisis.
    
    Returns:
        JSON con estadísticas del servicio
    """
    total_analyses = len(analysis_results)
    processing = sum(1 for r in analysis_results.values() if r["status"] == "processing")
    completed = sum(1 for r in analysis_results.values() if r["status"] == "completed")
    errors = sum(1 for r in analysis_results.values() if r["status"] == "error")
    
    return {
        "service": "MOP Budget Analysis",
        "status": "operational",
        "statistics": {
            "total_analyses": total_analyses,
            "processing": processing,
            "completed": completed,
            "errors": errors
        },
        "settings": {
            "max_file_size_mb": get_settings().max_file_size_mb,
            "supported_formats": ["PDF"],
            "analysis_types": ["full", "quick", "budget_only"]
        }
    }


# === FUNCIONES AUXILIARES ===

async def process_pdf_analysis(
    analysis_id: str,
    pdf_path: str,
    analysis_depth: str,
    metadata: Dict[str, Any]
):
    """
    Procesa un análisis PDF en background.
    
    Args:
        analysis_id: ID único del análisis
        pdf_path: Ruta al archivo PDF temporal
        analysis_depth: Tipo de análisis
        metadata: Metadatos adicionales
    """
    try:
        logger.info(f"Iniciando procesamiento de análisis {analysis_id}")
        
        # Actualizar progreso
        analysis_results[analysis_id]["progress"] = 10
        analysis_results[analysis_id]["message"] = "Extrayendo contenido del PDF..."
        
        # 1. Extraer contenido del PDF
        extracted_content = await extract_pdf_content(pdf_path)
        
        if not extracted_content or extracted_content.get("error"):
            raise Exception(f"Error extrayendo PDF: {extracted_content.get('error', 'Error desconocido')}")
        
        # Actualizar progreso
        analysis_results[analysis_id]["progress"] = 50
        analysis_results[analysis_id]["message"] = "Analizando contenido con IA..."
        
        # 2. Analizar con Claude
        analysis_result = await analyze_mop_document(extracted_content, analysis_depth)
        
        if not analysis_result:
            raise Exception("Error en análisis con Claude")
        
        # 3. Añadir metadata adicional
        if "metadata" in analysis_result:
            analysis_result["metadata"].update({
                "original_filename": metadata.get("filename", "unknown.pdf"),
                "file_size_bytes": metadata.get("file_size", 0),
                "project_type": metadata.get("project_type"),
                "project_location": metadata.get("project_location"),
                "analysis_depth": analysis_depth
            })
        
        # 4. Marcar como completado
        analysis_results[analysis_id].update({
            "status": "completed",
            "progress": 100,
            "data": analysis_result,
            "completed_at": datetime.now().isoformat()
        })
        
        logger.info(f"Análisis {analysis_id} completado exitosamente")
        
    except Exception as e:
        logger.error(f"Error procesando análisis {analysis_id}: {e}")
        
        # Marcar como error
        analysis_results[analysis_id].update({
            "status": "error",
            "error": str(e),
            "failed_at": datetime.now().isoformat()
        })
        
    finally:
        # Limpiar archivo temporal
        try:
            await cleanup_temp_file(analysis_id)
        except Exception as e:
            logger.warning(f"Error limpiando archivo temporal: {e}")


# === ENDPOINTS DE PRUEBA Y DEBUG ===

@router.post("/test/extract-only")
async def test_extract_only(pdfFile: UploadFile = File(...)):
    """
    Endpoint de prueba para solo extraer contenido sin análisis IA.
    Útil para debug y testing.
    """
    if not pdfFile.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Solo archivos PDF")
    
    content = await pdfFile.read()
    temp_path = await save_temp_file(content, "test", ".pdf")
    
    try:
        extracted = await extract_pdf_content(temp_path)
        return {
            "filename": pdfFile.filename,
            "extraction_result": {
                "text_length": len(extracted.get("text_content", "")),
                "tables_found": len(extracted.get("tables", [])),
                "budget_items_found": len(extracted.get("budget_items", [])),
                "confidence": extracted.get("extraction_metadata", {}).get("confidence_score", 0),
                "methods_used": extracted.get("extraction_metadata", {}).get("methods_used", [])
            },
            "sample_text": extracted.get("text_content", "")[:1000] + "..." if len(extracted.get("text_content", "")) > 1000 else extracted.get("text_content", ""),
            "budget_items_sample": extracted.get("budget_items", [])[:5]
        }
    finally:
        await cleanup_temp_file("test")


# Añadir este nuevo endpoint al final de app/api/endpoints/budget_analysis.py

@router.post("/pdf/multiple")
async def analyze_multiple_pdfs(
    background_tasks: BackgroundTasks,
    pdfFiles: List[UploadFile] = File(...),
    analysisDepth: str = Form("full"),
    projectType: Optional[str] = Form(None), 
    projectLocation: Optional[str] = Form(None)
):
    """
    Endpoint para análisis de múltiples PDFs MOP (proyecto completo).
    
    Args:
        pdfFiles: Lista de archivos PDF a analizar
        analysisDepth: Profundidad del análisis ("full", "quick", "budget_only")
        projectType: Tipo de proyecto (opcional)
        projectLocation: Ubicación del proyecto (opcional)
    
    Returns:
        JSON con analysisId y estado del procesamiento
    """
    settings = get_settings()
    analysis_id = str(uuid.uuid4())
    
    logger.info(f"Iniciando análisis de múltiples PDFs - ID: {analysis_id}, Archivos: {len(pdfFiles)}")
    
    try:
        # 1. Validaciones iniciales
        if not pdfFiles or len(pdfFiles) == 0:
            raise HTTPException(
                status_code=400,
                detail="Debe proporcionar al menos un archivo PDF"
            )
        
        if len(pdfFiles) > 10:  # Límite razonable
            raise HTTPException(
                status_code=400,
                detail="Máximo 10 archivos PDF por análisis"
            )
        
        # 2. Procesar cada archivo
        pdf_files_info = []
        total_size = 0
        
        for idx, pdf_file in enumerate(pdfFiles):
            # Validar extensión
            if not pdf_file.filename.lower().endswith('.pdf'):
                raise HTTPException(
                    status_code=400,
                    detail=f"Archivo {idx + 1} ({pdf_file.filename}): Solo se aceptan archivos PDF"
                )
            
            # Leer contenido
            content = await pdf_file.read()
            total_size += len(content)
            
            if len(content) == 0:
                raise HTTPException(
                    status_code=400,
                    detail=f"Archivo {idx + 1} ({pdf_file.filename}): El archivo está vacío"
                )
            
            # Validar PDF
            if not await validate_pdf_file(content):
                raise HTTPException(
                    status_code=400,
                    detail=f"Archivo {idx + 1} ({pdf_file.filename}): No es un PDF válido o está corrupto"
                )
            
            # Guardar archivo temporal
            temp_file_path = await save_temp_file(content, f"{analysis_id}_{idx}", ".pdf")
            
            pdf_files_info.append({
                "index": idx,
                "filename": pdf_file.filename,
                "size": len(content),
                "temp_path": temp_file_path
            })
        
        # 3. Validar tamaño total
        if total_size > settings.MAX_FILE_SIZE * 3:  # Permitir hasta 3x para múltiples archivos
            raise HTTPException(
                status_code=413,
                detail=f"Tamaño total de archivos demasiado grande: {total_size / (1024*1024):.1f}MB. Máximo: {settings.max_file_size_mb * 3:.1f}MB"
            )
        
        # 4. Registrar análisis como "procesando"
        analysis_results[analysis_id] = {
            "status": "processing",
            "created_at": datetime.now().isoformat(),
            "files": [{"filename": f["filename"], "size": f["size"]} for f in pdf_files_info],
            "total_files": len(pdf_files_info),
            "total_size": total_size,
            "analysis_depth": analysisDepth,
            "project_type": projectType,
            "project_location": projectLocation,
            "progress": 0
        }
        
        # 5. Procesar en background
        background_tasks.add_task(
            process_multiple_pdfs_analysis,
            analysis_id,
            pdf_files_info,
            analysisDepth,
            {
                "total_files": len(pdf_files_info),
                "total_size": total_size,
                "project_type": projectType,
                "project_location": projectLocation
            }
        )
        
        logger.info(f"Análisis múltiple {analysis_id} iniciado en background con {len(pdf_files_info)} archivos")
        
        return JSONResponse(
            status_code=202,
            content={
                "analysisId": analysis_id,
                "status": "processing",
                "message": f"Análisis iniciado con {len(pdf_files_info)} archivos PDF. Use el analysisId para consultar el estado.",
                "files_count": len(pdf_files_info),
                "total_size_mb": round(total_size / (1024*1024), 2),
                "estimatedTime": "3-8 minutos"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error iniciando análisis múltiple: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error interno del servidor: {str(e)}"
        )


# Nueva función para procesar múltiples PDFs
async def process_multiple_pdfs_analysis(
    analysis_id: str,
    pdf_files_info: List[Dict],
    analysis_depth: str,
    metadata: Dict[str, Any]
):
    """
    Procesa múltiples PDFs en background y los combina en un análisis unificado.
    
    Args:
        analysis_id: ID único del análisis
        pdf_files_info: Lista con información de los archivos PDF
        analysis_depth: Tipo de análisis
        metadata: Metadatos adicionales
    """
    try:
        logger.info(f"Iniciando procesamiento de análisis múltiple {analysis_id} con {len(pdf_files_info)} archivos")
        
        # Actualizar progreso
        analysis_results[analysis_id]["progress"] = 5
        analysis_results[analysis_id]["message"] = "Iniciando extracción de contenido..."
        
        # 1. Extraer contenido de todos los PDFs
        all_extracted_content = []
        combined_content = {
            "text_content": "",
            "tables": [],
            "budget_items": [],
            "project_info": {},
            "totals": {},
            "extraction_metadata": {
                "methods_used": [],
                "pages_processed": 0,
                "tables_found": 0,
                "confidence_score": 0.0,
                "files_processed": len(pdf_files_info)
            },
            "raw_extractions": {}
        }
        
        progress_per_file = 40 / len(pdf_files_info)  # 40% total para extracción
        
        for idx, file_info in enumerate(pdf_files_info):
            try:
                logger.info(f"Extrayendo contenido de archivo {idx + 1}/{len(pdf_files_info)}: {file_info['filename']}")
                
                # Actualizar progreso
                current_progress = 5 + (idx * progress_per_file)
                analysis_results[analysis_id]["progress"] = int(current_progress)
                analysis_results[analysis_id]["message"] = f"Extrayendo {file_info['filename']}..."
                
                # Extraer contenido del PDF individual
                extracted = await extract_pdf_content(file_info["temp_path"])
                
                if not extracted or extracted.get("error"):
                    logger.warning(f"Error extrayendo {file_info['filename']}: {extracted.get('error', 'Error desconocido')}")
                    continue
                
                # Añadir identificador de archivo al contenido
                if extracted.get("text_content"):
                    file_header = f"\n\n=== ARCHIVO: {file_info['filename']} ===\n"
                    extracted["text_content"] = file_header + extracted["text_content"]
                
                # Añadir metadata de archivo a tablas e items
                if extracted.get("tables"):
                    for table in extracted["tables"]:
                        table["source_file"] = file_info['filename']
                
                if extracted.get("budget_items"):
                    for item in extracted["budget_items"]:
                        item["source_file"] = file_info['filename']
                
                all_extracted_content.append(extracted)
                
            except Exception as e:
                logger.error(f"Error procesando archivo {file_info['filename']}: {e}")
                continue
        
        if not all_extracted_content:
            raise Exception("No se pudo extraer contenido de ningún archivo PDF")
        
        # 2. Combinar todo el contenido extraído
        analysis_results[analysis_id]["progress"] = 45
        analysis_results[analysis_id]["message"] = "Combinando contenido extraído..."
        
        for extracted in all_extracted_content:
            # Combinar texto
            if extracted.get("text_content"):
                combined_content["text_content"] += extracted["text_content"] + "\n\n"
            
            # Combinar tablas
            if extracted.get("tables"):
                combined_content["tables"].extend(extracted["tables"])
            
            # Combinar items presupuestarios
            if extracted.get("budget_items"):
                combined_content["budget_items"].extend(extracted["budget_items"])
            
            # Combinar información del proyecto (priorizar no vacíos)
            if extracted.get("project_info"):
                for key, value in extracted["project_info"].items():
                    if value and not combined_content["project_info"].get(key):
                        combined_content["project_info"][key] = value
            
            # Combinar totales (priorizar no ceros)
            if extracted.get("totals"):
                for key, value in extracted["totals"].items():
                    if value and value > 0:
                        combined_content["totals"][key] = value
            
            # Combinar metadata
            metadata_extracted = extracted.get("extraction_metadata", {})
            combined_content["extraction_metadata"]["pages_processed"] += metadata_extracted.get("pages_processed", 0)
            combined_content["extraction_metadata"]["tables_found"] += len(extracted.get("tables", []))
            
            # Combinar métodos usados (únicos)
            methods = metadata_extracted.get("methods_used", [])
            for method in methods:
                if method not in combined_content["extraction_metadata"]["methods_used"]:
                    combined_content["extraction_metadata"]["methods_used"].append(method)
        
        # Calcular confidence score promedio
        confidence_scores = [e.get("extraction_metadata", {}).get("confidence_score", 0) for e in all_extracted_content]
        if confidence_scores:
            combined_content["extraction_metadata"]["confidence_score"] = sum(confidence_scores) / len(confidence_scores)
        
        # 3. Análizar contenido combinado con Claude
        analysis_results[analysis_id]["progress"] = 50
        analysis_results[analysis_id]["message"] = "Analizando contenido combinado con IA..."
        
        analysis_result = await analyze_mop_document(combined_content, analysis_depth)
        
        if not analysis_result:
            raise Exception("Error en análisis con Claude")
        
        # 4. Añadir metadata de análisis múltiple
        if "metadata" in analysis_result:
            analysis_result["metadata"].update({
                "files_processed": len(pdf_files_info),
                "file_names": [f["filename"] for f in pdf_files_info],
                "total_size_bytes": metadata.get("total_size", 0),
                "project_type": metadata.get("project_type"),
                "project_location": metadata.get("project_location"),
                "analysis_depth": analysis_depth,
                "analysis_type": "multiple_pdfs"
            })
        
        # Añadir resumen de archivos procesados al analysis
        analysis_result["files_summary"] = {
            "total_files": len(pdf_files_info),
            "files_processed": len(all_extracted_content),
            "files_with_budget_data": len([e for e in all_extracted_content if e.get("budget_items")]),
            "total_pages": combined_content["extraction_metadata"]["pages_processed"],
            "total_tables": len(combined_content["tables"]),
            "total_budget_items": len(combined_content["budget_items"])
        }
        
        # 5. Marcar como completado
        analysis_results[analysis_id].update({
            "status": "completed",
            "progress": 100,
            "data": analysis_result,
            "completed_at": datetime.now().isoformat()
        })
        
        logger.info(f"Análisis múltiple {analysis_id} completado exitosamente")
        
    except Exception as e:
        logger.error(f"Error procesando análisis múltiple {analysis_id}: {e}")
        
        # Marcar como error
        analysis_results[analysis_id].update({
            "status": "error",
            "error": str(e),
            "failed_at": datetime.now().isoformat()
        })
        
    finally:
        # Limpiar archivos temporales
        try:
            for file_info in pdf_files_info:
                temp_path = Path(file_info["temp_path"])
                if temp_path.exists():
                    temp_path.unlink()
                    logger.info(f"Archivo temporal eliminado: {temp_path}")
        except Exception as e:
            logger.warning(f"Error limpiando archivos temporales: {e}")


# También añadir al final del archivo, antes del if __name__ == "__main__":

@router.post("/test/multiple-extract-only")
async def test_multiple_extract_only(pdfFiles: List[UploadFile] = File(...)):
    """
    Endpoint de prueba para extraer contenido de múltiples PDFs sin análisis IA.
    Útil para debug y testing.
    """
    if not pdfFiles or len(pdfFiles) == 0:
        raise HTTPException(status_code=400, detail="Debe proporcionar al menos un archivo PDF")
    
    results = {}
    temp_files = []
    
    try:
        for idx, pdf_file in enumerate(pdfFiles):
            if not pdf_file.filename.lower().endswith('.pdf'):
                raise HTTPException(status_code=400, detail=f"Archivo {idx + 1}: Solo archivos PDF")
            
            content = await pdf_file.read()
            temp_path = await save_temp_file(content, f"test_multi_{idx}", ".pdf")
            temp_files.append(temp_path)
            
            extracted = await extract_pdf_content(temp_path)
            
            results[pdf_file.filename] = {
                "text_length": len(extracted.get("text_content", "")),
                "tables_found": len(extracted.get("tables", [])),
                "budget_items_found": len(extracted.get("budget_items", [])),
                "confidence": extracted.get("extraction_metadata", {}).get("confidence_score", 0),
                "methods_used": extracted.get("extraction_metadata", {}).get("methods_used", []),
                "sample_text": extracted.get("text_content", "")[:500] + "..." if len(extracted.get("text_content", "")) > 500 else extracted.get("text_content", "")
            }
        
        return {
            "total_files": len(pdfFiles),
            "results": results,
            "summary": {
                "total_text_length": sum(r["text_length"] for r in results.values()),
                "total_tables": sum(r["tables_found"] for r in results.values()),
                "total_budget_items": sum(r["budget_items_found"] for r in results.values()),
                "avg_confidence": sum(r["confidence"] for r in results.values()) / len(results) if results else 0
            }
        }
    
    finally:
        # Limpiar archivos temporales
        for temp_path in temp_files:
            try:
                await cleanup_temp_file(Path(temp_path).stem)
            except Exception as e:
                logger.warning(f"Error limpiando archivo temporal {temp_path}: {e}")




if __name__ == "__main__":
    print("Budget Analysis endpoints loaded successfully!")
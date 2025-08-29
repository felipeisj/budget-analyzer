#!/usr/bin/env python3
"""
Script para probar el análisis de múltiples PDFs del CCI Futrono.
"""

import requests
import json
import time
import os
from pathlib import Path
from typing import Dict, Any
import sys

# Configuración
API_BASE_URL = "http://localhost:8000"
PDF_DIRECTORY = "../docs/cci_futrono"  # Ajusta según tu estructura
PDF_FILES = ["bases1.pdf", "bases2.pdf", "bases3.pdf"]

def print_separator(title: str = ""):
    """Imprime un separador visual."""
    print("\n" + "="*80)
    if title:
        print(f" {title} ".center(80, "="))
        print("="*80)
    print()

def print_json_pretty(data: Dict[Any, Any], max_depth: int = 3, current_depth: int = 0):
    """Imprime JSON de forma legible con control de profundidad."""
    indent = "  " * current_depth
    
    if isinstance(data, dict):
        for key, value in data.items():
            if current_depth < max_depth:
                if isinstance(value, (dict, list)) and value:
                    print(f"{indent}{key}:")
                    print_json_pretty(value, max_depth, current_depth + 1)
                else:
                    print(f"{indent}{key}: {value}")
            else:
                if isinstance(value, (dict, list)):
                    print(f"{indent}{key}: [{'dict' if isinstance(value, dict) else 'list'} with {len(value)} items]")
                else:
                    print(f"{indent}{key}: {value}")
    
    elif isinstance(data, list):
        if current_depth < max_depth:
            for i, item in enumerate(data[:5]):  # Solo primeros 5 items
                print(f"{indent}[{i}]:")
                print_json_pretty(item, max_depth, current_depth + 1)
            if len(data) > 5:
                print(f"{indent}... y {len(data) - 5} items más")
        else:
            print(f"{indent}[Lista con {len(data)} elementos]")

def upload_multiple_pdfs(pdf_files: list, analysis_depth: str = "full") -> Dict:
    """
    Sube múltiples PDFs para análisis.
    
    Args:
        pdf_files: Lista de rutas a los archivos PDF
        analysis_depth: Profundidad del análisis
    
    Returns:
        Respuesta del servidor
    """
    url = f"{API_BASE_URL}/api/budget-analysis/pdf/multiple"
    
    # Preparar archivos para upload
    files = []
    for pdf_path in pdf_files:
        if not os.path.exists(pdf_path):
            print(f"❌ Error: No se encuentra el archivo {pdf_path}")
            return None
        
        file_size = os.path.getsize(pdf_path) / (1024*1024)  # MB
        print(f"📄 {os.path.basename(pdf_path)}: {file_size:.2f}MB")
        
        files.append(('pdfFiles', (os.path.basename(pdf_path), open(pdf_path, 'rb'), 'application/pdf')))
    
    # Datos del form
    data = {
        'analysisDepth': analysis_depth,
        'projectType': 'Conservación Camino Público',
        'projectLocation': 'Futrono, Los Ríos'
    }
    
    print(f"\n🚀 Enviando {len(files)} archivos al servidor...")
    print(f"📊 Análisis: {analysis_depth}")
    
    try:
        response = requests.post(url, files=files, data=data, timeout=30)
        
        # Cerrar archivos
        for _, file_tuple in files:
            file_tuple[1].close()
        
        if response.status_code == 202:
            result = response.json()
            print(f"✅ Análisis iniciado con ID: {result['analysisId']}")
            return result
        else:
            print(f"❌ Error {response.status_code}: {response.text}")
            return None
            
    except requests.exceptions.Timeout:
        print("⏰ Timeout - El servidor tardó demasiado en responder")
        return None
    except requests.exceptions.ConnectionError:
        print("🔌 Error de conexión - ¿Está el servidor ejecutándose?")
        return None
    except Exception as e:
        print(f"❌ Error inesperado: {e}")
        return None

def check_analysis_status(analysis_id: str) -> Dict:
    """
    Verifica el estado de un análisis.
    
    Args:
        analysis_id: ID del análisis
    
    Returns:
        Estado actual del análisis
    """
    url = f"{API_BASE_URL}/api/budget-analysis/pdf/{analysis_id}"
    
    try:
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            return {"status": "completed", "data": response.json()}
        elif response.status_code == 202:
            return {"status": "processing", "data": response.json()}
        else:
            return {"status": "error", "data": response.json()}
            
    except Exception as e:
        return {"status": "error", "error": str(e)}

def wait_for_completion(analysis_id: str, max_wait_minutes: int = 10):
    """
    Espera a que se complete el análisis.
    
    Args:
        analysis_id: ID del análisis
        max_wait_minutes: Tiempo máximo a esperar en minutos
    """
    max_attempts = max_wait_minutes * 6  # cada 10 segundos
    attempt = 0
    
    print(f"⏳ Esperando finalización del análisis (máx {max_wait_minutes} min)...")
    
    while attempt < max_attempts:
        status_result = check_analysis_status(analysis_id)
        
        if status_result["status"] == "completed":
            print("✅ Análisis completado!")
            return status_result["data"]
        
        elif status_result["status"] == "processing":
            progress = status_result["data"].get("progress", 0)
            print(f"🔄 Progreso: {progress}% - {status_result['data'].get('message', 'Procesando...')}")
            
        elif status_result["status"] == "error":
            print(f"❌ Error en el análisis: {status_result['data'].get('error', 'Error desconocido')}")
            return None
        
        time.sleep(10)
        attempt += 1
    
    print(f"⏰ Timeout - El análisis no se completó en {max_wait_minutes} minutos")
    return None

def display_analysis_results(result: Dict):
    """Muestra los resultados del análisis de forma organizada."""
    
    print_separator("INFORMACIÓN GENERAL")
    print(f"🆔 Analysis ID: {result.get('analysisId', 'N/A')}")
    
    # Metadata
    if 'metadata' in result:
        metadata = result['metadata']
        print(f"📁 Archivos procesados: {metadata.get('files_processed', 'N/A')}")
        print(f"📄 Nombres: {', '.join(metadata.get('file_names', []))}")
        print(f"💾 Tamaño total: {metadata.get('total_size_bytes', 0) / (1024*1024):.1f}MB")
        print(f"⏱️ Tiempo de procesamiento: {metadata.get('processingTime', 'N/A')}")
        print(f"🎯 Confianza: {metadata.get('confidence_score', 0):.2f}")
    
    # Resumen de archivos
    if 'files_summary' in result:
        summary = result['files_summary']
        print_separator("RESUMEN DE ARCHIVOS")
        print(f"📊 Total archivos: {summary.get('total_files', 0)}")
        print(f"✅ Archivos procesados: {summary.get('files_processed', 0)}")
        print(f"💰 Archivos con datos presupuestarios: {summary.get('files_with_budget_data', 0)}")
        print(f"📄 Total páginas: {summary.get('total_pages', 0)}")
        print(f"📋 Total tablas: {summary.get('total_tables', 0)}")
        print(f"🔢 Total items presupuestarios: {summary.get('total_budget_items', 0)}")
    
    # Análisis principal
    if 'analysis' in result:
        analysis = result['analysis']
        
        print_separator("RESUMEN EJECUTIVO")
        print(analysis.get('resumen_ejecutivo', 'No disponible'))
        
        # Presupuesto
        if 'presupuesto_estimado' in analysis:
            presupuesto = analysis['presupuesto_estimado']
            print_separator("PRESUPUESTO ESTIMADO")
            print(f"💰 Total: ${presupuesto.get('total_clp', 0):,.0f} CLP")
            print(f"🧱 Materiales: {presupuesto.get('materials_percentage', 0):.1f}%")
            print(f"👷 Mano de obra: {presupuesto.get('labor_percentage', 0):.1f}%")
            print(f"🚜 Equipos: {presupuesto.get('equipment_percentage', 0):.1f}%")
            print(f"📊 Gastos generales: {presupuesto.get('overhead_percentage', 0):.1f}%")
        
        # Materiales detallados (primeros 5)
        if 'materiales_detallados' in analysis and analysis['materiales_detallados']:
            print_separator("MATERIALES PRINCIPALES")
            for i, material in enumerate(analysis['materiales_detallados'][:5]):
                print(f"{i+1}. {material.get('descripcion', 'N/A')}")
                print(f"   💰 Costo: ${material.get('costo_estimado_clp', 0):,.0f}")
                print(f"   🏪 Proveedor: {material.get('proveedor_sugerido', 'N/A')}")
        
        # Riesgos (primeros 3)
        if 'analisis_riesgos' in analysis and analysis['analisis_riesgos']:
            print_separator("PRINCIPALES RIESGOS")
            for i, riesgo in enumerate(analysis['analisis_riesgos'][:3]):
                print(f"{i+1}. {riesgo.get('descripcion', 'N/A')}")
                print(f"   ⚠️ Probabilidad: {riesgo.get('probabilidad', 'N/A').upper()}")
                print(f"   💥 Impacto: {riesgo.get('impacto', 'N/A').upper()}")
                print(f"   🛡️ Mitigación: {riesgo.get('medida_mitigacion', 'N/A')}")
        
        # Recomendaciones (primeras 3)
        if 'recomendaciones' in analysis and analysis['recomendaciones']:
            print_separator("PRINCIPALES RECOMENDACIONES")
            for i, rec in enumerate(analysis['recomendaciones'][:3]):
                print(f"{i+1}. {rec.get('recomendacion', 'N/A')}")
                print(f"   🎯 Categoría: {rec.get('categoria', 'N/A')}")
                print(f"   🔥 Prioridad: {rec.get('prioridad', 'N/A').upper()}")
                print(f"   📋 Justificación: {rec.get('justificacion', 'N/A')}")

def save_full_results(result: Dict, filename: str = "analysis_results.json"):
    """Guarda los resultados completos en un archivo JSON."""
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"💾 Resultados completos guardados en: {filename}")
    except Exception as e:
        print(f"❌ Error guardando archivo: {e}")

def main():
    """Función principal del script."""
    print_separator("ANALIZADOR DE MÚLTIPLES PDFs MOP")
    print("🎯 Proyecto: CCI Futrono y Lago Ranco")
    
    # Verificar que el servidor esté ejecutándose
    try:
        response = requests.get(f"{API_BASE_URL}/health", timeout=5)
        if response.status_code != 200:
            print("❌ El servidor no está respondiendo correctamente")
            return
        print("✅ Servidor conectado y funcionando")
    except:
        print("❌ No se puede conectar al servidor. ¿Está ejecutándose en localhost:8000?")
        return
    
    # Construir rutas completas de los archivos
    pdf_paths = []
    for filename in PDF_FILES:
        full_path = os.path.join(PDF_DIRECTORY, filename)
        if os.path.exists(full_path):
            pdf_paths.append(full_path)
        else:
            print(f"❌ No se encuentra: {full_path}")
            return
    
    print(f"📁 Directorio: {PDF_DIRECTORY}")
    print(f"📄 Archivos encontrados: {len(pdf_paths)}")
    
    # Subir archivos
    upload_result = upload_multiple_pdfs(pdf_paths, "full")
    if not upload_result:
        return
    
    analysis_id = upload_result['analysisId']
    
    # Esperar y obtener resultados
    final_result = wait_for_completion(analysis_id, max_wait_minutes=10)
    if not final_result:
        print("❌ No se pudieron obtener los resultados")
        return
    
    # Mostrar resultados
    display_analysis_results(final_result)
    
    # Guardar resultados completos
    save_full_results(final_result, f"cci_futrono_analysis_{analysis_id[:8]}.json")
    
    print_separator("ANÁLISIS COMPLETADO")
    print("🎉 ¡Análisis finalizado exitosamente!")
    print(f"📋 ID del análisis: {analysis_id}")

if __name__ == "__main__":
    main()
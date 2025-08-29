#!/usr/bin/env python3
"""
Script para visualizar archivos JSON de resultados de análisis MOP.
"""

import json
import sys
import os
from pathlib import Path
from typing import Dict, Any, List

def print_separator(title: str = "", char: str = "=", width: int = 80):
    """Imprime un separador visual."""
    print("\n" + char * width)
    if title:
        print(f" {title} ".center(width, char))
        print(char * width)
    print()

def format_currency(amount: float) -> str:
    """Formatea un monto en pesos chilenos."""
    if amount == 0:
        return "$0"
    return f"${amount:,.0f}".replace(",", ".")

def display_project_summary(analysis: Dict):
    """Muestra resumen del proyecto."""
    print("🏗️  INFORMACIÓN DEL PROYECTO")
    print("-" * 40)
    print(f"📋 Resumen: {analysis.get('resumen_ejecutivo', 'No disponible')}")
    print(f"📅 Cronograma: {analysis.get('cronograma_estimado', 'No especificado')}")

def display_budget_summary(presupuesto: Dict):
    """Muestra resumen presupuestario."""
    print("💰 PRESUPUESTO ESTIMADO")
    print("-" * 40)
    total = presupuesto.get('total_clp', 0)
    print(f"💵 TOTAL: {format_currency(total)} CLP")
    
    if total > 0:
        print(f"🧱 Materiales: {presupuesto.get('materials_percentage', 0):.1f}% ({format_currency(total * presupuesto.get('materials_percentage', 0) / 100)})")
        print(f"👷 Mano de obra: {presupuesto.get('labor_percentage', 0):.1f}% ({format_currency(total * presupuesto.get('labor_percentage', 0) / 100)})")
        print(f"🚜 Equipos: {presupuesto.get('equipment_percentage', 0):.1f}% ({format_currency(total * presupuesto.get('equipment_percentage', 0) / 100)})")
        print(f"📊 Gastos generales: {presupuesto.get('overhead_percentage', 0):.1f}% ({format_currency(total * presupuesto.get('overhead_percentage', 0) / 100)})")

def display_materials(materiales: List[Dict], max_items: int = 10):
    """Muestra lista de materiales."""
    if not materiales:
        return
    
    print("🧱 MATERIALES DETALLADOS")
    print("-" * 40)
    for i, material in enumerate(materiales[:max_items], 1):
        print(f"{i:2d}. {material.get('descripcion', 'N/A')}")
        print(f"    💰 Costo: {format_currency(material.get('costo_estimado_clp', 0))}")
        print(f"    📦 Cantidad: {material.get('cantidad_estimada', 'N/A')}")
        print(f"    🏪 Proveedor: {material.get('proveedor_sugerido', 'No especificado')}")
        print()
    
    if len(materiales) > max_items:
        print(f"    ... y {len(materiales) - max_items} materiales más")

def display_labor(mano_obra: List[Dict], max_items: int = 8):
    """Muestra detalles de mano de obra."""
    if not mano_obra:
        return
    
    print("👷 MANO DE OBRA")
    print("-" * 40)
    for i, trabajo in enumerate(mano_obra[:max_items], 1):
        print(f"{i:2d}. {trabajo.get('especialidad', 'N/A')}")
        print(f"    👥 Personal: {trabajo.get('cantidad_personas', 0)} personas")
        print(f"    📅 Días: {trabajo.get('dias_trabajo', 0)} días")
        print(f"    💵 Costo diario: {format_currency(trabajo.get('costo_diario', 0))}")
        print(f"    💰 Total: {format_currency(trabajo.get('costo_total', 0))}")
        print()
    
    if len(mano_obra) > max_items:
        print(f"    ... y {len(mano_obra) - max_items} especialidades más")

def display_equipment(equipos: List[Dict], max_items: int = 8):
    """Muestra equipos y maquinaria."""
    if not equipos:
        return
    
    print("🚜 EQUIPOS Y MAQUINARIA")
    print("-" * 40)
    for i, equipo in enumerate(equipos[:max_items], 1):
        print(f"{i:2d}. {equipo.get('tipo_equipo', 'N/A')}")
        print(f"    🔢 Cantidad: {equipo.get('cantidad', 0)} unidades")
        print(f"    📅 Días de uso: {equipo.get('dias_uso', 0)} días")
        print(f"    💵 Costo diario: {format_currency(equipo.get('costo_diario', 0))}")
        print(f"    💰 Total: {format_currency(equipo.get('costo_total', 0))}")
        print()
    
    if len(equipos) > max_items:
        print(f"    ... y {len(equipos) - max_items} equipos más")

def display_risks(riesgos: List[Dict], max_items: int = 5):
    """Muestra análisis de riesgos."""
    if not riesgos:
        return
    
    print("⚠️  ANÁLISIS DE RIESGOS")
    print("-" * 40)
    
    # Agrupar por tipo de riesgo
    risk_types = {}
    for riesgo in riesgos:
        tipo = riesgo.get('tipo_riesgo', 'otros')
        if tipo not in risk_types:
            risk_types[tipo] = []
        risk_types[tipo].append(riesgo)
    
    for tipo, lista_riesgos in risk_types.items():
        print(f"\n📋 {tipo.upper().replace('_', ' ')}")
        for i, riesgo in enumerate(lista_riesgos[:3], 1):  # Max 3 por tipo
            prob = riesgo.get('probabilidad', 'N/A').upper()
            impacto = riesgo.get('impacto', 'N/A').upper()
            
            # Emojis según probabilidad e impacto
            prob_emoji = {"ALTA": "🔴", "MEDIA": "🟡", "BAJA": "🟢"}.get(prob, "⚪")
            impacto_emoji = {"ALTO": "🔴", "MEDIO": "🟡", "BAJO": "🟢"}.get(impacto, "⚪")
            
            print(f"  {i}. {riesgo.get('descripcion', 'N/A')}")
            print(f"     {prob_emoji} Probabilidad: {prob} | {impacto_emoji} Impacto: {impacto}")
            print(f"     🛡️  Mitigación: {riesgo.get('medida_mitigacion', 'N/A')}")
            print()

def display_recommendations(recomendaciones: List[Dict], max_items: int = 8):
    """Muestra recomendaciones."""
    if not recomendaciones:
        return
    
    print("💡 RECOMENDACIONES")
    print("-" * 40)
    
    # Agrupar por prioridad
    high_priority = [r for r in recomendaciones if r.get('prioridad', '').lower() == 'alta']
    medium_priority = [r for r in recomendaciones if r.get('prioridad', '').lower() == 'media']
    low_priority = [r for r in recomendaciones if r.get('prioridad', '').lower() == 'baja']
    
    for priority_name, priority_list, emoji in [
        ("ALTA PRIORIDAD", high_priority, "🔥"),
        ("MEDIA PRIORIDAD", medium_priority, "⚡"),
        ("BAJA PRIORIDAD", low_priority, "💡")
    ]:
        if priority_list:
            print(f"\n{emoji} {priority_name}")
            for i, rec in enumerate(priority_list[:4], 1):  # Max 4 por prioridad
                print(f"  {i}. {rec.get('recomendacion', 'N/A')}")
                print(f"     📂 Categoría: {rec.get('categoria', 'N/A')}")
                print(f"     📋 Justificación: {rec.get('justificacion', 'N/A')}")
                print()

def display_suppliers(proveedores: List[Dict], max_items: int = 10):
    """Muestra proveedores sugeridos."""
    if not proveedores:
        return
    
    print("🏪 PROVEEDORES SUGERIDOS")
    print("-" * 40)
    
    # Agrupar por región si es posible
    by_region = {}
    for proveedor in proveedores:
        region = proveedor.get('region', 'No especificada')
        if region not in by_region:
            by_region[region] = []
        by_region[region].append(proveedor)
    
    for region, lista_proveedores in by_region.items():
        print(f"\n📍 {region.upper()}")
        for i, proveedor in enumerate(lista_proveedores[:5], 1):  # Max 5 por región
            print(f"  {i}. {proveedor.get('nombre_empresa', 'N/A')}")
            print(f"     🏷️  Especialidad: {proveedor.get('especialidad', 'N/A')}")
            print(f"     📂 Categoría: {proveedor.get('categoria', 'N/A')}")
            print(f"     📞 Contacto: {proveedor.get('contacto_estimado', 'Por consultar')}")
            print()

def display_metadata(metadata: Dict, files_summary: Dict = None):
    """Muestra información técnica del análisis."""
    print("📊 INFORMACIÓN TÉCNICA")
    print("-" * 40)
    
    if files_summary:
        print(f"📁 Archivos procesados: {files_summary.get('files_processed', 0)}/{files_summary.get('total_files', 0)}")
        print(f"💰 Archivos con presupuesto: {files_summary.get('files_with_budget_data', 0)}")
        print(f"📄 Total páginas: {files_summary.get('total_pages', 0)}")
        print(f"📋 Tablas encontradas: {files_summary.get('total_tables', 0)}")
        print(f"🔢 Items presupuestarios: {files_summary.get('total_budget_items', 0)}")
    
    print(f"🎯 Nivel de confianza: {metadata.get('confidence_score', 0):.2f}")
    print(f"⏱️  Tiempo de procesamiento: {metadata.get('processingTime', 'N/A')}")
    
    if 'file_names' in metadata:
        print(f"📄 Archivos analizados:")
        for name in metadata['file_names']:
            print(f"    • {name}")

def load_and_display_json(filepath: str):
    """Carga y muestra un archivo JSON de análisis."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        print_separator(f"ANÁLISIS MOP - {os.path.basename(filepath)}")
        
        # Información general
        analysis_id = data.get('analysisId', 'N/A')
        print(f"🆔 ID del Análisis: {analysis_id}")
        print(f"📅 Tipo de análisis: {data.get('metadata', {}).get('analysis_type', 'N/A')}")
        
        # Mostrar cada sección
        analysis = data.get('analysis', {})
        
        print_separator("RESUMEN", char="-", width=50)
        display_project_summary(analysis)
        
        if 'presupuesto_estimado' in analysis:
            print_separator("PRESUPUESTO", char="-", width=50)
            display_budget_summary(analysis['presupuesto_estimado'])
        
        if 'materiales_detallados' in analysis:
            print_separator("MATERIALES", char="-", width=50)
            display_materials(analysis['materiales_detallados'])
        
        if 'mano_obra' in analysis:
            print_separator("MANO DE OBRA", char="-", width=50)
            display_labor(analysis['mano_obra'])
        
        if 'equipos_maquinaria' in analysis:
            print_separator("EQUIPOS", char="-", width=50)
            display_equipment(analysis['equipos_maquinaria'])
        
        if 'analisis_riesgos' in analysis:
            print_separator("RIESGOS", char="-", width=50)
            display_risks(analysis['analisis_riesgos'])
        
        if 'recomendaciones' in analysis:
            print_separator("RECOMENDACIONES", char="-", width=50)
            display_recommendations(analysis['recomendaciones'])
        
        if 'proveedores_chile' in analysis:
            print_separator("PROVEEDORES", char="-", width=50)
            display_suppliers(analysis['proveedores_chile'])
        
        # Información técnica
        print_separator("METADATA", char="-", width=50)
        display_metadata(data.get('metadata', {}), data.get('files_summary'))
        
        print_separator("FIN DEL ANÁLISIS")
        
    except FileNotFoundError:
        print(f"❌ Error: No se encuentra el archivo {filepath}")
    except json.JSONDecodeError as e:
        print(f"❌ Error: El archivo no es un JSON válido - {e}")
    except Exception as e:
        print(f"❌ Error inesperado: {e}")

def main():
    """Función principal."""
    if len(sys.argv) != 2:
        print("📖 Uso: python json_viewer.py <archivo.json>")
        print("📁 Ejemplo: python json_viewer.py cci_futrono_analysis_12345678.json")
        
        # Buscar archivos JSON en el directorio actual
        json_files = list(Path(".").glob("*.json"))
        if json_files:
            print(f"\n📁 Archivos JSON encontrados en el directorio actual:")
            for i, file in enumerate(json_files, 1):
                file_size = file.stat().st_size / 1024  # KB
                print(f"  {i}. {file.name} ({file_size:.1f}KB)")
        
        return
    
    filepath = sys.argv[1]
    load_and_display_json(filepath)

if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
Script simple para generar y abrir reporte HTML desde JSON de análisis MOP.
"""

import json
import sys
import subprocess
import platform
import webbrowser
from datetime import datetime
from pathlib import Path

def format_currency(amount):
    """Formatea montos en pesos chilenos."""
    if amount == 0:
        return "$0"
    return f"${amount:,.0f}".replace(",", ".")

def create_html_report(json_data, output_file):
    """Crea un reporte HTML limpio y profesional."""
    
    analysis = json_data.get('analysis', {})
    metadata = json_data.get('metadata', {})
    files_summary = json_data.get('files_summary', {})
    
    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Análisis MOP - {json_data.get('analysisId', 'N/A')}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6; background: #f8f9fa; color: #333; padding: 20px;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; border-radius: 12px; 
                     box-shadow: 0 4px 20px rgba(0,0,0,0.1); overflow: hidden; }}
        .header {{ background: linear-gradient(135deg, #2563eb, #7c3aed); color: white; 
                   padding: 40px 30px; text-align: center; }}
        .header h1 {{ font-size: 2.5rem; margin-bottom: 10px; font-weight: 700; }}
        .header .subtitle {{ opacity: 0.9; font-size: 1.1rem; }}
        .content {{ padding: 30px; }}
        .section {{ margin-bottom: 40px; }}
        .section-title {{ color: #2563eb; font-size: 1.5rem; font-weight: 600;
                          border-bottom: 3px solid #2563eb; padding-bottom: 8px; margin-bottom: 25px; }}
        .summary-box {{ background: linear-gradient(135deg, #f0f9ff, #e0f2fe); 
                       border-left: 5px solid #2563eb; padding: 25px; border-radius: 8px; 
                       margin-bottom: 30px; }}
        .budget-highlight {{ background: linear-gradient(135deg, #10b981, #059669); 
                            color: white; text-align: center; padding: 40px; border-radius: 12px;
                            margin: 30px 0; box-shadow: 0 4px 15px rgba(16, 185, 129, 0.3); }}
        .budget-amount {{ font-size: 3rem; font-weight: 700; margin-bottom: 10px; }}
        .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); 
                      gap: 20px; margin: 30px 0; }}
        .stat-card {{ background: white; border: 2px solid #e5e7eb; border-radius: 12px; 
                     padding: 25px; text-align: center; transition: transform 0.2s; }}
        .stat-card:hover {{ transform: translateY(-2px); box-shadow: 0 4px 15px rgba(0,0,0,0.1); }}
        .stat-number {{ display: block; font-size: 2.5rem; font-weight: 700; color: #2563eb; }}
        .stat-label {{ color: #6b7280; font-weight: 500; margin-top: 8px; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(350px, 1fr)); gap: 25px; }}
        .card {{ background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 10px; padding: 25px; }}
        .card-title {{ font-size: 1.2rem; font-weight: 600; margin-bottom: 15px; }}
        .risk-item, .rec-item, .provider-item {{ 
            background: white; border-radius: 8px; padding: 20px; margin-bottom: 15px;
            border-left: 5px solid #e5e7eb; transition: all 0.2s;
        }}
        .risk-alta {{ border-left-color: #dc2626; background: #fef2f2; }}
        .risk-media {{ border-left-color: #f59e0b; background: #fffbeb; }}
        .risk-baja {{ border-left-color: #10b981; background: #f0fdf4; }}
        .priority-alta {{ border-left-color: #dc2626; background: #fef2f2; }}
        .priority-media {{ border-left-color: #f59e0b; background: #fffbeb; }}
        .priority-baja {{ border-left-color: #10b981; background: #f0fdf4; }}
        .item-title {{ font-weight: 600; color: #374151; margin-bottom: 10px; }}
        .item-meta {{ color: #6b7280; font-size: 0.9rem; margin-bottom: 8px; }}
        .item-desc {{ color: #4b5563; }}
        .footer {{ background: #374151; color: white; text-align: center; padding: 30px; }}
        .footer p {{ margin: 5px 0; }}
        @media (max-width: 768px) {{
            .container {{ margin: 10px; border-radius: 0; }}
            .content {{ padding: 20px; }}
            .header {{ padding: 30px 20px; }}
            .budget-amount {{ font-size: 2rem; }}
            .grid {{ grid-template-columns: 1fr; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 Análisis de Licitación MOP</h1>
            <p class="subtitle">ID: {json_data.get('analysisId', 'N/A')}</p>
            <p class="subtitle">Generado: {datetime.now().strftime('%d/%m/%Y a las %H:%M')}</p>
        </div>
        
        <div class="content">
            <!-- Resumen Ejecutivo -->
            <div class="section">
                <h2 class="section-title">📋 Resumen Ejecutivo</h2>
                <div class="summary-box">
                    <p style="font-size: 1.1rem; margin-bottom: 15px;">
                        {analysis.get('resumen_ejecutivo', 'No disponible')}
                    </p>
                    <p><strong>⏱️ Cronograma estimado:</strong> {analysis.get('cronograma_estimado', 'No especificado')}</p>
                </div>
            </div>
            
            <!-- Presupuesto -->
            <div class="section">
                <h2 class="section-title">💰 Presupuesto Total</h2>
                <div class="budget-highlight">
                    <div class="budget-amount">{format_currency(analysis.get('presupuesto_estimado', {}).get('total_clp', 0))}</div>
                    <p style="font-size: 1.2rem; opacity: 0.9;">Pesos Chilenos (CLP)</p>
                </div>
            </div>
            
            <!-- Estadísticas -->
            <div class="section">
                <h2 class="section-title">📈 Estadísticas del Análisis</h2>
                <div class="stats-grid">
                    <div class="stat-card">
                        <span class="stat-number">{files_summary.get('files_processed', 0)}</span>
                        <div class="stat-label">📄 Archivos Procesados</div>
                    </div>
                    <div class="stat-card">
                        <span class="stat-number">{files_summary.get('total_pages', 0)}</span>
                        <div class="stat-label">📖 Páginas Analizadas</div>
                    </div>
                    <div class="stat-card">
                        <span class="stat-number">{files_summary.get('total_tables', 0)}</span>
                        <div class="stat-label">📋 Tablas Encontradas</div>
                    </div>
                    <div class="stat-card">
                        <span class="stat-number">{metadata.get('confidence_score', 0):.2f}</span>
                        <div class="stat-label">🎯 Score de Confianza</div>
                    </div>
                </div>
            </div>
            
            <!-- Riesgos y Recomendaciones -->
            <div class="section">
                <div class="grid">
                    <!-- Riesgos -->
                    <div class="card">
                        <div class="card-title">⚠️ Análisis de Riesgos</div>"""
    
    # Agregar riesgos
    riesgos = analysis.get('analisis_riesgos', [])
    if riesgos:
        for riesgo in riesgos:
            prob = riesgo.get('probabilidad', 'media').lower()
            html += f"""
                        <div class="risk-item risk-{prob}">
                            <div class="item-title">🚨 {riesgo.get('descripcion', 'N/A')}</div>
                            <div class="item-meta">
                                📊 {riesgo.get('probabilidad', 'N/A').title()} probabilidad • 
                                💥 {riesgo.get('impacto', 'N/A').title()} impacto
                            </div>
                            <div class="item-desc">
                                <strong>Mitigación:</strong> {riesgo.get('medida_mitigacion', 'N/A')}
                            </div>
                        </div>"""
    else:
        html += "<p>No se identificaron riesgos específicos.</p>"
    
    html += """
                    </div>
                    
                    <!-- Recomendaciones -->
                    <div class="card">
                        <div class="card-title">💡 Recomendaciones</div>"""
    
    # Agregar recomendaciones
    recomendaciones = analysis.get('recomendaciones', [])
    if recomendaciones:
        for rec in recomendaciones:
            prioridad = rec.get('prioridad', 'media').lower()
            html += f"""
                        <div class="rec-item priority-{prioridad}">
                            <div class="item-title">💡 {rec.get('recomendacion', 'N/A')}</div>
                            <div class="item-meta">
                                📂 {rec.get('categoria', 'N/A').title()} • 
                                🔥 Prioridad {rec.get('prioridad', 'N/A').title()}
                            </div>
                            <div class="item-desc">{rec.get('justificacion', 'N/A')}</div>
                        </div>"""
    else:
        html += "<p>No se generaron recomendaciones específicas.</p>"
    
    html += """
                    </div>
                </div>
            </div>
            
            <!-- Proveedores -->
            <div class="section">
                <h2 class="section-title">🏪 Proveedores Sugeridos</h2>"""
    
    # Agregar proveedores
    proveedores = analysis.get('proveedores_chile', [])
    if proveedores:
        for prov in proveedores:
            html += f"""
                <div class="provider-item">
                    <div class="item-title">🏢 {prov.get('nombre_empresa', 'N/A')}</div>
                    <div class="item-meta">
                        📍 {prov.get('region', 'N/A')} • 
                        🔧 {prov.get('especialidad', 'N/A')}
                    </div>
                    <div class="item-desc">📞 {prov.get('contacto_estimado', 'Por consultar')}</div>
                </div>"""
    else:
        html += "<p>No se identificaron proveedores específicos.</p>"
    
    # Cerrar HTML
    html += f"""
            </div>
        </div>
        
        <div class="footer">
            <p><strong>📄 Análisis MOP automatizado</strong></p>
            <p>🏗️ {metadata.get('project_type', 'N/A')} • {metadata.get('project_location', 'N/A')}</p>
            <p>⚡ Procesado en {metadata.get('processingTime', 'N/A')}</p>
        </div>
    </div>
</body>
</html>"""
    
    # Escribir archivo
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)
    
    return output_file

def open_file(filepath):
    """Abre un archivo con la aplicación predeterminada del sistema."""
    system = platform.system()
    
    try:
        if system == "Darwin":  # macOS
            subprocess.run(['open', filepath], check=True)
        elif system == "Windows":
            subprocess.run(['start', filepath], shell=True, check=True)
        elif system == "Linux":
            subprocess.run(['xdg-open', filepath], check=True)
        else:
            # Fallback usando webbrowser
            webbrowser.open(f'file://{Path(filepath).absolute()}')
            
        return True
    except:
        # Fallback final
        try:
            webbrowser.open(f'file://{Path(filepath).absolute()}')
            return True
        except:
            return False

def main():
    if len(sys.argv) != 2:
        print("📖 Uso: python open_report.py <archivo.json>")
        print("📁 Ejemplo: python open_report.py cci_futrono_results.json")
        return
    
    json_file = sys.argv[1]
    
    if not Path(json_file).exists():
        print(f"❌ Error: No se encuentra el archivo {json_file}")
        return
    
    print(f"📄 Procesando {json_file}...")
    
    try:
        # Cargar JSON
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Crear nombre del HTML
        html_file = json_file.replace('.json', '_reporte.html')
        
        # Generar HTML
        print("🔨 Generando reporte HTML...")
        create_html_report(data, html_file)
        
        # Abrir archivo
        print("🌐 Abriendo reporte en el navegador...")
        if open_file(html_file):
            print(f"✅ ¡Reporte abierto exitosamente!")
            print(f"📁 Archivo guardado como: {html_file}")
        else:
            print(f"⚠️  Reporte generado pero no se pudo abrir automáticamente")
            print(f"📁 Abre manualmente: {html_file}")
        
    except json.JSONDecodeError:
        print(f"❌ Error: El archivo {json_file} no es un JSON válido")
    except Exception as e:
        print(f"❌ Error procesando archivo: {e}")

if __name__ == "__main__":
    main()
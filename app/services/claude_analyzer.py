"""
Analizador de contenido MOP usando Claude AI.
Procesa el contenido extraído y genera análisis estructurado.
"""

import asyncio
import json
import re
from typing import Dict, List, Optional, Any
from datetime import datetime
import logging

import anthropic
from anthropic import AsyncAnthropic

from app.config.settings import get_settings
from app.config.constants import (
    MOP_CODES, COST_CATEGORIES, VALIDATION_RANGES,
    categorize_item_by_description, clean_currency_string
)

logger = logging.getLogger(__name__)


class ClaudeAnalyzer:
    """
    Analizador Claude mejorado que implementa la lógica de tu JS controller
    con análisis detallado de presupuestos MOP.
    """
    
    def __init__(self, api_key: str):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.max_retries = 3
        self.chunk_size = 8000
        
        # Patrones específicos MOP (extraídos de tus docs)
        self.mop_patterns = {
            'codigo_mop': r'7\.\d{3}\.\d+[a-zA-Z]?',
            'precio': r'\$\s*[\d.,]+',
            'unidad': r'\b(m3|m2|ml|kg|ton|gl|uni|mes|día|hr|lts)\b',
            'proyecto': r'(?i)(proyecto|obra|construcción|conservación|mejoramiento)',
            'region': r'(?i)(región|región de los ríos|región del ranco)',
            'comuna': r'(?i)(comuna|lago ranco|futrono)'
        }
    
    async def analyze_mop_document_detailed(
        self, 
        extracted_content: Dict[str, Any], 
        analysis_depth: str = "full"
    ) -> Dict[str, Any]:
        """
        Análisis detallado que replica la lógica de tu JS controller
        pero con mejor extracción de información presupuestaria.
        """
        
        logger.info("Iniciando análisis detallado MOP")
        
        try:
            # 1. Pre-procesar contenido como en tu JS
            processed_content = self._preprocess_mop_content(extracted_content)
            
            # 2. Crear chunks inteligentes por secciones
            chunks = self._create_intelligent_chunks(processed_content)
            
            # 3. Análisis multi-prompt como tu JS controller
            analysis_results = await self._multi_prompt_analysis(chunks, analysis_depth)
            
            # 4. Consolidar y corregir cálculos (tu función procesarYCorregirAnalisis)
            consolidated = self._consolidate_and_correct_analysis(
                analysis_results, 
                processed_content
            )
            
            # 5. Validar consistencia (tu función validarConsistenciaPresupuesto)
            validation = self._validate_budget_consistency(consolidated)
            
            # 6. Aplicar correcciones finales
            final_analysis = self._apply_final_corrections(consolidated, validation)
            
            return final_analysis
            
        except Exception as e:
            logger.error(f"Error en análisis detallado: {e}")
            return self._create_fallback_response(str(e), extracted_content)
    
    def _preprocess_mop_content(self, extracted_content: Dict[str, Any]) -> Dict[str, Any]:
        """
        Pre-procesa contenido específico para documentos MOP.
        Basado en tu lógica JS pero optimizado para Python.
        """
        
        text_content = extracted_content.get("text_content", "")
        budget_items = extracted_content.get("budget_items", [])
        tables = extracted_content.get("tables", [])
        
        # Extraer información del proyecto
        project_info = self._extract_project_info(text_content)
        
        # Identificar secciones presupuestarias
        budget_sections = self._identify_budget_sections(text_content)
        
        # Procesar items presupuestarios de tablas
        processed_items = self._process_budget_items(budget_items, tables)
        
        # Extraer totales y subtotales
        financial_totals = self._extract_financial_totals(text_content, tables)
        
        return {
            "text_content": text_content,
            "project_info": project_info,
            "budget_sections": budget_sections,
            "processed_items": processed_items,
            "financial_totals": financial_totals,
            "content_length": len(text_content),
            "tables_count": len(tables),
            "items_count": len(processed_items)
        }
    
    def _extract_project_info(self, text: str) -> Dict[str, Any]:
        """Extrae información del proyecto usando patrones específicos MOP."""
        
        info = {
            "nombre": "",
            "region": "",
            "comuna": "",
            "provincia": "",
            "tipo_obra": "",
            "etapa": "",
            "coordenadas_utm": ""
        }
        
        # Buscar nombre del proyecto
        project_patterns = [
            r'PROYECTO\s*:\s*([^:\n]+)',
            r'NOMBRE\s+PROYECTO\s*:\s*([^:\n]+)',
            r'(?i)(CONSERVACION|CONSTRUCCION|MEJORAMIENTO)\s+DE\s+([^\n,]+)'
        ]
        
        for pattern in project_patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                info["nombre"] = match.group(1 if len(match.groups()) == 1 else 2).strip()
                break
        
        # Extraer ubicación
        if "REGIÓN DE LOS RÍOS" in text.upper():
            info["region"] = "Región de Los Ríos"
        
        if "LAGO RANCO" in text.upper():
            info["comuna"] = "Lago Ranco"
        if "FUTRONO" in text.upper():
            info["comuna"] += (", " if info["comuna"] else "") + "Futrono"
        
        # Extraer etapa
        etapa_match = re.search(r'ETAPA\s*:\s*([^:\n]+)', text, re.IGNORECASE)
        if etapa_match:
            info["etapa"] = etapa_match.group(1).strip()
        
        return info
    
    def _identify_budget_sections(self, text: str) -> Dict[str, str]:
        """Identifica y extrae secciones del presupuesto."""
        
        sections = {}
        
        # Patrones de secciones importantes
        section_patterns = {
            "materiales": r'(?i)(A\.\s*MATERIALES|MATERIALES|INSUMOS)(.*?)(?=B\.|MANO DE OBRA|\n\n[A-Z])',
            "mano_obra": r'(?i)(B\.\s*MANO DE OBRA|MANO DE OBRA|PERSONAL)(.*?)(?=C\.|EQUIPOS|\n\n[A-Z])',
            "equipos": r'(?i)(C\.\s*EQUIPOS|EQUIPOS Y MAQUINARIAS|MAQUINARIA)(.*?)(?=D\.|GASTOS|\n\n[A-Z])',
            "gastos_generales": r'(?i)(GASTOS GENERALES|GASTOS ADMINISTRATIVOS)(.*?)(?=TOTAL|UTILIDAD|\n\n[A-Z])',
            "resumen": r'(?i)(TOTAL NETO|TOTAL GENERAL|RESUMEN)(.*?)(?=\n\n[A-Z]|$)'
        }
        
        for section_name, pattern in section_patterns.items():
            match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
            if match:
                sections[section_name] = match.group(2).strip()[:2000]  # Limitar tamaño
        
        return sections
    
    def _process_budget_items(self, raw_items: List[Dict], tables: List) -> List[Dict]:
        """Procesa items presupuestarios con validación y corrección."""
        
        processed_items = []
        
        for item in raw_items:
            processed_item = self._validate_and_clean_item(item)
            if processed_item:
                processed_items.append(processed_item)
        
        # Extraer items adicionales de tablas si no hay suficientes
        if len(processed_items) < 5 and tables:
            additional_items = self._extract_items_from_tables(tables)
            processed_items.extend(additional_items)
        
        return processed_items
    
    def _validate_and_clean_item(self, item: Dict) -> Optional[Dict]:
        """Valida y limpia un item presupuestario."""
        
        # Validar código MOP
        codigo = item.get("codigo_mop", "").strip()
        if not re.match(self.mop_patterns['codigo_mop'], codigo):
            # Intentar extraer código de la descripción
            desc = item.get("descripcion", "")
            codigo_match = re.search(self.mop_patterns['codigo_mop'], desc)
            if codigo_match:
                codigo = codigo_match.group()
            else:
                return None  # Sin código MOP válido
        
        # Limpiar valores numéricos
        cantidad = self._clean_numeric_value(item.get("cantidad", 0))
        precio_unitario = self._clean_numeric_value(item.get("precio_unitario", 0))
        subtotal = self._clean_numeric_value(item.get("subtotal", 0))
        
        # Validar cálculo
        if cantidad > 0 and precio_unitario > 0:
            calculated_subtotal = cantidad * precio_unitario
            if abs(subtotal - calculated_subtotal) > 100:  # Tolerancia de 100 pesos
                logger.warning(f"Cálculo incorrecto en item {codigo}: {subtotal} vs {calculated_subtotal}")
                subtotal = calculated_subtotal
        
        # Categorizar item
        categoria = self._categorize_mop_item(codigo, item.get("descripcion", ""))
        
        return {
            "codigo_mop": codigo,
            "descripcion": item.get("descripcion", "").strip(),
            "unidad": item.get("unidad", "").strip(),
            "cantidad": cantidad,
            "precio_unitario": precio_unitario,
            "subtotal": subtotal,
            "categoria": categoria
        }
    
    def _categorize_mop_item(self, codigo: str, descripcion: str) -> str:
        """Categoriza un item MOP según su código y descripción."""
        
        # Categorización por código MOP
        if codigo.startswith("7.301"):
            return "limpieza_demolicion"
        elif codigo.startswith("7.302"):
            return "movimiento_tierras"
        elif codigo.startswith("7.303"):
            return "drenaje_alcantarillado"
        elif codigo.startswith("7.304"):
            return "pavimentacion"
        elif codigo.startswith("7.305"):
            return "obras_arte"
        elif codigo.startswith("7.306"):
            return "materiales"
        elif codigo.startswith("7.311"):
            return "mantenciones"
        
        # Categorización por descripción
        desc_lower = descripcion.lower()
        if any(word in desc_lower for word in ["material", "insumo", "agregado", "cemento", "acero"]):
            return "materials"
        elif any(word in desc_lower for word in ["jornal", "personal", "trabajador", "operario"]):
            return "labor"
        elif any(word in desc_lower for word in ["excavadora", "camión", "maquinaria", "equipo"]):
            return "equipment"
        else:
            return "otros"
    
    def _extract_financial_totals(self, text: str, tables: List) -> Dict[str, float]:
        """Extrae totales financieros del documento."""
        
        totals = {
            "total_neto": 0,
            "iva": 0,
            "total_bruto": 0,
            "gastos_generales": 0,
            "utilidad": 0
        }
        
        # Patrones para encontrar totales
        total_patterns = {
            "total_neto": r'TOTAL\s+NETO\s*[:$]?\s*([\d.,]+)',
            "iva": r'(?:IVA|I\.V\.A\.)\s*19%?\s*[:$]?\s*([\d.,]+)',
            "total_bruto": r'TOTAL\s+(?:BRUTO|GENERAL)\s*[:$]?\s*([\d.,]+)',
            "gastos_generales": r'GASTOS\s+GENERALES\s*[:$]?\s*([\d.,]+)',
            "utilidad": r'UTILIDAD(?:ES)?\s*[:$]?\s*([\d.,]+)'
        }
        
        for key, pattern in total_patterns.items():
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                # Tomar el valor más alto encontrado (probablemente el total)
                values = [self._clean_numeric_value(match) for match in matches]
                totals[key] = max(values) if values else 0
        
        # También buscar en tablas
        for table in tables:
            if isinstance(table, list) and len(table) > 0:
                for row in table[-3:]:  # Últimas 3 filas
                    if isinstance(row, dict):
                        for cell_key, cell_value in row.items():
                            if "total" in str(cell_key).lower():
                                value = self._clean_numeric_value(str(cell_value))
                                if value > totals.get("total_bruto", 0):
                                    totals["total_bruto"] = value
        
        return totals
    
    def _clean_numeric_value(self, value) -> float:
        """Limpia y convierte valores numéricos."""
        
        if isinstance(value, (int, float)):
            return float(value)
        
        if isinstance(value, str):
            # Remover símbolos y espacios
            cleaned = re.sub(r'[^\d.,]', '', value)
            # Manejar formato chileno (puntos como separadores de miles)
            if ',' in cleaned and '.' in cleaned:
                # Formato: 1.234.567,89
                cleaned = cleaned.replace('.', '').replace(',', '.')
            elif '.' in cleaned and len(cleaned.split('.')[-1]) <= 2:
                # Formato: 1234.56 (decimales)
                pass
            else:
                # Formato: 1.234.567 (separadores de miles)
                cleaned = cleaned.replace(',', '').replace('.', '')
            
            try:
                return float(cleaned) if cleaned else 0
            except ValueError:
                return 0
        
        return 0
    
    async def _multi_prompt_analysis(
        self, 
        chunks: List[Dict], 
        analysis_depth: str
    ) -> Dict[str, Any]:
        """Análisis multi-prompt como tu JS controller pero mejorado."""
        
        analysis_results = {
            "budget_analysis": None,
            "risk_analysis": None,
            "provider_analysis": None
        }
        
        # Prompt principal de presupuesto
        budget_prompt = self._build_detailed_budget_prompt(chunks)
        budget_result = await self._execute_claude_prompt(budget_prompt)
        if budget_result and budget_result.get("success"):
            analysis_results["budget_analysis"] = budget_result
        
        # Prompt de análisis de riesgos si es análisis completo
        if analysis_depth in ["full", "detailed"]:
            risk_prompt = self._build_risk_analysis_prompt(chunks)
            risk_result = await self._execute_claude_prompt(risk_prompt)
            if risk_result and risk_result.get("success"):
                analysis_results["risk_analysis"] = risk_result
            
            # Prompt de proveedores
            provider_prompt = self._build_provider_analysis_prompt(chunks)
            provider_result = await self._execute_claude_prompt(provider_prompt)
            if provider_result and provider_result.get("success"):
                analysis_results["provider_analysis"] = provider_result
        
        return analysis_results
    
    def _create_intelligent_chunks(self, processed_content: Dict[str, Any]) -> List[Dict]:
        """Crea chunks inteligentes basados en secciones del presupuesto."""
        
        chunks = []
        
        # Chunk principal con información del proyecto
        main_chunk = {
            "type": "project_info",
            "content": f"""
INFORMACIÓN DEL PROYECTO:
{json.dumps(processed_content['project_info'], indent=2, ensure_ascii=False)}

RESUMEN DEL CONTENIDO:
- Longitud del texto: {processed_content['content_length']} caracteres
- Número de tablas: {processed_content['tables_count']}
- Items presupuestarios identificados: {processed_content['items_count']}

TOTALES FINANCIEROS IDENTIFICADOS:
{json.dumps(processed_content['financial_totals'], indent=2, ensure_ascii=False)}
""",
            "priority": 1
        }
        chunks.append(main_chunk)
        
        # Chunks por sección presupuestaria
        for section_name, section_content in processed_content["budget_sections"].items():
            if section_content.strip():
                chunks.append({
                    "type": f"budget_section_{section_name}",
                    "content": f"SECCIÓN {section_name.upper()}:\n{section_content}",
                    "priority": 2
                })
        
        # Chunk de items procesados
        if processed_content["processed_items"]:
            items_text = "ITEMS PRESUPUESTARIOS PROCESADOS:\n"
            for i, item in enumerate(processed_content["processed_items"][:20]):  # Máximo 20
                items_text += f"{i+1}. {item['codigo_mop']} - {item['descripcion'][:100]}\n"
                items_text += f"   Cantidad: {item['cantidad']} {item['unidad']} | "
                items_text += f"P.Unit: ${item['precio_unitario']:,.0f} | "
                items_text += f"Subtotal: ${item['subtotal']:,.0f}\n\n"
            
            chunks.append({
                "type": "processed_items",
                "content": items_text,
                "priority": 2
            })
        
        # Chunk del texto completo (truncado) como contexto
        text_content = processed_content["text_content"]
        if len(text_content) > 4000:
            text_content = text_content[:4000] + "...\n[TEXTO TRUNCADO PARA OPTIMIZAR ANÁLISIS]"
        
        chunks.append({
            "type": "full_context",
            "content": f"CONTEXTO COMPLETO DEL DOCUMENTO:\n{text_content}",
            "priority": 3
        })
        
        # Ordenar por prioridad
        chunks.sort(key=lambda x: x["priority"])
        
        return chunks
    
    def _build_detailed_budget_prompt(self, chunks: List[Dict]) -> str:
        """Construye prompt detallado para análisis presupuestario."""
        
        # Combinar contenido de chunks por prioridad
        combined_content = ""
        for chunk in chunks[:3]:  # Solo los 3 más importantes
            combined_content += f"\n\n{chunk['content']}"
        
        return f"""
Eres un experto en análisis de licitaciones del Ministerio de Obras Públicas (MOP) de Chile con 20 años de experiencia en proyectos viales e infraestructura pública.

DOCUMENTO A ANALIZAR:
{combined_content[:12000]}

INSTRUCCIONES ESPECÍFICAS:
1. Analiza este documento de licitación MOP chileno con metodología profesional
2. Extrae TODA la información presupuestaria disponible
3. Identifica códigos MOP estándar y valida su coherencia
4. Calcula totales aplicando metodología estándar chilena:
   - Gastos Generales: 12% sobre costos directos
   - Utilidad: 10% sobre (costos directos + gastos generales)  
   - Contingencia: 5% sobre costos directos
   - IVA: 19% sobre subtotal
5. Clasifica TODOS los costos por categoría específica
6. Proporciona análisis detallado de cada partida importante
7. Identifica proveedores chilenos específicos por región
8. Analiza riesgos técnicos, financieros y operacionales
9. Genera recomendaciones específicas y accionables

ESTRUCTURA JSON REQUERIDA (completa TODOS los campos):
{{
    "proyecto_info": {{
        "nombre": "string - nombre completo del proyecto",
        "region": "string - región específica",
        "comuna": "string - comuna(s) involucradas",
        "provincia": "string - provincia",
        "tipo_obra": "string - tipo específico de construcción",
        "etapa": "string - etapa del proyecto",
        "coordenadas_utm": "string - coordenadas si disponibles",
        "mandante": "string - organismo mandante",
        "inspector_fiscal": "string - si está disponible"
    }},
    
    "resumen_ejecutivo": "string - Análisis profesional detallado del proyecto (mínimo 300 palabras). Incluir: tipo de obra, ubicación exacta, alcance, metodología constructiva, aspectos técnicos relevantes, cronograma estimado, y consideraciones especiales del terreno o ubicación.",
    
    "presupuesto_estimado": {{
        "total_clp": number - total final calculado,
        "materials_percentage": number - % materiales del costo directo,
        "labor_percentage": number - % mano de obra del costo directo, 
        "equipment_percentage": number - % equipos del costo directo,
        "overhead_percentage": number - % overhead del costo directo
    }},
    
    "desglose_costos_detallado": {{
        "costos_directos": {{
            "materiales": number,
            "mano_obra": number, 
            "equipos": number,
            "subcontratos": number,
            "total": number
        }},
        "costos_indirectos": {{
            "gastos_generales": number - 12% sobre costos directos,
            "utilidad": number - 10% sobre (directos + GG),
            "contingencia": number - 5% sobre costos directos,
            "total": number
        }},
        "impuestos": {{
            "subtotal": number - directos + indirectos,
            "iva": number - 19% sobre subtotal,
            "total_final": number
        }}
    }},
    
    "materiales_detallados": [
        {{
            "codigo_mop": "string",
            "descripcion": "string - descripción técnica completa",
            "unidad": "string",
            "cantidad": number,
            "precio_unitario": number,
            "subtotal": number,
            "categoria": "string - categoría específica MOP",
            "especificaciones_tecnicas": "string - especificaciones detalladas",
            "proveedor_sugerido": "string - proveedor chileno específico",
            "region_proveedor": "string - región del proveedor",
            "observaciones": "string - notas técnicas importantes"
        }}
    ],
    
    "mano_obra_detallada": [
        {{
            "especialidad": "string - especialidad específica",
            "codigo_mop": "string - si aplica",
            "cantidad_trabajadores": number,
            "horas_totales": number,
            "tarifa_hora": number,
            "subtotal": number,
            "nivel_experiencia": "string - junior/intermedio/senior/especialista",
            "certificaciones_requeridas": "string - certificaciones necesarias",
            "condiciones_trabajo": "string - condiciones especiales",
            "observaciones": "string - requisitos específicos"
        }}
    ],
    
    "equipos_maquinaria_detallados": [
        {{
            "tipo_equipo": "string - tipo específico",
            "codigo_mop": "string - si aplica", 
            "modelo_sugerido": "string - modelo recomendado",
            "cantidad": number,
            "tarifa_diaria": number,
            "dias_uso": number,
            "subtotal": number,
            "incluye_operador": boolean,
            "especificaciones_tecnicas": "string - specs técnicas",
            "proveedor_sugerido": "string - empresa de arriendo",
            "observaciones": "string - requisitos especiales"
        }}
    ],
    
    "proveedores_chile_especificos": [
        {{
            "nombre": "string - nombre real de empresa",
            "rut": "string - RUT si disponible",
            "categoria": "string - tipo de productos/servicios",
            "region_operacion": "string - regiones donde opera",
            "contacto": "string - información de contacto",
            "especialidades": ["string"] - lista especialidades,
            "experiencia_mop": "string - experiencia previa MOP",
            "certificaciones": "string - certificaciones relevantes"
        }}
    ],
    
    "analisis_riesgos_detallado": [
        {{
            "categoria": "string - técnico/financiero/operacional/ambiental/legal",
            "factor": "string - descripción específica del riesgo", 
            "probabilidad": "alta|media|baja",
            "impacto": "alto|medio|bajo",
            "impacto_financiero": number - costo estimado en CLP,
            "mitigation": "string - estrategia específica de mitigación",
            "responsable": "string - quién debe gestionar",
            "timeline": "string - cuándo implementar",
            "indicadores": "string - cómo medir efectividad"
        }}
    ],
    
    "recomendaciones_especificas": [
        {{
            "categoria": "string - técnica/financiera/operacional/legal",
            "recomendacion": "string - recomendación específica",
            "justificacion": "string - por qué es importante",
            "impacto_estimado": "string - beneficio esperado",
            "prioridad": "alta|media|baja",
            "timeline": "string - cuándo implementar",
            "responsable": "string - quién debe ejecutar"
        }}
    ],
    
    "cronograma_detallado": {{
        "duracion_total_meses": number,
        "fases": [
            {{
                "fase": "string - nombre de la fase",
                "duracion_semanas": number,
                "actividades_principales": ["string"],
                "recursos_criticos": ["string"],
                "dependencias": ["string"]
            }}
        ],
        "hitos_criticos": ["string"],
        "factores_estacionales": "string - consideraciones climáticas",
        "ruta_critica": "string - actividades más importantes"
    }}
}}

VALIDACIONES OBLIGATORIAS:
1. Todos los cálculos matemáticos deben ser exactos
2. Los porcentajes de categorías deben basarse en costos directos reales
3. El IVA debe ser exactamente 19% del subtotal
4. Incluir mínimo 8 materiales, 5 tipos de mano de obra, 5 equipos
5. Mínimo 6 riesgos identificados y 8 recomendaciones
6. Todos los proveedores deben ser empresas chilenas reales
7. Las especificaciones técnicas deben ser detalladas y precisas

RESPONDE ÚNICAMENTE CON JSON VÁLIDO, SIN TEXTO ADICIONAL.
"""

    def _consolidate_and_correct_analysis(
        self, 
        analysis_results: Dict[str, Any], 
        processed_content: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Consolida y corrige análisis aplicando tu lógica JS de procesarYCorregirAnalisis.
        """
        
        # Obtener resultado principal
        main_result = analysis_results.get("budget_analysis")
        if not main_result or not main_result.get("success"):
            return self._create_basic_analysis(processed_content)
        
        analysis_data = main_result.get("data", {})
        
        # Aplicar correcciones matemáticas como tu JS controller
        corrected_analysis = self._apply_budget_corrections(analysis_data, processed_content)
        
        # Enriquecer con análisis adicionales
        if analysis_results.get("risk_analysis"):
            risk_data = analysis_results["risk_analysis"].get("data", {})
            corrected_analysis = self._merge_risk_analysis(corrected_analysis, risk_data)
        
        if analysis_results.get("provider_analysis"):
            provider_data = analysis_results["provider_analysis"].get("data", {})
            corrected_analysis = self._merge_provider_analysis(corrected_analysis, provider_data)
        
        return corrected_analysis
    
    def _create_basic_analysis(self, processed_content: Dict[str, Any]) -> Dict[str, Any]:
        """Crea análisis básico cuando Claude falla completamente."""
        
        analysis_id = f"basic_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Usar totales extraídos si están disponibles
        financial_totals = processed_content.get("financial_totals", {})
        estimated_total = financial_totals.get("total_bruto", 0)
        
        # Si no hay totales, usar items procesados
        if estimated_total == 0:
            items = processed_content.get("processed_items", [])
            estimated_total = sum(item.get("subtotal", 0) for item in items)
        
        return {
            "analysisId": analysis_id,
            "analysis": {
                "resumen_ejecutivo": "Análisis básico generado a partir de la extracción de datos. El análisis completo con IA no estuvo disponible.",
                "presupuesto_estimado": {
                    "total_clp": estimated_total,
                    "materials_percentage": 45,
                    "labor_percentage": 30,
                    "equipment_percentage": 25,
                    "overhead_percentage": 35
                },
                "proyecto_info": processed_content.get("project_info", {}),
                "materiales_detallados": [
                    {
                        "codigo_mop": item.get("codigo_mop", "N/A"),
                        "descripcion": item.get("descripcion", ""),
                        "unidad": item.get("unidad", ""),
                        "cantidad": item.get("cantidad", 0),
                        "precio_unitario": item.get("precio_unitario", 0),
                        "subtotal": item.get("subtotal", 0),
                        "categoria": item.get("categoria", "materials")
                    }
                    for item in processed_content.get("processed_items", [])[:10]
                    if item.get("categoria") in ["materials", "materiales"]
                ],
                "mano_obra_detallada": [],
                "equipos_maquinaria_detallados": [],
                "proveedores_chile_especificos": [],
                "analisis_riesgos_detallado": [
                    {
                        "categoria": "técnico",
                        "factor": "Análisis básico - Revisión manual recomendada",
                        "probabilidad": "media",
                        "impacto": "medio",
                        "impacto_financiero": 0,
                        "mitigation": "Completar análisis con especialista",
                        "responsable": "Inspector Fiscal",
                        "timeline": "Próxima revisión",
                        "indicadores": "Análisis manual completado"
                    }
                ],
                "recomendaciones_especificas": [
                    {
                        "categoria": "técnica",
                        "recomendacion": "Revisar análisis manualmente",
                        "justificacion": "El análisis automático fue limitado",
                        "prioridad": "alta",
                        "timeline": "Inmediato",
                        "responsable": "Equipo técnico"
                    }
                ],
                "cronograma_detallado": {
                    "duracion_total_meses": 12,
                    "fases": [
                        {
                            "fase": "Revisión manual pendiente",
                            "duracion_semanas": 1,
                            "actividades_principales": ["Análisis manual del presupuesto"],
                            "recursos_criticos": ["Especialista MOP"],
                            "dependencias": ["Documentación completa"]
                        }
                    ],
                    "hitos_criticos": ["Análisis manual completado"],
                    "factores_estacionales": "Por determinar",
                    "ruta_critica": "Completar revisión manual"
                }
            },
            "metadata": {
                "chunksProcessed": 0,
                "originalFileSize": processed_content.get("content_length", 0),
                "processingTime": datetime.now().isoformat(),
                "confidence_score": 40,
                "extraction_method": ["basic_analysis"],
                "analysis_type": "basic_fallback"
            }
        }
    
    def _apply_final_corrections(self, analysis_data: Dict[str, Any], validation: Dict[str, Any]) -> Dict[str, Any]:
        """Aplica correcciones finales basadas en validación."""
        
        # Crear estructura final con analysisId
        analysis_id = f"mop_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:17]}"
        
        final_analysis = {
            "analysisId": analysis_id,
            "analysis": analysis_data,
            "metadata": {
                "chunksProcessed": 1,
                "originalFileSize": 0,
                "processingTime": datetime.now().isoformat(),
                "confidence_score": validation.get("confidence_score", 75),
                "validation_warnings": validation.get("warnings", []),
                "validation_errors": validation.get("errors", []),
                "is_valid": validation.get("is_valid", True)
            }
        }
        
        return final_analysis
    
    def _merge_risk_analysis(self, main_analysis: Dict[str, Any], risk_data: Dict[str, Any]) -> Dict[str, Any]:
        """Fusiona análisis de riesgos con el análisis principal."""
        
        # Fusionar riesgos por categoría
        if "analisis_riesgos_detallado" in main_analysis:
            # Agregar riesgos adicionales del análisis específico
            additional_risks = []
            
            for category in ["riesgos_tecnicos", "riesgos_financieros", "riesgos_operacionales", "riesgos_ambientales"]:
                if category in risk_data:
                    for risk in risk_data[category]:
                        additional_risks.append({
                            "categoria": category.replace("riesgos_", ""),
                            "factor": risk.get("factor", ""),
                            "probabilidad": risk.get("probabilidad", "media"),
                            "impacto": risk.get("impacto", "medio"),
                            "impacto_financiero": risk.get("costo_mitigacion", 0),
                            "mitigation": risk.get("mitigacion", ""),
                            "responsable": "Equipo del proyecto",
                            "timeline": "Durante ejecución",
                            "indicadores": "Revisión continua"
                        })
            
            # Agregar riesgos adicionales sin duplicar
            existing_factors = {risk["factor"] for risk in main_analysis["analisis_riesgos_detallado"]}
            for risk in additional_risks:
                if risk["factor"] not in existing_factors:
                    main_analysis["analisis_riesgos_detallado"].append(risk)
        
        return main_analysis
    
    def _merge_provider_analysis(self, main_analysis: Dict[str, Any], provider_data: Dict[str, Any]) -> Dict[str, Any]:
        """Fusiona análisis de proveedores con el análisis principal."""
        
        # Fusionar proveedores por categoría
        all_providers = []
        
        for category in ["proveedores_materiales", "proveedores_equipos", "proveedores_servicios"]:
            if category in provider_data:
                for provider in provider_data[category]:
                    all_providers.append({
                        "nombre": provider.get("empresa", ""),
                        "rut": "",
                        "categoria": category.replace("proveedores_", ""),
                        "region_operacion": ", ".join(provider.get("regiones_atencion", [])),
                        "contacto": provider.get("contacto_estimado", ""),
                        "especialidades": provider.get("productos", []),
                        "experiencia_mop": provider.get("experiencia_mop", ""),
                        "certificaciones": provider.get("ventajas", "")
                    })
        
        # Reemplazar proveedores existentes si hay mejores datos
        if all_providers:
            main_analysis["proveedores_chile_especificos"] = all_providers
        
        return main_analysis
    
    def _extract_items_from_tables(self, tables: List) -> List[Dict]:
        """Extrae items adicionales de tablas cuando no hay suficientes items procesados."""
        
        additional_items = []
        
        for table in tables:
            if isinstance(table, list):
                for row in table:
                    if isinstance(row, dict):
                        # Buscar patrones de items presupuestarios
                        codigo = None
                        descripcion = None
                        precio = 0
                        
                        for key, value in row.items():
                            key_str = str(key).lower()
                            value_str = str(value)
                            
                            # Buscar código MOP
                            if not codigo and re.match(self.mop_patterns['codigo_mop'], value_str):
                                codigo = value_str
                            
                            # Buscar descripción (campo más largo)
                            if not descripcion and len(value_str) > 20 and not value_str.replace('.', '').replace(',', '').isdigit():
                                descripcion = value_str
                            
                            # Buscar precio (números grandes)
                            if 'precio' in key_str or 'total' in key_str or 'subtotal' in key_str:
                                clean_price = self._clean_numeric_value(value_str)
                                if clean_price > precio:
                                    precio = clean_price
                        
                        # Si encontramos datos válidos, crear item
                        if codigo and (descripcion or precio > 0):
                            additional_items.append({
                                "codigo_mop": codigo,
                                "descripcion": descripcion or f"Item {codigo}",
                                "unidad": "",
                                "cantidad": 1,
                                "precio_unitario": precio,
                                "subtotal": precio,
                                "categoria": self._categorize_mop_item(codigo, descripcion or "")
                            })
        
        return additional_items[:5]  # Máximo 5 items adicionales
    
    def _apply_budget_corrections(
        self, 
        analysis_data: Dict[str, Any], 
        processed_content: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Aplica correcciones presupuestarias como tu función JS."""
        
        # Calcular totales reales de items (como tu JS)
        materiales_total = 0
        mano_obra_total = 0
        equipos_total = 0
        
        # Sumar materiales detallados
        for item in analysis_data.get("materiales_detallados", []):
            materiales_total += item.get("subtotal", 0)
        
        # Sumar mano de obra
        for item in analysis_data.get("mano_obra_detallada", []):
            mano_obra_total += item.get("subtotal", 0)
        
        # Sumar equipos
        for item in analysis_data.get("equipos_maquinaria_detallados", []):
            equipos_total += item.get("subtotal", 0)
        
        # Si no hay items detallados, usar totales extraídos del documento
        if materiales_total == 0 and mano_obra_total == 0 and equipos_total == 0:
            financial_totals = processed_content.get("financial_totals", {})
            total_estimado = financial_totals.get("total_bruto", 0)
            
            if total_estimado > 0:
                # Distribución estimada estándar
                materiales_total = total_estimado * 0.45
                mano_obra_total = total_estimado * 0.30
                equipos_total = total_estimado * 0.25
        
        # Aplicar metodología chilena estándar (como tu calcularPresupuestoCompleto JS)
        costos_directos = materiales_total + mano_obra_total + equipos_total
        
        # Gastos generales: 12% sobre costos directos
        gastos_generales = costos_directos * 0.12
        
        # Utilidad: 10% sobre (costos directos + gastos generales)
        base_utilidad = costos_directos + gastos_generales
        utilidad = base_utilidad * 0.10
        
        # Contingencia: 5% sobre costos directos
        contingencia = costos_directos * 0.05
        
        # Subtotal antes de IVA
        subtotal = costos_directos + gastos_generales + utilidad + contingencia
        
        # IVA 19%
        iva = subtotal * 0.19
        total_final = subtotal + iva
        
        # Actualizar análisis con cálculos corregidos
        analysis_data["presupuesto_estimado"] = {
            "total_clp": total_final,
            "materials_percentage": (materiales_total / costos_directos * 100) if costos_directos > 0 else 0,
            "labor_percentage": (mano_obra_total / costos_directos * 100) if costos_directos > 0 else 0,
            "equipment_percentage": (equipos_total / costos_directos * 100) if costos_directos > 0 else 0,
            "overhead_percentage": ((gastos_generales + utilidad + contingencia) / costos_directos * 100) if costos_directos > 0 else 0
        }
        
        # Actualizar desglose detallado
        analysis_data["desglose_costos_detallado"] = {
            "costos_directos": {
                "materiales": materiales_total,
                "mano_obra": mano_obra_total,
                "equipos": equipos_total,
                "subcontratos": 0,
                "total": costos_directos
            },
            "costos_indirectos": {
                "gastos_generales": gastos_generales,
                "utilidad": utilidad,
                "contingencia": contingencia,
                "total": gastos_generales + utilidad + contingencia
            },
            "impuestos": {
                "subtotal": subtotal,
                "iva": iva,
                "total_final": total_final
            }
        }
        
        return analysis_data
    
    def _validate_budget_consistency(self, analysis_data: Dict[str, Any]) -> Dict[str, Any]:
        """Valida consistencia presupuestaria como tu JS validarConsistenciaPresupuesto."""
        
        warnings = []
        errors = []
        
        # Validar coherencia de totales
        presupuesto_total = analysis_data.get("presupuesto_estimado", {}).get("total_clp", 0)
        desglose = analysis_data.get("desglose_costos_detallado", {})
        desglose_total = desglose.get("impuestos", {}).get("total_final", 0)
        
        if abs(presupuesto_total - desglose_total) > 1000:
            warnings.append(f"Diferencia en totales: presupuesto={presupuesto_total:,.0f} vs desglose={desglose_total:,.0f}")
        
        # Validar IVA
        subtotal = desglose.get("impuestos", {}).get("subtotal", 0)
        iva = desglose.get("impuestos", {}).get("iva", 0)
        iva_esperado = subtotal * 0.19
        
        if abs(iva - iva_esperado) > 100:
            errors.append(f"IVA incorrecto: {iva:,.0f} vs esperado {iva_esperado:,.0f}")
        
        # Validar items individuales
        for item in analysis_data.get("materiales_detallados", []):
            cantidad = item.get("cantidad", 0)
            precio = item.get("precio_unitario", 0)
            subtotal = item.get("subtotal", 0)
            
            if cantidad > 0 and precio > 0:
                subtotal_esperado = cantidad * precio
                if abs(subtotal - subtotal_esperado) > 100:
                    warnings.append(f"Cálculo item {item.get('codigo_mop', 'N/A')}: {subtotal:,.0f} vs {subtotal_esperado:,.0f}")
        
        return {
            "is_valid": len(errors) == 0,
            "warnings": warnings,
            "errors": errors,
            "confidence_score": max(0, 100 - len(errors) * 25 - len(warnings) * 10)
        }
    
    def _build_risk_analysis_prompt(self, chunks: List[Dict]) -> str:
        """Prompt específico para análisis de riesgos."""
        
        context = chunks[0]["content"][:4000] if chunks else "Contenido no disponible"
        
        return f"""
Eres un experto en gestión de riesgos para proyectos de infraestructura MOP Chile.

CONTEXTO DEL PROYECTO:
{context}

Analiza los riesgos específicos de este proyecto MOP considerando:
- Tipo de obra y complejidad técnica
- Ubicación geográfica y condiciones climáticas
- Acceso al sitio de obra
- Disponibilidad de recursos locales
- Aspectos regulatorios y permisos
- Condiciones del mercado chileno actual

RESPONDE EN JSON:
{{
    "riesgos_tecnicos": [
        {{
            "factor": "descripción específica",
            "probabilidad": "alta|media|baja",
            "impacto": "alto|medio|bajo",
            "mitigacion": "estrategia específica",
            "costo_mitigacion": number
        }}
    ],
    "riesgos_financieros": [...],
    "riesgos_operacionales": [...],
    "riesgos_ambientales": [...],
    "factores_climaticos": "análisis específico de la región",
    "recomendaciones_prioritarias": ["string"]
}}
"""
    
    def _build_provider_analysis_prompt(self, chunks: List[Dict]) -> str:
        """Prompt específico para análisis de proveedores."""
        
        context = chunks[0]["content"][:4000] if chunks else "Contenido no disponible"
        
        return f"""
Eres un experto en el mercado de proveedores de construcción en Chile.

PROYECTO A ANALIZAR:
{context}

Identifica proveedores chilenos específicos para este proyecto considerando:
- Región del proyecto y proveedores locales
- Tipo de materiales y equipos requeridos
- Empresas con experiencia MOP comprobada
- Capacidad de suministro y distribución
- Competitividad de precios por región

RESPONDE EN JSON:
{{
    "proveedores_materiales": [
        {{
            "empresa": "nombre real de empresa chilena",
            "productos": ["lista de productos"],
            "regiones_atencion": ["regiones donde opera"],
            "experiencia_mop": "años de experiencia",
            "contacto_estimado": "información de contacto",
            "ventajas": "fortalezas específicas"
        }}
    ],
    "proveedores_equipos": [...],
    "proveedores_servicios": [...],
    "recomendaciones_logisticas": "string - consideraciones de transporte y almacenamiento",
    "analisis_mercado_regional": "string - condiciones específicas de la región"
}}
"""

    async def _execute_claude_prompt(self, prompt: str) -> Optional[Dict[str, Any]]:
        """Ejecuta prompt con Claude con reintentos y manejo de errores."""
        
        for attempt in range(self.max_retries):
            try:
                response = self.client.messages.create(
                    model="claude-3-haiku-20240307",
                    max_tokens=4000,
                    temperature=0.1,
                    messages=[{"role": "user", "content": prompt}]
                )
                
                response_text = response.content[0].text.strip()
                
                # Extraer JSON de la respuesta
                json_start = response_text.find('{')
                json_end = response_text.rfind('}') + 1
                
                if json_start >= 0 and json_end > json_start:
                    json_content = response_text[json_start:json_end]
                    parsed_data = json.loads(json_content)
                    
                    return {
                        "success": True,
                        "data": parsed_data,
                        "raw_response": response_text
                    }
                else:
                    logger.warning(f"No se encontró JSON válido en intento {attempt + 1}")
                    
            except json.JSONDecodeError as e:
                logger.warning(f"Error JSON en intento {attempt + 1}: {e}")
                if attempt == self.max_retries - 1:
                    return {"success": False, "error": f"Error parsing JSON: {e}"}
                    
            except Exception as e:
                logger.error(f"Error Claude API intento {attempt + 1}: {e}")
                if attempt == self.max_retries - 1:
                    return {"success": False, "error": str(e)}
                    
                await asyncio.sleep(2 ** attempt)  # Backoff exponencial
        
        return None
    
    def _create_fallback_response(self, error_msg: str, extracted_content: Dict) -> Dict[str, Any]:
        """Crea respuesta de fallback cuando Claude falla."""
        
        analysis_id = f"fallback_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Intentar extraer información básica del contenido
        basic_info = self._extract_basic_info_fallback(extracted_content)
        
        return {
            "analysisId": analysis_id,
            "analysis": {
                "resumen_ejecutivo": f"Análisis limitado debido a error técnico: {error_msg}. Se logró procesar información básica del documento.",
                "presupuesto_estimado": {
                    "total_clp": basic_info.get("estimated_total", 0),
                    "materials_percentage": 45,
                    "labor_percentage": 30,
                    "equipment_percentage": 25,
                    "overhead_percentage": 35
                },
                "proyecto_info": basic_info.get("project_info", {}),
                "materiales_detallados": basic_info.get("materials", []),
                "mano_obra_detallada": [],
                "equipos_maquinaria_detallados": [],
                "proveedores_chile_especificos": [],
                "analisis_riesgos_detallado": [
                    {
                        "categoria": "técnico",
                        "factor": "Análisis incompleto por limitaciones técnicas",
                        "probabilidad": "alta",
                        "impacto": "medio",
                        "impacto_financiero": 0,
                        "mitigation": "Revisar documento manualmente con especialista MOP",
                        "responsable": "Inspector Fiscal",
                        "timeline": "Inmediato",
                        "indicadores": "Revisión manual completada"
                    }
                ],
                "recomendaciones_especificas": [
                    {
                        "categoria": "técnica",
                        "recomendacion": "Procesar documento con herramientas especializadas de OCR",
                        "justificacion": "Mejorará calidad de extracción de datos",
                        "prioridad": "alta",
                        "timeline": "Antes de continuar análisis",
                        "responsable": "Equipo técnico"
                    }
                ],
                "cronograma_detallado": {
                    "duracion_total_meses": 12,
                    "fases": [
                        {
                            "fase": "Análisis manual requerido",
                            "duracion_semanas": 2,
                            "actividades_principales": ["Revisión manual del documento"],
                            "recursos_criticos": ["Especialista MOP"],
                            "dependencias": ["Acceso a documento fuente"]
                        }
                    ],
                    "hitos_criticos": ["Análisis manual completado"],
                    "factores_estacionales": "Por determinar según análisis manual",
                    "ruta_critica": "Completar análisis manual del presupuesto"
                }
            },
            "metadata": {
                "chunksProcessed": 0,
                "originalFileSize": extracted_content.get("extraction_metadata", {}).get("file_size", 0),
                "processingTime": datetime.now().isoformat(),
                "confidence_score": 25,
                "extraction_method": ["fallback"],
                "analysis_type": "limited_fallback",
                "error_details": error_msg
            }
        }
    
    def _extract_basic_info_fallback(self, extracted_content: Dict) -> Dict[str, Any]:
        """Extrae información básica cuando Claude falla."""
        
        text = extracted_content.get("text_content", "")
        
        # Buscar totales numéricos básicos
        amounts = re.findall(r'[\d.,]+', text)
        numeric_amounts = []
        for amount in amounts:
            try:
                clean_amount = self._clean_numeric_value(amount)
                if 1000000 < clean_amount < 10000000000:  # Rango razonable para proyectos MOP
                    numeric_amounts.append(clean_amount)
            except:
                continue
        
        estimated_total = max(numeric_amounts) if numeric_amounts else 0
        
        # Información básica del proyecto
        project_info = {
            "nombre": "Proyecto MOP - Requiere análisis manual",
            "region": "Por determinar",
            "comuna": "Por determinar", 
            "tipo_obra": "Infraestructura pública",
            "etapa": "Por determinar"
        }
        
        # Si hay texto, intentar extraer algo
        if "conservación" in text.lower():
            project_info["tipo_obra"] = "Conservación de caminos"
        elif "construcción" in text.lower():
            project_info["tipo_obra"] = "Construcción"
        elif "mejoramiento" in text.lower():
            project_info["tipo_obra"] = "Mejoramiento"
            
        if "los ríos" in text.lower():
            project_info["region"] = "Región de Los Ríos"
            
        return {
            "estimated_total": estimated_total,
            "project_info": project_info,
            "materials": []
        }    


# Función de conveniencia para uso externo
async def analyze_mop_document(extracted_content: Dict[str, Any], analysis_depth: str = "full") -> Dict[str, Any]:
    """
    Función principal que reemplaza tu análisis actual.
    Mantiene la misma interfaz pero usa el analizador mejorado.
    """
    from app.config.settings import get_settings
    
    settings = get_settings()
    analyzer = ClaudeAnalyzer(settings.ANTHROPIC_API_KEY)
    
    return await analyzer.analyze_mop_document_detailed(extracted_content, analysis_depth)

if __name__ == "__main__":
    # Test básico
    print("Claude Analyzer loaded successfully!")
    
    # Test de configuración
    try:
        analyzer = ClaudeAnalyzer()
        print(f"Claude model: {analyzer.model}")
        print(f"Max tokens: {analyzer.max_tokens}")
    except Exception as e:
        print(f"Error inicializando: {e}")
        print("Verifica tu ANTHROPIC_API_KEY en .env")
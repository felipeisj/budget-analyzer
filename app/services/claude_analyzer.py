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
    Analizador principal usando Claude AI para procesamiento de contenido MOP.
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.client = AsyncAnthropic(api_key=self.settings.ANTHROPIC_API_KEY)
        
        # Configuración de Claude
        self.model = self.settings.CLAUDE_MODEL
        self.max_tokens = self.settings.CLAUDE_MAX_TOKENS
        self.temperature = self.settings.CLAUDE_TEMPERATURE
    
    async def analyze_mop_content(
        self, 
        extracted_content: Dict[str, Any],
        analysis_type: str = "full"
    ) -> Dict[str, Any]:
        """
        Analiza contenido MOP extraído y genera respuesta estructurada.
        
        Args:
            extracted_content: Contenido extraído por el PDF extractor
            analysis_type: Tipo de análisis ("full", "quick", "budget_only")
            
        Returns:
            Dict con análisis completo formato API response
        """
        logger.info(f"Iniciando análisis Claude tipo: {analysis_type}")
        
        try:
            # 1. Preparar contenido para análisis
            prepared_content = self._prepare_content_for_analysis(extracted_content)
            
            if not prepared_content["text_content"]:
                raise ValueError("No hay contenido de texto suficiente para analizar")
            
            # 2. Generar prompts según tipo de análisis
            prompts = self._build_analysis_prompts(prepared_content, analysis_type)
            
            # 3. Procesar con Claude en chunks si es necesario
            claude_results = {}
            for prompt_name, prompt_content in prompts.items():
                logger.info(f"Procesando prompt: {prompt_name}")
                
                result = await self._process_with_claude(prompt_content)
                claude_results[prompt_name] = result
                
                # Pequeña pausa entre requests para evitar rate limiting
                await asyncio.sleep(0.5)
            
            # 4. Consolidar resultados
            final_analysis = await self._consolidate_analysis(
                claude_results, 
                extracted_content,
                analysis_type
            )
            
            # 5. Validar y limpiar resultado
            validated_analysis = self._validate_analysis(final_analysis)
            
            logger.info("Análisis Claude completado exitosamente")
            return validated_analysis
            
        except Exception as e:
            logger.error(f"Error en análisis Claude: {e}")
            return self._create_error_response(str(e), extracted_content)
    
    def _prepare_content_for_analysis(self, extracted_content: Dict) -> Dict:
        """Prepara y limpia el contenido para análisis."""
        # Combinar todo el texto disponible
        text_parts = []
        
        # Texto principal
        if extracted_content.get("text_content"):
            text_parts.append(extracted_content["text_content"])
        
        # Información de tablas estructurada
        if extracted_content.get("tables"):
            table_text = self._format_tables_as_text(extracted_content["tables"])
            text_parts.append(f"\n=== TABLAS ESTRUCTURADAS ===\n{table_text}")
        
        # Items presupuestarios ya extraídos
        if extracted_content.get("budget_items"):
            items_text = self._format_budget_items_as_text(extracted_content["budget_items"])
            text_parts.append(f"\n=== ITEMS PRESUPUESTARIOS EXTRAÍDOS ===\n{items_text}")
        
        combined_text = "\n".join(text_parts)
        
        return {
            "text_content": combined_text,
            "total_length": len(combined_text),
            "needs_chunking": len(combined_text) > self.settings.TEXT_CHUNK_SIZE,
            "metadata": extracted_content.get("extraction_metadata", {})
        }
    
    def _format_tables_as_text(self, tables: List[Dict]) -> str:
        """Formatea tablas como texto estructurado."""
        formatted = []
        
        for idx, table in enumerate(tables):
            table_text = [f"TABLA {idx + 1} (Página {table.get('page', 'N/A')}):"]
            
            if table.get("headers"):
                table_text.append("Headers: " + " | ".join(str(h) for h in table["headers"]))
            
            if table.get("items"):
                table_text.append("Items presupuestarios:")
                for item in table["items"]:
                    item_line = f"  - {item.get('codigo_mop', 'N/A')}: {item.get('descripcion', 'N/A')} | {item.get('cantidad', 0)} {item.get('unidad', '')} | ${item.get('precio_unitario', 0):,.0f} | Total: ${item.get('subtotal', 0):,.0f}"
                    table_text.append(item_line)
            
            formatted.append("\n".join(table_text))
        
        return "\n\n".join(formatted)
    
    def _format_budget_items_as_text(self, items: List[Dict]) -> str:
        """Formatea items presupuestarios como texto."""
        formatted = []
        
        for item in items:
            item_text = f"{item.get('codigo_mop', 'N/A')} | {item.get('descripcion', 'N/A')} | {item.get('cantidad', 0)} {item.get('unidad', '')} | Precio Unit: ${item.get('precio_unitario', 0):,.0f} | Total: ${item.get('subtotal', 0):,.0f}"
            formatted.append(item_text)
        
        return "\n".join(formatted)
    
    def _build_analysis_prompts(self, prepared_content: Dict, analysis_type: str) -> Dict[str, str]:
        """Construye prompts específicos para diferentes tipos de análisis."""
        
        base_context = f"""
Eres un experto en análisis de licitaciones y presupuestos del Ministerio de Obras Públicas (MOP) de Chile.

DOCUMENTO A ANALIZAR:
{prepared_content['text_content'][:self.settings.TEXT_CHUNK_SIZE]}

INSTRUCCIONES GENERALES:
- Analiza este documento de licitación MOP chileno
- Extrae información presupuestaria estructurada
- Identifica códigos MOP estándar (formato 7.xxx.xxx)
- Valida cálculos matemáticos (IVA 19%)
- Clasifica costos por categoría (materiales, mano de obra, equipos, overhead)
- Responde SOLO en formato JSON válido
"""
        
        prompts = {}
        
        if analysis_type in ["full", "budget_only"]:
            prompts["budget_analysis"] = f"""
{base_context}

EXTRAE LA SIGUIENTE INFORMACIÓN PRESUPUESTARIA:

Responde en este formato JSON exacto:
{{
    "proyecto_info": {{
        "nombre": "string",
        "region": "string",
        "comuna": "string", 
        "tipo_obra": "string",
        "coordenadas_utm": "string"
    }},
    "items_presupuestarios": [
        {{
            "codigo_mop": "string",
            "descripcion": "string",
            "unidad": "string",
            "cantidad": number,
            "precio_unitario": number,
            "subtotal": number,
            "categoria": "materials|labor|equipment|overhead"
        }}
    ],
    "resumen_costos": {{
        "total_neto": number,
        "iva": number,
        "total_bruto": number,
        "cantidad_items": number
    }},
    "validacion_matematica": {{
        "calculo_iva_correcto": boolean,
        "suma_items_coincide": boolean,
        "errores_detectados": ["string"]
    }}
}}

IMPORTANTE:
- Solo incluir items con códigos MOP válidos (formato 7.xxx.xxx)
- Verificar que subtotal = cantidad × precio_unitario
- Verificar que total_bruto = total_neto + iva
- IVA debe ser 19% del total_neto
"""

        if analysis_type == "full":
            prompts["market_analysis"] = f"""
{base_context}

GENERA ANÁLISIS DE MERCADO Y RECOMENDACIONES:

Responde en este formato JSON exacto:
{{
    "analisis_costos": {{
        "materials_percentage": number,
        "labor_percentage": number, 
        "equipment_percentage": number,
        "overhead_percentage": number,
        "distribucion_coherente": boolean
    }},
    "materiales_detallados": [
        {{
            "categoria": "string",
            "descripcion": "string", 
            "cantidad_estimada": "string",
            "costo_estimado_clp": number,
            "proveedor_sugerido": "string"
        }}
    ],
    "mano_obra": [
        {{
            "especialidad": "string",
            "cantidad_personas": number,
            "dias_trabajo": number,
            "costo_diario": number,
            "costo_total": number
        }}
    ],
    "equipos_maquinaria": [
        {{
            "tipo_equipo": "string",
            "cantidad": number,
            "dias_uso": number,
            "costo_diario": number,
            "costo_total": number
        }}
    ]
}}
"""
            
            prompts["recommendations"] = f"""
{base_context}

GENERA ANÁLISIS DE RIESGOS Y RECOMENDACIONES:

Responde en este formato JSON exacto:
{{
    "analisis_riesgos": [
        {{
            "tipo_riesgo": "tecnico|financiero|ambiental|regulatorio",
            "descripcion": "string",
            "probabilidad": "alta|media|baja",
            "impacto": "alto|medio|bajo",
            "medida_mitigacion": "string"
        }}
    ],
    "recomendaciones": [
        {{
            "categoria": "costos|cronograma|proveedores|calidad",
            "recomendacion": "string",
            "justificacion": "string",
            "prioridad": "alta|media|baja"
        }}
    ],
    "proveedores_chile": [
        {{
            "categoria": "string",
            "nombre_empresa": "string",
            "region": "string",
            "especialidad": "string",
            "contacto_estimado": "string"
        }}
    ],
    "cronograma_estimado": "string"
}}
"""
        
        return prompts
    
    async def _process_with_claude(self, prompt: str) -> Dict:
        """Procesa un prompt individual con Claude."""
        try:
            message = await self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )
            
            response_text = message.content[0].text
            
            # Intentar parsear como JSON
            try:
                result = json.loads(response_text)
                return {"success": True, "data": result}
            except json.JSONDecodeError:
                # Si no es JSON válido, extraer JSON del texto
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    try:
                        result = json.loads(json_match.group())
                        return {"success": True, "data": result}
                    except:
                        pass
                
                return {"success": False, "error": "Invalid JSON response", "raw_text": response_text}
            
        except Exception as e:
            logger.error(f"Error procesando con Claude: {e}")
            return {"success": False, "error": str(e)}
    
    async def _consolidate_analysis(
        self, 
        claude_results: Dict, 
        original_content: Dict,
        analysis_type: str
    ) -> Dict:
        """Consolida todos los resultados en formato de respuesta final."""
        
        # Generar ID único para el análisis
        analysis_id = f"mop_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Estructura base de respuesta
        consolidated = {
            "analysisId": analysis_id,
            "analysis": {
                "resumen_ejecutivo": "",
                "presupuesto_estimado": {
                    "total_clp": 0,
                    "materials_percentage": 0,
                    "labor_percentage": 0,
                    "equipment_percentage": 0,
                    "overhead_percentage": 0
                },
                "materiales_detallados": [],
                "mano_obra": [],
                "equipos_maquinaria": [],
                "proveedores_chile": [],
                "analisis_riesgos": [],
                "recomendaciones": [],
                "cronograma_estimado": "Por definir según análisis detallado"
            },
            "metadata": {
                "chunksProcessed": 1,
                "originalFileSize": 0,
                "processingTime": datetime.now().isoformat(),
                "confidence_score": 0.0
            }
        }
        
        # Consolidar información presupuestaria
        if "budget_analysis" in claude_results and claude_results["budget_analysis"]["success"]:
            budget_data = claude_results["budget_analysis"]["data"]
            
            # Información del proyecto
            if "proyecto_info" in budget_data:
                proyecto = budget_data["proyecto_info"]
                consolidated["analysis"]["resumen_ejecutivo"] = f"Proyecto: {proyecto.get('nombre', 'N/A')} en {proyecto.get('region', 'N/A')}, {proyecto.get('comuna', 'N/A')}. Tipo de obra: {proyecto.get('tipo_obra', 'N/A')}."
            
            # Presupuesto estimado
            if "resumen_costos" in budget_data:
                costos = budget_data["resumen_costos"]
                consolidated["analysis"]["presupuesto_estimado"]["total_clp"] = costos.get("total_bruto", 0)
        
        # Consolidar análisis de mercado
        if "market_analysis" in claude_results and claude_results["market_analysis"]["success"]:
            market_data = claude_results["market_analysis"]["data"]
            
            # Distribución de costos
            if "analisis_costos" in market_data:
                costos = market_data["analisis_costos"]
                consolidated["analysis"]["presupuesto_estimado"].update({
                    "materials_percentage": costos.get("materials_percentage", 0),
                    "labor_percentage": costos.get("labor_percentage", 0),
                    "equipment_percentage": costos.get("equipment_percentage", 0),
                    "overhead_percentage": costos.get("overhead_percentage", 0)
                })
            
            # Detalles de materiales, mano de obra y equipos
            for key in ["materiales_detallados", "mano_obra", "equipos_maquinaria"]:
                if key in market_data:
                    consolidated["analysis"][key] = market_data[key]
        
        # Consolidar recomendaciones
        if "recommendations" in claude_results and claude_results["recommendations"]["success"]:
            rec_data = claude_results["recommendations"]["data"]
            
            for key in ["analisis_riesgos", "recomendaciones", "proveedores_chile"]:
                if key in rec_data:
                    consolidated["analysis"][key] = rec_data[key]
            
            if "cronograma_estimado" in rec_data:
                consolidated["analysis"]["cronograma_estimado"] = rec_data["cronograma_estimado"]
        
        # Calcular metadata
        consolidated["metadata"].update({
            "chunksProcessed": len(claude_results),
            "originalFileSize": original_content.get("extraction_metadata", {}).get("file_size", 0),
            "confidence_score": self._calculate_analysis_confidence(claude_results, consolidated)
        })
        
        return consolidated
    
    def _calculate_analysis_confidence(self, claude_results: Dict, consolidated: Dict) -> float:
        """Calcula score de confianza del análisis."""
        score = 0.0
        
        # Éxito de prompts
        successful_prompts = sum(1 for result in claude_results.values() if result.get("success", False))
        total_prompts = len(claude_results)
        
        if total_prompts > 0:
            score += (successful_prompts / total_prompts) * 0.4
        
        # Completitud de datos
        analysis = consolidated.get("analysis", {})
        
        if analysis.get("presupuesto_estimado", {}).get("total_clp", 0) > 0:
            score += 0.2
        
        if len(analysis.get("materiales_detallados", [])) > 0:
            score += 0.1
        
        if len(analysis.get("analisis_riesgos", [])) > 0:
            score += 0.1
        
        if len(analysis.get("recomendaciones", [])) > 0:
            score += 0.1
        
        if analysis.get("resumen_ejecutivo", ""):
            score += 0.1
        
        return min(1.0, score)
    
    def _validate_analysis(self, analysis: Dict) -> Dict:
        """Valida y limpia el análisis final."""
        # Validar rangos de porcentajes
        presupuesto = analysis.get("analysis", {}).get("presupuesto_estimado", {})
        
        total_percentage = (
            presupuesto.get("materials_percentage", 0) +
            presupuesto.get("labor_percentage", 0) +
            presupuesto.get("equipment_percentage", 0) +
            presupuesto.get("overhead_percentage", 0)
        )
        
        # Si los porcentajes no suman ~100%, normalizarlos
        if total_percentage > 0 and abs(total_percentage - 100) > 5:
            factor = 100 / total_percentage
            presupuesto["materials_percentage"] = round(presupuesto.get("materials_percentage", 0) * factor, 1)
            presupuesto["labor_percentage"] = round(presupuesto.get("labor_percentage", 0) * factor, 1)
            presupuesto["equipment_percentage"] = round(presupuesto.get("equipment_percentage", 0) * factor, 1)
            presupuesto["overhead_percentage"] = round(presupuesto.get("overhead_percentage", 0) * factor, 1)
        
        # Validar montos
        if presupuesto.get("total_clp", 0) < 0:
            presupuesto["total_clp"] = 0
        
        return analysis
    
    def _create_error_response(self, error_message: str, original_content: Dict = None) -> Dict:
        """Crea respuesta de error estructurada."""
        analysis_id = f"error_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        return {
            "analysisId": analysis_id,
            "error": error_message,
            "analysis": {
                "resumen_ejecutivo": f"Error en el análisis: {error_message}",
                "presupuesto_estimado": {
                    "total_clp": 0,
                    "materials_percentage": 0,
                    "labor_percentage": 0,
                    "equipment_percentage": 0,
                    "overhead_percentage": 0
                },
                "materiales_detallados": [],
                "mano_obra": [],
                "equipos_maquinaria": [],
                "proveedores_chile": [],
                "analisis_riesgos": [{
                    "tipo_riesgo": "tecnico",
                    "descripcion": "Error en procesamiento del documento",
                    "probabilidad": "alta",
                    "impacto": "alto",
                    "medida_mitigacion": "Revisar formato del documento y volver a intentar"
                }],
                "recomendaciones": [{
                    "categoria": "proceso",
                    "recomendacion": "Verificar que el PDF contenga texto extraíble y tablas presupuestarias",
                    "justificacion": "Error durante el análisis del contenido",
                    "prioridad": "alta"
                }],
                "cronograma_estimado": "No disponible debido a error en análisis"
            },
            "metadata": {
                "chunksProcessed": 0,
                "originalFileSize": original_content.get("extraction_metadata", {}).get("file_size", 0) if original_content else 0,
                "processingTime": datetime.now().isoformat(),
                "confidence_score": 0.0
            }
        }


# Función de conveniencia para uso externo
async def analyze_mop_document(extracted_content: Dict, analysis_type: str = "full") -> Dict:
    """
    Función principal para analizar contenido MOP extraído.
    
    Args:
        extracted_content: Contenido extraído por pdf_extractor
        analysis_type: Tipo de análisis ("full", "quick", "budget_only")
        
    Returns:
        Dict con análisis completo en formato API response
    """
    analyzer = ClaudeAnalyzer()
    return await analyzer.analyze_mop_content(extracted_content, analysis_type)


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
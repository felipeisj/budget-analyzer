# app/services/pdf_extractor.py
"""
Extractor PDF mejorado que soluciona el problema de extracción limitada.
Encuentra TODOS los items presupuestarios usando múltiples métodos.
"""

import camelot
import pandas as pd
import re
from typing import Dict, List, Any
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class PDFExtractor:
    """Extractor mejorado para documentos MOP chilenos."""
    
    def __init__(self):
        self.mop_item_patterns = [
            r'7\.\d{3}\.\d+[a-zA-Z]?',  # Códigos MOP estándar
            r'[A-Z]\d+\.\d+[a-zA-Z]?',   # Códigos alternativos
            r'ÍTEM.*?7\.\d{3}',          # ÍTEM seguido de código
            r'Item.*?7\.\d{3}'           # Item seguido de código
        ]
        
        self.price_patterns = [
            r'\$\s*[\d.,]+',             # Precios con $
            r'[\d.,]+\s*\$',             # Precios con $ al final
            r'TOTAL\s*\$?\s*[\d.,]+'     # Totales
        ]
        
        # Configuración optimizada para documentos MOP
        self.camelot_config = {
            'pages': 'all',
            'flavor': 'lattice',  # Mejor para tablas con bordes
            'table_areas': None,   # Detectar automáticamente
            'columns': None,       # Detectar automáticamente
            'split_text': True,    # Dividir texto en celdas
            'strip_text': '\n',    # Limpiar saltos de línea
            'row_tol': 2,         # Tolerancia para filas
            'column_tol': 0       # Tolerancia para columnas
        }
        
        # Configuración alternativa para tablas sin bordes
        self.camelot_stream_config = {
            'pages': 'all',
            'flavor': 'stream',
            'table_areas': None,
            'columns': None,
            'edge_tol': 500,      # Tolerancia para bordes
            'row_tol': 2,
            'column_tol': 0
        }

    def extract_enhanced_budget_data(self, pdf_path: str) -> Dict[str, Any]:
        """
        Extracción mejorada que debería encontrar TODOS los items presupuestarios.
        """
        
        logger.info(f"Iniciando extracción mejorada de: {pdf_path}")
        
        try:
            # 1. EXTRACCIÓN CON MÚLTIPLES MÉTODOS
            tables_lattice = self._extract_tables_lattice(pdf_path)
            tables_stream = self._extract_tables_stream(pdf_path)
            text_items = self._extract_text_items(pdf_path)
            
            # 2. CONSOLIDAR TODOS LOS ITEMS ENCONTRADOS
            all_items = []
            all_items.extend(self._process_lattice_tables(tables_lattice))
            all_items.extend(self._process_stream_tables(tables_stream))
            all_items.extend(self._process_text_items(text_items))
            
            # 3. DEDUPLICAR Y VALIDAR
            unique_items = self._deduplicate_items(all_items)
            validated_items = self._validate_items(unique_items)
            
            # 4. EXTRAER INFORMACIÓN DEL PROYECTO
            project_info = self._extract_project_info(pdf_path)
            
            # 5. CALCULAR TOTALES
            totals = self._calculate_totals(validated_items)
            
            result = {
                "items_found": len(validated_items),
                "items_detail": validated_items,
                "project_info": project_info,
                "financial_totals": totals,
                "extraction_method": ["lattice", "stream", "text_analysis"],
                "extraction_success": True
            }
            
            logger.info(f"✅ Extracción exitosa: {len(validated_items)} items encontrados")
            return result
            
        except Exception as e:
            logger.error(f"❌ Error en extracción mejorada: {e}")
            return self._fallback_extraction(pdf_path)

    def _extract_tables_lattice(self, pdf_path: str) -> List:
        """Extrae tablas usando método lattice (para tablas con bordes)."""
        
        try:
            logger.info("Extrayendo tablas con método lattice...")
            tables = camelot.read_pdf(pdf_path, **self.camelot_config)
            logger.info(f"Encontradas {len(tables)} tablas con lattice")
            return tables
        except Exception as e:
            logger.warning(f"Error en extracción lattice: {e}")
            return []

    def _extract_tables_stream(self, pdf_path: str) -> List:
        """Extrae tablas usando método stream (para tablas sin bordes)."""
        
        try:
            logger.info("Extrayendo tablas con método stream...")
            tables = camelot.read_pdf(pdf_path, **self.camelot_stream_config)
            logger.info(f"Encontradas {len(tables)} tablas con stream")
            return tables
        except Exception as e:
            logger.warning(f"Error en extracción stream: {e}")
            return []

    def _extract_text_items(self, pdf_path: str) -> List[str]:
        """Extrae items directamente del texto cuando las tablas fallan."""
        
        try:
            import PyPDF2
            
            text_content = []
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                
                for page_num, page in enumerate(pdf_reader.pages):
                    page_text = page.extract_text()
                    
                    # Buscar líneas que contienen códigos MOP
                    for line in page_text.split('\n'):
                        for pattern in self.mop_item_patterns:
                            if re.search(pattern, line):
                                text_content.append(line.strip())
                                break
            
            logger.info(f"Encontradas {len(text_content)} líneas con códigos MOP en texto")
            return text_content
            
        except Exception as e:
            logger.warning(f"Error en extracción de texto: {e}")
            return []

    def _process_lattice_tables(self, tables: List) -> List[Dict]:
        """Procesa tablas extraídas con método lattice."""
        
        items = []
        
        for i, table in enumerate(tables):
            try:
                df = table.df
                logger.debug(f"Procesando tabla lattice {i}, dimensiones: {df.shape}")
                
                # Buscar columnas relevantes
                items.extend(self._extract_items_from_dataframe(df, f"lattice_table_{i}"))
                
            except Exception as e:
                logger.warning(f"Error procesando tabla lattice {i}: {e}")
        
        return items

    def _process_stream_tables(self, tables: List) -> List[Dict]:
        """Procesa tablas extraídas con método stream."""
        
        items = []
        
        for i, table in enumerate(tables):
            try:
                df = table.df
                logger.debug(f"Procesando tabla stream {i}, dimensiones: {df.shape}")
                
                items.extend(self._extract_items_from_dataframe(df, f"stream_table_{i}"))
                
            except Exception as e:
                logger.warning(f"Error procesando tabla stream {i}: {e}")
        
        return items

    def _extract_items_from_dataframe(self, df: pd.DataFrame, source: str) -> List[Dict]:
        """Extrae items presupuestarios de un DataFrame."""
        
        items = []
        
        try:
            # Convertir todo a string para búsqueda
            df_str = df.astype(str)
            
            for idx, row in df_str.iterrows():
                # Buscar código MOP en cualquier columna
                mop_code = None
                description = None
                quantity = None
                unit = None
                unit_price = None
                total = None
                
                row_text = ' '.join(row.values)
                
                # Buscar código MOP
                for pattern in self.mop_item_patterns:
                    match = re.search(pattern, row_text)
                    if match:
                        mop_code = match.group(0)
                        break
                
                if not mop_code:
                    continue
                
                # Extraer descripción (texto más largo sin números)
                for cell in row.values:
                    if len(cell) > 20 and not re.search(r'^\d+[.,]?\d*$', cell.strip()):
                        if not any(char.isdigit() for char in cell[:10]):  # Descripción no empieza con números
                            description = cell.strip()
                            break
                
                # Extraer valores numéricos
                numeric_values = []
                for cell in row.values:
                    if re.search(r'[\d.,]+', cell):
                        cleaned = self._clean_numeric_value(cell)
                        if cleaned > 0:
                            numeric_values.append(cleaned)
                
                # Asignar valores basado en rangos típicos MOP
                for value in numeric_values:
                    if 0 < value < 10000 and not quantity:  # Rango típico de cantidad
                        quantity = value
                    elif 10 < value < 1000000 and not unit_price:  # Rango típico precio unitario
                        unit_price = value
                    elif value > 1000 and not total:  # Rango típico total
                        total = value
                
                # Buscar unidad (m3, m2, etc.)
                unit_match = re.search(r'\b(m3|m2|ml|kg|ton|gl|uni|día|hr|lts)\b', row_text.lower())
                if unit_match:
                    unit = unit_match.group(1)
                
                # Si tenemos suficiente información, crear el item
                if mop_code and (description or total):
                    item = {
                        "codigo_mop": mop_code,
                        "descripcion": description or f"Item {mop_code}",
                        "cantidad": quantity or 0,
                        "unidad": unit or "uni",
                        "precio_unitario": unit_price or 0,
                        "subtotal": total or (quantity * unit_price if quantity and unit_price else 0),
                        "source": source,
                        "row_index": idx
                    }
                    
                    items.append(item)
                    logger.debug(f"Item extraído: {mop_code} - {description[:30] if description else 'N/A'}")
        
        except Exception as e:
            logger.warning(f"Error extrayendo items de DataFrame: {e}")
        
        return items

    def _process_text_items(self, text_lines: List[str]) -> List[Dict]:
        """Procesa items encontrados en texto plano."""
        
        items = []
        
        for i, line in enumerate(text_lines):
            try:
                # Extraer código MOP
                mop_code = None
                for pattern in self.mop_item_patterns:
                    match = re.search(pattern, line)
                    if match:
                        mop_code = match.group(0)
                        break
                
                if not mop_code:
                    continue
                
                # Extraer descripción (texto después del código)
                description_match = re.search(rf'{re.escape(mop_code)}\s*(.+?)(?:\d|$)', line)
                description = description_match.group(1).strip() if description_match else f"Item {mop_code}"
                
                # Extraer valores numéricos
                prices = re.findall(r'[\d.,]+', line)
                numeric_values = [self._clean_numeric_value(p) for p in prices if self._clean_numeric_value(p) > 0]
                
                # Crear item básico
                item = {
                    "codigo_mop": mop_code,
                    "descripcion": description,
                    "cantidad": numeric_values[0] if len(numeric_values) > 0 else 0,
                    "unidad": "uni",
                    "precio_unitario": numeric_values[1] if len(numeric_values) > 1 else 0,
                    "subtotal": numeric_values[-1] if numeric_values else 0,  # Último número suele ser total
                    "source": "text_extraction",
                    "line_index": i
                }
                
                items.append(item)
                logger.debug(f"Item de texto: {mop_code} - {description[:30]}")
                
            except Exception as e:
                logger.warning(f"Error procesando línea de texto {i}: {e}")
        
        return items

    def _clean_numeric_value(self, value: str) -> float:
        """Limpia y convierte valores numéricos chilenos."""
        
        if not isinstance(value, str):
            return 0
        
        # Remover símbolos y espacios
        cleaned = re.sub(r'[^\d.,]', '', value)
        
        if not cleaned:
            return 0
        
        try:
            # Manejar formato chileno (puntos como separadores de miles)
            if ',' in cleaned and '.' in cleaned:
                # Formato: 1.234.567,89
                cleaned = cleaned.replace('.', '').replace(',', '.')
            elif cleaned.count('.') > 1:
                # Formato: 1.234.567 (separadores de miles)
                cleaned = cleaned.replace('.', '')
            
            return float(cleaned)
            
        except ValueError:
            return 0

    def _deduplicate_items(self, all_items: List[Dict]) -> List[Dict]:
        """Elimina items duplicados manteniendo el más completo."""
        
        unique_items = {}
        
        for item in all_items:
            codigo = item.get("codigo_mop", "")
            if not codigo:
                continue
            
            if codigo not in unique_items:
                unique_items[codigo] = item
            else:
                # Mantener el item más completo (más campos no vacíos)
                current = unique_items[codigo]
                current_score = sum(1 for v in current.values() if v and str(v).strip())
                new_score = sum(1 for v in item.values() if v and str(v).strip())
                
                if new_score > current_score:
                    unique_items[codigo] = item
        
        result = list(unique_items.values())
        logger.info(f"Deduplicación: {len(all_items)} → {len(result)} items únicos")
        
        return result

    def _validate_items(self, items: List[Dict]) -> List[Dict]:
        """Valida y limpia los items extraídos."""
        
        validated = []
        
        for item in items:
            try:
                # Validaciones básicas
                if not item.get("codigo_mop"):
                    continue
                
                # Limpiar descripción
                description = item.get("descripcion", "").strip()
                if len(description) < 3:
                    description = f"Item {item['codigo_mop']}"
                
                # Validar valores numéricos
                cantidad = max(0, float(item.get("cantidad", 0)))
                precio_unitario = max(0, float(item.get("precio_unitario", 0)))
                subtotal = max(0, float(item.get("subtotal", 0)))
                
                # Calcular subtotal si falta
                if subtotal == 0 and cantidad > 0 and precio_unitario > 0:
                    subtotal = cantidad * precio_unitario
                
                validated_item = {
                    "codigo_mop": item["codigo_mop"],
                    "descripcion": description,
                    "cantidad": cantidad,
                    "unidad": item.get("unidad", "uni"),
                    "precio_unitario": precio_unitario,
                    "subtotal": subtotal,
                    "categoria": self._categorize_item(description)
                }
                
                validated.append(validated_item)
                
            except Exception as e:
                logger.warning(f"Error validando item {item.get('codigo_mop', 'N/A')}: {e}")
        
        logger.info(f"Validación: {len(items)} → {len(validated)} items válidos")
        return validated

    def _categorize_item(self, description: str) -> str:
        """Categoriza el item según su descripción."""
        
        description_lower = description.lower()
        
        if any(word in description_lower for word in ['hormigón', 'concreto', 'cemento']):
            return 'materiales_construccion'
        elif any(word in description_lower for word in ['excavación', 'movimiento', 'tierra']):
            return 'movimiento_tierras'
        elif any(word in description_lower for word in ['asfalto', 'pavimento', 'rodadura']):
            return 'pavimentacion'
        elif any(word in description_lower for word in ['jornal', 'mano', 'obra']):
            return 'mano_obra'
        elif any(word in description_lower for word in ['equipo', 'maquinaria', 'camión']):
            return 'equipos'
        else:
            return 'otros'

    def _extract_project_info(self, pdf_path: str) -> Dict[str, str]:
        """Extrae información básica del proyecto."""
        
        try:
            import PyPDF2
            
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                
                # Leer las primeras 3 páginas para info del proyecto
                text = ""
                for page in pdf_reader.pages[:3]:
                    text += page.extract_text() + "\n"
            
            # Extraer información con regex
            proyecto = self._extract_field(text, [r'PROYECTO\s*:?\s*(.+)', r'OBRA\s*:?\s*(.+)'])
            region = self._extract_field(text, [r'REGIÓN\s*:?\s*(.+)', r'REGION\s*:?\s*(.+)'])
            comuna = self._extract_field(text, [r'COMUNA\s*:?\s*(.+)'])
            mandante = self._extract_field(text, [r'MANDANTE\s*:?\s*(.+)'])
            
            return {
                "nombre": proyecto or "Proyecto MOP",
                "region": region or "Por determinar",
                "comuna": comuna or "Por determinar", 
                "mandante": mandante or "MOP"
            }
            
        except Exception as e:
            logger.warning(f"Error extrayendo info del proyecto: {e}")
            return {
                "nombre": "Proyecto MOP",
                "region": "Por determinar",
                "comuna": "Por determinar",
                "mandante": "MOP"
            }

    def _extract_field(self, text: str, patterns: List[str]) -> str:
        """Extrae un campo específico del texto usando múltiples patrones."""
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                result = match.group(1).strip()
                # Limpiar resultado (tomar solo primera línea)
                result = result.split('\n')[0].strip()
                if len(result) > 3:
                    return result
        
        return ""

    def _calculate_totals(self, items: List[Dict]) -> Dict[str, float]:
        """Calcula totales financieros."""
        
        total_items = sum(item.get("subtotal", 0) for item in items)
        
        # Aplicar estructura de costos MOP estándar
        gastos_generales = total_items * 0.12  # 12%
        utilidad = (total_items + gastos_generales) * 0.10  # 10%
        contingencia = total_items * 0.05  # 5%
        
        subtotal_sin_iva = total_items + gastos_generales + utilidad + contingencia
        iva = subtotal_sin_iva * 0.19  # 19%
        total_final = subtotal_sin_iva + iva
        
        return {
            "costos_directos": total_items,
            "gastos_generales": gastos_generales,
            "utilidad": utilidad,
            "contingencia": contingencia,
            "subtotal_sin_iva": subtotal_sin_iva,
            "iva": iva,
            "total_final": total_final
        }

    def _fallback_extraction(self, pdf_path: str) -> Dict[str, Any]:
        """Extracción básica cuando fallan todos los métodos."""
        
        return {
            "items_found": 0,
            "items_detail": [],
            "project_info": {"nombre": "Extracción fallida", "region": "N/A"},
            "financial_totals": {"total_final": 0},
            "extraction_method": ["fallback"],
            "extraction_success": False,
            "error": "Falló la extracción con todos los métodos"
        }


# Función de conveniencia para uso externo
def extract_budget_data(pdf_path: str) -> Dict[str, Any]:
    """
    Función principal que reemplaza tu extractor actual.
    Mantiene la misma interfaz pero con capacidades mejoradas.
    """
    extractor = PDFExtractor()
    return extractor.extract_enhanced_budget_data(pdf_path)


# Test opcional
if __name__ == "__main__":
    print("PDF Extractor mejorado cargado exitosamente!")
    print("Mejoras incluidas:")
    print("- Extracción múltiple: lattice + stream + texto")
    print("- Patrones específicos MOP")
    print("- Deduplicación inteligente")
    print("- Validación automática")
    
    # Verificar dependencias
    try:
        import camelot
        print("✅ Camelot disponible")
    except ImportError:
        print("❌ Instalar camelot: pip install camelot-py[cv]")
    
    try:
        import pandas as pd
        print("✅ Pandas disponible")
    except ImportError:
        print("❌ Instalar pandas: pip install pandas")
    
    try:
        import PyPDF2
        print("✅ PyPDF2 disponible")
    except ImportError:
        print("❌ Instalar PyPDF2: pip install PyPDF2")
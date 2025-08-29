"""
Extractor principal de PDFs MOP.
Utiliza múltiples métodos para extraer contenido de documentos complejos.
"""

import pdfplumber
import tabula
import camelot
import pytesseract
from typing import Dict, List, Optional, Tuple, Any
import pandas as pd
from PIL import Image
import io
import re
import logging
from pathlib import Path
import asyncio
import aiofiles
from concurrent.futures import ThreadPoolExecutor
import fitz  # PyMuPDF
import cv2
import numpy as np

from app.config.settings import get_settings
from app.config.constants import (
    REGEX_PATTERNS, TABLE_HEADERS, TABLE_ROW_PATTERNS,
    is_valid_mop_code, clean_currency_string
)

logger = logging.getLogger(__name__)


class MOPPDFExtractor:
    """
    Extractor principal para PDFs de licitaciones MOP.
    Utiliza múltiples técnicas para extraer texto, tablas e imágenes.
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.executor = ThreadPoolExecutor(max_workers=4)
        
        # Configuración de extracción
        self.extraction_methods = [
            self._extract_with_pdfplumber,
            self._extract_with_tabula,
            self._extract_with_camelot,
            self._extract_with_pymupdf,
        ]
        
        # Solo usar OCR si es necesario (documentos escaneados)
        self.fallback_methods = [
            self._extract_with_ocr
        ]
    
    async def extract_comprehensive(self, pdf_path: str) -> Dict[str, Any]:
        """
        Extrae contenido completo usando múltiples métodos.
        
        Args:
            pdf_path: Ruta al archivo PDF
            
        Returns:
            Dict con toda la información extraída
        """
        logger.info(f"Iniciando extracción completa de: {pdf_path}")
        
        # Inicializar resultado
        results = {
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
                "processing_time_seconds": 0
            },
            "raw_extractions": {}
        }
        
        start_time = asyncio.get_event_loop().time()
        
        try:
            # 1. Validar archivo
            if not await self._validate_pdf(pdf_path):
                raise ValueError(f"PDF no válido: {pdf_path}")
            
            # 2. Análisis inicial del documento
            doc_analysis = await self._analyze_document_structure(pdf_path)
            results["extraction_metadata"]["pages_processed"] = doc_analysis["total_pages"]
            
            # 3. Extraer con métodos principales
            for method in self.extraction_methods:
                try:
                    logger.info(f"Ejecutando método: {method.__name__}")
                    method_result = await method(pdf_path)
                    
                    if method_result and method_result.get("success", False):
                        results = self._merge_results(results, method_result)
                        results["extraction_metadata"]["methods_used"].append(method.__name__)
                        results["raw_extractions"][method.__name__] = method_result
                        
                except Exception as e:
                    logger.warning(f"Error en método {method.__name__}: {e}")
                    continue
            
            # 4. Si no hay suficiente contenido, usar métodos de respaldo
            if self._needs_fallback(results):
                logger.info("Usando métodos de respaldo (OCR)")
                for method in self.fallback_methods:
                    try:
                        method_result = await method(pdf_path)
                        if method_result and method_result.get("success", False):
                            results = self._merge_results(results, method_result)
                            results["extraction_metadata"]["methods_used"].append(method.__name__)
                    except Exception as e:
                        logger.warning(f"Error en método de respaldo {method.__name__}: {e}")
            
            # 5. Post-procesamiento y análisis
            results = await self._post_process_results(results)
            
            # 6. Calcular métricas finales
            end_time = asyncio.get_event_loop().time()
            results["extraction_metadata"]["processing_time_seconds"] = end_time - start_time
            results["extraction_metadata"]["tables_found"] = len(results["tables"])
            results["extraction_metadata"]["confidence_score"] = self._calculate_confidence(results)
            
            logger.info(f"Extracción completada. Confianza: {results['extraction_metadata']['confidence_score']:.2f}")
            
            return results
            
        except Exception as e:
            logger.error(f"Error en extracción completa: {e}")
            results["error"] = str(e)
            return results
    
    async def _validate_pdf(self, pdf_path: str) -> bool:
        """Valida que el archivo PDF sea accesible y no corrupto."""
        try:
            path = Path(pdf_path)
            if not path.exists() or path.stat().st_size == 0:
                return False
            
            # Test básico con pdfplumber
            with pdfplumber.open(pdf_path) as pdf:
                return len(pdf.pages) > 0
                
        except Exception as e:
            logger.error(f"Error validando PDF: {e}")
            return False
    
    async def _analyze_document_structure(self, pdf_path: str) -> Dict:
        """Analiza la estructura general del documento."""
        try:
            with pdfplumber.open(pdf_path) as pdf:
                analysis = {
                    "total_pages": len(pdf.pages),
                    "has_text": False,
                    "has_tables": False,
                    "has_images": False,
                    "estimated_scan": False
                }
                
                # Analizar primeras 3 páginas para determinar tipo
                sample_pages = min(3, len(pdf.pages))
                for i in range(sample_pages):
                    page = pdf.pages[i]
                    
                    # Verificar texto
                    text = page.extract_text()
                    if text and len(text.strip()) > 50:
                        analysis["has_text"] = True
                    
                    # Verificar tablas
                    tables = page.extract_tables()
                    if tables:
                        analysis["has_tables"] = True
                    
                    # Verificar imágenes
                    if page.images:
                        analysis["has_images"] = True
                
                # Determinar si es documento escaneado
                text_ratio = 0
                if analysis["has_text"]:
                    sample_text = pdf.pages[0].extract_text() or ""
                    text_ratio = len(sample_text.strip()) / max(1, len(sample_text))
                
                analysis["estimated_scan"] = text_ratio < 0.1 and analysis["has_images"]
                
                return analysis
                
        except Exception as e:
            logger.error(f"Error analizando estructura: {e}")
            return {"total_pages": 0, "has_text": False, "has_tables": False, "has_images": False}
    
    async def _extract_with_pdfplumber(self, pdf_path: str) -> Dict:
        """Extracción principal con pdfplumber - mejor para texto y tablas básicas."""
        try:
            result = {"success": False, "text": "", "tables": [], "budget_items": []}
            
            with pdfplumber.open(pdf_path) as pdf:
                all_text = []
                all_tables = []
                
                for page_num, page in enumerate(pdf.pages):
                    # Extraer texto
                    page_text = page.extract_text()
                    if page_text:
                        all_text.append(f"=== PÁGINA {page_num + 1} ===\n{page_text}\n")
                    
                    # Extraer tablas
                    tables = page.extract_tables()
                    if tables:
                        for table_idx, table in enumerate(tables):
                            if self._is_budget_table(table):
                                processed_table = self._process_table(table, page_num + 1, table_idx + 1)
                                if processed_table:
                                    all_tables.append(processed_table)
                
                result.update({
                    "success": True,
                    "text": "\n".join(all_text),
                    "tables": all_tables,
                    "method": "pdfplumber"
                })
                
                # Extraer items presupuestarios del texto
                budget_items = self._extract_budget_items_from_text(result["text"])
                result["budget_items"] = budget_items
                
                return result
                
        except Exception as e:
            logger.error(f"Error con pdfplumber: {e}")
            return {"success": False, "error": str(e)}
    
    async def _extract_with_tabula(self, pdf_path: str) -> Dict:
        """Extracción con tabula - mejor para tablas complejas."""
        try:
            result = {"success": False, "tables": [], "method": "tabula"}
            
            # Ejecutar en hilo separado para evitar bloqueo
            loop = asyncio.get_event_loop()
            tables = await loop.run_in_executor(
                self.executor,
                lambda: tabula.read_pdf(pdf_path, pages='all', multiple_tables=True, pandas_options={'header': None})
            )
            
            processed_tables = []
            for idx, df in enumerate(tables):
                if not df.empty and len(df.columns) >= 4:  # Mínimo 4 columnas para presupuesto
                    processed_table = self._process_dataframe_table(df, page_num=idx+1, table_idx=idx+1)
                    if processed_table:
                        processed_tables.append(processed_table)
            
            result.update({
                "success": True,
                "tables": processed_tables
            })
            
            return result
            
        except Exception as e:
            logger.error(f"Error con tabula: {e}")
            return {"success": False, "error": str(e)}
    
    async def _extract_with_camelot(self, pdf_path: str) -> Dict:
        """Extracción con camelot - mejor para tablas con bordes."""
        try:
            result = {"success": False, "tables": [], "method": "camelot"}
            
            # Ejecutar en hilo separado
            loop = asyncio.get_event_loop()
            tables = await loop.run_in_executor(
                self.executor,
                lambda: camelot.read_pdf(pdf_path, pages='all', flavor='lattice')
            )
            
            processed_tables = []
            for table in tables:
                if table.accuracy > 50:  # Solo tablas con buena precisión
                    processed_table = self._process_dataframe_table(
                        table.df, 
                        page_num=table.page, 
                        table_idx=len(processed_tables) + 1
                    )
                    if processed_table:
                        processed_tables.append(processed_table)
            
            result.update({
                "success": True,
                "tables": processed_tables
            })
            
            return result
            
        except Exception as e:
            logger.error(f"Error con camelot: {e}")
            return {"success": False, "error": str(e)}
    
    async def _extract_with_pymupdf(self, pdf_path: str) -> Dict:
        """Extracción con PyMuPDF - complementaria."""
        try:
            result = {"success": False, "text": "", "images": [], "method": "pymupdf"}
            
            doc = fitz.open(pdf_path)
            all_text = []
            
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                
                # Extraer texto
                text = page.get_text()
                if text.strip():
                    all_text.append(f"=== PÁGINA {page_num + 1} (PyMuPDF) ===\n{text}\n")
                
                # Extraer imágenes si es necesario
                # (Implementar si se necesita análisis de imágenes)
            
            doc.close()
            
            result.update({
                "success": True,
                "text": "\n".join(all_text)
            })
            
            return result
            
        except Exception as e:
            logger.error(f"Error con PyMuPDF: {e}")
            return {"success": False, "error": str(e)}
    
    async def _extract_with_ocr(self, pdf_path: str) -> Dict:
        """Extracción con OCR - último recurso para documentos escaneados."""
        try:
            result = {"success": False, "text": "", "method": "ocr"}
            
            # Convertir PDF a imágenes y aplicar OCR
            doc = fitz.open(pdf_path)
            all_text = []
            
            for page_num in range(min(5, len(doc))):  # Limitar a 5 páginas por performance
                page = doc.load_page(page_num)
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # Escalar para mejor OCR
                img_data = pix.pil_tobytes(format="PNG")
                img = Image.open(io.BytesIO(img_data))
                
                # Aplicar OCR
                ocr_text = pytesseract.image_to_string(img, lang=self.settings.OCR_LANGUAGE)
                if ocr_text.strip():
                    all_text.append(f"=== PÁGINA {page_num + 1} (OCR) ===\n{ocr_text}\n")
            
            doc.close()
            
            result.update({
                "success": True,
                "text": "\n".join(all_text)
            })
            
            return result
            
        except Exception as e:
            logger.error(f"Error con OCR: {e}")
            return {"success": False, "error": str(e)}
    
    def _is_budget_table(self, table: List[List]) -> bool:
        """Determina si una tabla es presupuestaria."""
        if not table or len(table) < 2:
            return False
        
        # Verificar headers típicos
        header_row = table[0] if table else []
        header_text = " ".join([str(cell) for cell in header_row if cell]).lower()
        
        budget_keywords = ["ítem", "item", "designación", "descripción", "unidad", "cantidad", "precio", "unitario", "total"]
        
        return sum(1 for keyword in budget_keywords if keyword in header_text) >= 3
    
    def _process_table(self, table: List[List], page_num: int, table_idx: int) -> Optional[Dict]:
        """Procesa una tabla extraída."""
        if not table or len(table) < 2:
            return None
        
        processed = {
            "page": page_num,
            "table_index": table_idx,
            "headers": table[0],
            "rows": table[1:],
            "items": []
        }
        
        # Procesar filas para extraer items presupuestarios
        for row_idx, row in enumerate(table[1:], 1):
            if len(row) >= 4:  # Mínimo 4 columnas
                item = self._parse_budget_row(row, row_idx)
                if item:
                    processed["items"].append(item)
        
        return processed if processed["items"] else None
    
    def _process_dataframe_table(self, df: pd.DataFrame, page_num: int, table_idx: int) -> Optional[Dict]:
        """Procesa una tabla de pandas DataFrame."""
        if df.empty or len(df.columns) < 4:
            return None
        
        # Convertir a formato de lista para procesamiento uniforme
        table_data = [df.columns.tolist()] + df.values.tolist()
        return self._process_table(table_data, page_num, table_idx)
    
    def _parse_budget_row(self, row: List, row_idx: int) -> Optional[Dict]:
        """Parsea una fila de tabla presupuestaria."""
        try:
            # Limpiar valores
            clean_row = [str(cell).strip() if cell else "" for cell in row]
            
            # Buscar código MOP
            mop_code = None
            for cell in clean_row[:2]:  # Código suele estar en primeras columnas
                if is_valid_mop_code(cell):
                    mop_code = cell
                    break
            
            if not mop_code:
                return None
            
            # Extraer descripción (suele ser la columna más larga)
            description = ""
            for cell in clean_row:
                if len(cell) > len(description) and not cell.replace(".", "").replace(",", "").isdigit():
                    description = cell
            
            # Extraer valores numéricos
            numeric_values = []
            for cell in clean_row:
                try:
                    value = clean_currency_string(cell)
                    if value > 0:
                        numeric_values.append(value)
                except:
                    continue
            
            if len(numeric_values) >= 3:  # cantidad, precio_unitario, total
                return {
                    "row_index": row_idx,
                    "codigo_mop": mop_code,
                    "descripcion": description,
                    "cantidad": numeric_values[0],
                    "precio_unitario": numeric_values[1],
                    "subtotal": numeric_values[2],
                    "raw_row": clean_row
                }
            
            return None
            
        except Exception as e:
            logger.warning(f"Error parseando fila {row_idx}: {e}")
            return None
    
    def _extract_budget_items_from_text(self, text: str) -> List[Dict]:
        """Extrae items presupuestarios del texto usando regex."""
        items = []
        
        for pattern in TABLE_ROW_PATTERNS:
            matches = re.finditer(pattern, text, re.MULTILINE)
            for match in matches:
                try:
                    groups = match.groups()
                    if len(groups) >= 6:
                        item = {
                            "codigo_mop": groups[0],
                            "descripcion": groups[1].strip(),
                            "unidad": groups[2],
                            "cantidad": clean_currency_string(groups[3]),
                            "precio_unitario": clean_currency_string(groups[4]),
                            "subtotal": clean_currency_string(groups[5]),
                            "source": "regex"
                        }
                        
                        # Validar que sea un item válido
                        if (is_valid_mop_code(item["codigo_mop"]) and 
                            item["cantidad"] > 0 and 
                            item["precio_unitario"] > 0):
                            items.append(item)
                            
                except Exception as e:
                    logger.warning(f"Error procesando match regex: {e}")
                    continue
        
        return items
    
    def _merge_results(self, main_result: Dict, method_result: Dict) -> Dict:
        """Combina resultados de diferentes métodos de extracción."""
        if not method_result.get("success", False):
            return main_result
        
        # Combinar texto
        if method_result.get("text"):
            if main_result["text_content"]:
                main_result["text_content"] += f"\n\n{method_result['text']}"
            else:
                main_result["text_content"] = method_result["text"]
        
        # Combinar tablas
        if method_result.get("tables"):
            main_result["tables"].extend(method_result["tables"])
        
        # Combinar items presupuestarios
        if method_result.get("budget_items"):
            main_result["budget_items"].extend(method_result["budget_items"])
        
        return main_result
    
    def _needs_fallback(self, results: Dict) -> bool:
        """Determina si se necesitan métodos de respaldo."""
        text_length = len(results.get("text_content", ""))
        table_count = len(results.get("tables", []))
        item_count = len(results.get("budget_items", []))
        
        # Usar fallback si hay muy poco contenido extraído
        return text_length < 1000 and table_count < 2 and item_count < 5
    
    async def _post_process_results(self, results: Dict) -> Dict:
        """Post-procesamiento de resultados."""
        # Extraer información del proyecto
        if results["text_content"]:
            results["project_info"] = self._extract_project_info(results["text_content"])
            results["totals"] = self._extract_totals(results["text_content"])
        
        # Deduplicar items presupuestarios
        results["budget_items"] = self._deduplicate_budget_items(results["budget_items"])
        
        # Validar y limpiar datos
        results["budget_items"] = self._validate_budget_items(results["budget_items"])
        
        return results
    
    def _extract_project_info(self, text: str) -> Dict:
        """Extrae información básica del proyecto."""
        info = {}
        
        for key, pattern in REGEX_PATTERNS.items():
            if key.startswith("proyecto") or key in ["region", "comuna"]:
                match = pattern.search(text)
                if match:
                    info[key] = match.group(1).strip()
        
        return info
    
    def _extract_totals(self, text: str) -> Dict:
        """Extrae totales del documento."""
        totals = {}
        
        total_patterns = {
            "total_neto": REGEX_PATTERNS["total_neto"],
            "total_iva": REGEX_PATTERNS["total_iva"], 
            "total_general": REGEX_PATTERNS["total_general"]
        }
        
        for key, pattern in total_patterns.items():
            match = pattern.search(text)
            if match:
                totals[key] = clean_currency_string(match.group(1))
        
        return totals
    
    def _deduplicate_budget_items(self, items: List[Dict]) -> List[Dict]:
        """Elimina items duplicados."""
        seen = set()
        unique_items = []
        
        for item in items:
            # Crear clave única basada en código y descripción
            key = (item.get("codigo_mop", ""), item.get("descripcion", "")[:50])
            
            if key not in seen:
                seen.add(key)
                unique_items.append(item)
        
        return unique_items
    
    def _validate_budget_items(self, items: List[Dict]) -> List[Dict]:
        """Valida y limpia items presupuestarios."""
        valid_items = []
        
        for item in items:
            # Validaciones básicas
            if not is_valid_mop_code(item.get("codigo_mop", "")):
                continue
                
            if item.get("precio_unitario", 0) <= 0 or item.get("cantidad", 0) <= 0:
                continue
                
            if item.get("precio_unitario", 0) > self.settings.MAX_UNIT_PRICE:
                continue
            
            valid_items.append(item)
        
        return valid_items
    
    def _calculate_confidence(self, results: Dict) -> float:
        """Calcula un score de confianza de la extracción."""
        score = 0.0
        
        # Texto extraído
        if len(results.get("text_content", "")) > 1000:
            score += 0.3
        
        # Tablas encontradas
        if len(results.get("tables", [])) > 0:
            score += 0.3
        
        # Items presupuestarios
        item_count = len(results.get("budget_items", []))
        if item_count > 10:
            score += 0.3
        elif item_count > 5:
            score += 0.2
        elif item_count > 0:
            score += 0.1
        
        # Información del proyecto
        if results.get("project_info"):
            score += 0.1
        
        return min(1.0, score)


# Función de conveniencia para uso externo
async def extract_pdf_content(pdf_path: str) -> Dict[str, Any]:
    """
    Función principal para extraer contenido de un PDF MOP.
    
    Args:
        pdf_path: Ruta al archivo PDF
        
    Returns:
        Dict con toda la información extraída
    """
    extractor = MOPPDFExtractor()
    return await extractor.extract_comprehensive(pdf_path)


if __name__ == "__main__":
    # Test básico
    import asyncio
    
    async def test_extractor():
        # Aquí pondrías la ruta a uno de tus PDFs de prueba
        pdf_path = "path/to/test.pdf"
        
        if Path(pdf_path).exists():
            result = await extract_pdf_content(pdf_path)
            print(f"Extracción completada. Confianza: {result['extraction_metadata']['confidence_score']:.2f}")
            print(f"Items encontrados: {len(result['budget_items'])}")
            print(f"Tablas encontradas: {len(result['tables'])}")
        else:
            print("Archivo de prueba no encontrado")
    
    # asyncio.run(test_extractor())
    print("PDF Extractor loaded successfully!")
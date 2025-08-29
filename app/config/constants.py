"""
Constantes y códigos específicos del MOP (Ministerio de Obras Públicas).
Basado en el análisis de los PDFs de bases administrativas.
"""

from typing import Dict, List, Set
import re
from enum import Enum


class TipoObra(Enum):
    """Tipos de obra según documentos MOP."""
    INFRAESTRUCTURA_VIAL = "infraestructura_vial"
    INFRAESTRUCTURA_HIDRAULICA = "infraestructura_hidraulica"
    INFRAESTRUCTURA_AEROPORTUARIA = "infraestructura_aeroportuaria"
    CONSERVACION_VIAL = "conservacion_vial"
    PAVIMENTACION = "pavimentacion"
    PUENTES = "puentes"
    EDIFICACION = "edificacion"


# === CÓDIGOS MOP ESTÁNDAR ===
# Basados en los patrones encontrados en los PDFs analizados

MOP_CODES = {
    # 7.301.x - Limpieza y preparación
    "7.301.1": "Limpieza Manual de la Faja",
    "7.301.2": "Limpieza Mecanizada",
    "7.301.3": "Desarme de Estructuras",
    
    # 7.302.x - Movimiento de tierras
    "7.302.1a": "Terraplenes, Tmáx Bajo 4\"",
    "7.302.2e": "Conformación de La Plataforma",
    "7.302.7a": "Excavación en Terreno de Cualquier Naturaleza",
    
    # 7.303.x - Obras de drenaje y arte
    "7.303.1341": "Alcantarillas de Tubos de Polietileno de Alta Densidad Estructurados, D=0.60 m",
    "7.303.1342": "Alcantarillas de Tubos de Polietileno de Alta Densidad Estructurados, D=0.75 m",
    "7.303.1343": "Alcantarillas de Tubos de Polietileno de Alta Densidad Estructurados, D=1.00 m",
    "7.303.1345": "Alcantarillas de Tubos de Polietileno de Alta Densidad Estructurados, D=1.50 m",
    "7.303.17b": "Construcción de Fosos y Contrafosos en Terreno de Cualquier Naturaleza",
    
    # 7.306.x - Recepción de canales
    "7.306.4a": "Recepción de Canales de Rodadura Ondulados, Tamaño Máximo 1 1/2\", Chancado al 30%",
    
    # ETE.1 - Especificaciones técnicas especiales
    "ETE.1": "Huellas en Base a Losetas de Hormigón Armado",
    
    # 7.311.x - Instalaciones y mantención
    "7.311.1": "Instalación de Faena y Campamentos en Obras de Mantenimiento",
    "7.311.2": "Apertura, Uso y Abandono de Botadero en Obras de Mantenimiento", 
    "7.311.3": "Apertura, Explotación y Abandono de Empréstitos en Obras de Mantenimiento",
    
    # 804.2 - Gestión ambiental
    "804-2": "Plan de Gestión de Residuos de Construcción Y/O Demoliciones"
}


# === PATRONES DE EXTRACCIÓN ===

# Patrones regex para identificar diferentes elementos en los PDFs
REGEX_PATTERNS = {
    # Identificar ítems presupuestarios
    "budget_item": re.compile(
        r"(\d+\.?\d*\.?\d*[a-zA-Z]?)\s+([^$]+?)\s+(\w+)\s+([\d,\.]+)\s+\$\s*([\d,\.]+)\s+\$\s*([\d,\.]+)",
        re.MULTILINE | re.IGNORECASE
    ),
    
    # Identificar códigos MOP específicos
    "mop_code": re.compile(r"\b7\.\d{3}\.\d+[a-zA-Z]?\b"),
    
    # Identificar totales
    "total_neto": re.compile(r"TOTAL\s+NETO\s+\$\s*([\d,\.]+)", re.IGNORECASE),
    "total_iva": re.compile(r"19\s*%\s*I\.?V\.?A\.?\s+\$\s*([\d,\.]+)", re.IGNORECASE),
    "total_general": re.compile(r"TOTAL\s+GENERAL\s+\$\s*([\d,\.]+)", re.IGNORECASE),
    
    # Identificar información del proyecto
    "proyecto_nombre": re.compile(r"PROYECTO:\s*[\"']?([^\"'\n]+)[\"']?", re.IGNORECASE),
    "region": re.compile(r"REGIÓN\s+DE\s+([A-ZÁÉÍÓÚ\s]+)", re.IGNORECASE),
    "comuna": re.compile(r"COMUNA[S]?\s+DE\s+([A-ZÁÉÍÓÚ\s,]+)", re.IGNORECASE),
    
    # Identificar coordenadas UTM
    "utm_coordinates": re.compile(r"UTM.*?(\d{6,7})[,\s]+(\d{7,8})", re.IGNORECASE),
    
    # Identificar montos en texto
    "monto_palabras": re.compile(
        r"(SETECIENTOS|SEISCIENTOS|QUINIENTOS|CUATROCIENTOS|TRESCIENTOS|DOSCIENTOS|CIENTOS?)\s+"
        r"([A-ZÁÉÍÓÚ\s]*?)\s+(MILLONES?|MIL|PESOS)",
        re.IGNORECASE
    )
}


# === PATRONES DE TABLA PRESUPUESTARIA ===
TABLE_HEADERS = [
    # Español estándar
    ["Ítem", "Designación", "Unidad", "Cantidad", "P.Unitario", "P.Total"],
    ["Item", "Descripción", "Unidad", "Cantidad", "Precio Unitario", "Precio Total"],
    
    # Variaciones comunes
    ["Ítem", "Designación", "Unidad", "Cantidad", "P Unitario", "P Total"],
    ["Item", "Designacion", "Unidad", "Cantidad", "P.Unitario", "P.Total"],
    
    # Headers en inglés (por si acaso)
    ["Item", "Description", "Unit", "Quantity", "Unit Price", "Total Price"]
]

# Patrones para detectar filas de tabla presupuestaria
TABLE_ROW_PATTERNS = [
    # Patrón principal: código + descripción + unidad + cantidad + precios
    r"(\d+\.?\d*\.?\d*[a-zA-Z]?)\s+(.+?)\s+(\w+)\s+([\d,\.]+)\s+\$\s*([\d,\.]+)\s+\$\s*([\d,\.]+)",
    
    # Patrón alternativo sin símbolos $
    r"(\d+\.?\d*\.?\d*[a-zA-Z]?)\s+(.+?)\s+(\w+)\s+([\d,\.]+)\s+([\d,\.]+)\s+([\d,\.]+)",
    
    # Patrón con espacios variables
    r"(\d+\.?\d*\.?\d*[a-zA-Z]?)\s+(.+?)\s+(\w+)\s+([\d\s,\.]+)\s+\$?\s*([\d\s,\.]+)\s+\$?\s*([\d\s,\.]+)"
]


# === UNIDADES VÁLIDAS ===
VALID_UNITS = {
    # Unidades de volumen
    "m3", "m³", "cm3", "cm³",
    
    # Unidades de área  
    "m2", "m²", "cm2", "cm²", "ha",
    
    # Unidades de longitud
    "m", "cm", "mm", "km",
    
    # Unidades de peso
    "kg", "ton", "t", "gr", "g",
    
    # Unidades especiales
    "gl", "un", "unid", "pza", "lt", "l",
    
    # Unidades de tiempo
    "hr", "h", "día", "mes"
}


# === RANGOS DE VALIDACIÓN ===
VALIDATION_RANGES = {
    "max_unit_price": 10_000_000,  # 10M CLP máximo por unidad
    "max_total_price": 1_000_000_000,  # 1B CLP máximo total
    "min_quantity": 0.01,  # Cantidad mínima
    "max_quantity": 1_000_000,  # Cantidad máxima
    "iva_rate": 0.19,  # 19% IVA en Chile
    "tolerance_percentage": 0.02  # 2% tolerancia en cálculos
}


# === DIRECCIONES MOP ===
MOP_DIRECCIONES = {
    "DV": "Dirección de Vialidad",
    "DOH": "Dirección de Obras Hidráulicas", 
    "DA": "Dirección de Arquitectura",
    "DOP": "Dirección de Obras Portuarias",
    "DAP": "Dirección de Aeropuertos",
    "DGOP": "Dirección General de Obras Públicas"
}


# === REGIONES DE CHILE ===
REGIONES_CHILE = {
    "XV": "Arica y Parinacota",
    "I": "Tarapacá", 
    "II": "Antofagasta",
    "III": "Atacama",
    "IV": "Coquimbo",
    "V": "Valparaíso",
    "RM": "Metropolitana",
    "VI": "O'Higgins",
    "VII": "Maule",
    "XVI": "Ñuble", 
    "VIII": "Biobío",
    "IX": "Araucanía",
    "XIV": "Los Ríos",
    "X": "Los Lagos",
    "XI": "Aysén",
    "XII": "Magallanes"
}


# === CLASIFICACIÓN DE COSTOS ===
COST_CATEGORIES = {
    "materials": {
        "keywords": [
            "hormigón", "cemento", "acero", "ripio", "arena", "grava",
            "tubo", "alcantarilla", "loseta", "pavimento", "asfalto",
            "polietileno", "material", "agregado", "chancado"
        ],
        "percentage_range": (40, 70)  # % típico en proyectos MOP
    },
    "labor": {
        "keywords": [
            "mano de obra", "personal", "trabajador", "técnico",
            "operario", "maestro", "ayudante", "instalación",
            "conformación", "excavación", "construcción"
        ],
        "percentage_range": (15, 35)
    },
    "equipment": {
        "keywords": [
            "maquinaria", "equipo", "bulldozer", "excavadora", 
            "camión", "compactador", "rodillo", "motoniveladora",
            "retroexcavadora", "grúa", "herramienta"
        ],
        "percentage_range": (10, 25)
    },
    "overhead": {
        "keywords": [
            "gastos generales", "utilidad", "overhead", "administración",
            "faena", "campamento", "oficina", "gestión", "supervisión"
        ],
        "percentage_range": (8, 15)
    }
}


# === FUNCIONES AUXILIARES ===

def is_valid_mop_code(code: str) -> bool:
    """Verifica si un código corresponde a un formato MOP válido."""
    if not code:
        return False
    
    # Códigos 7.xxx.xxx
    if re.match(r"^7\.\d{3}\.\d+[a-zA-Z]?$", code):
        return True
    
    # Códigos ETE.x
    if re.match(r"^ETE\.\d+$", code):
        return True
    
    # Códigos xxx-x
    if re.match(r"^\d{3,4}-\d+$", code):
        return True
    
    return False


def categorize_item_by_description(description: str) -> str:
    """Categoriza un ítem según su descripción."""
    description_lower = description.lower()
    
    for category, info in COST_CATEGORIES.items():
        for keyword in info["keywords"]:
            if keyword in description_lower:
                return category
    
    return "materials"  # Por defecto


def clean_currency_string(value: str) -> float:
    """Convierte string con formato de moneda chilena a float."""
    if not value:
        return 0.0
    
    # Remover símbolos y espacios
    cleaned = re.sub(r'[^\d,\.]', '', str(value))
    
    # Manejar formato chileno (punto como separador de miles, coma como decimal)
    if ',' in cleaned and '.' in cleaned:
        # Si tiene ambos, la coma es decimal
        cleaned = cleaned.replace('.', '').replace(',', '.')
    elif ',' in cleaned:
        # Solo coma, podría ser decimal o miles
        parts = cleaned.split(',')
        if len(parts[-1]) == 3:  # Probablemente separador de miles
            cleaned = cleaned.replace(',', '')
        else:  # Probablemente decimal
            cleaned = cleaned.replace(',', '.')
    
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


if __name__ == "__main__":
    # Test básico de las funciones
    print("=== TEST CONSTANTES MOP ===")
    
    # Test códigos MOP
    test_codes = ["7.301.1", "7.302.5a", "ETE.1", "804-2", "invalid"]
    for code in test_codes:
        print(f"Código {code}: {'Válido' if is_valid_mop_code(code) else 'Inválido'}")
    
    # Test limpieza de moneda
    test_values = ["$ 1.234.567", "1,234,567.89", "1.234.567,50", "invalid"]
    for value in test_values:
        cleaned = clean_currency_string(value)
        print(f"Valor '{value}' -> {cleaned}")
    
    # Test categorización
    test_descriptions = [
        "Hormigón para pavimento",
        "Instalación de faena",
        "Excavadora CAT 320",
        "Gastos generales"
    ]
    for desc in test_descriptions:
        category = categorize_item_by_description(desc)
        print(f"'{desc}' -> {category}")
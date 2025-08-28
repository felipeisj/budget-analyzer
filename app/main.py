from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Cargar variables de entorno
load_dotenv()

app = FastAPI(
    title="MOP PDF Analyzer", 
    version="1.0.0",
    description="Microservicio para análisis de PDFs de licitaciones MOP"
)

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {
        "message": "MOP PDF Analyzer API", 
        "version": "1.0.0",
        "status": "running"
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy", 
        "service": "mop-pdf-analyzer",
        "environment": os.getenv("ENVIRONMENT", "development")
    }

@app.post("/analyze-pdf")
async def analyze_mop_pdf(file: UploadFile = File(...)):
    """Endpoint principal para análisis de PDFs MOP"""
    
    # Validar tipo de archivo
    if not file.filename.endswith('.pdf'):
        raise HTTPException(
            status_code=400, 
            detail="Solo se aceptan archivos PDF"
        )
    
    # Validar tamaño (100MB max por ahora)
    content = await file.read()
    if len(content) > 100 * 1024 * 1024:  # 100MB
        raise HTTPException(
            status_code=413, 
            detail="Archivo demasiado grande. Máximo 100MB"
        )
    
    try:
        logger.info(f"Procesando archivo: {file.filename}, tamaño: {len(content)} bytes")
        
        # Por ahora devolver respuesta básica
        return {
            "filename": file.filename,
            "size_bytes": len(content),
            "message": "Archivo recibido correctamente",
            "status": "processing_ready"
        }
        
    except Exception as e:
        logger.error(f"Error procesando PDF: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Error interno del servidor: {str(e)}"
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

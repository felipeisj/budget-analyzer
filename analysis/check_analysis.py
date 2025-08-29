#!/usr/bin/env python3
"""
Script para verificar el estado de un análisis específico y obtener debug info.
"""

import requests
import json
import sys
import time
from datetime import datetime

API_BASE_URL = "http://localhost:8000"

def check_analysis_status(analysis_id: str):
    """Verifica el estado detallado de un análisis."""
    url = f"{API_BASE_URL}/api/budget-analysis/pdf/{analysis_id}"
    
    try:
        print(f"🔍 Consultando estado del análisis: {analysis_id}")
        print(f"📡 URL: {url}")
        print("-" * 60)
        
        response = requests.get(url, timeout=10)
        
        print(f"📊 Status Code: {response.status_code}")
        print(f"📋 Headers: {dict(response.headers)}")
        print("-" * 60)
        
        if response.status_code in [200, 202, 500]:
            try:
                data = response.json()
                print("📄 Respuesta JSON:")
                print(json.dumps(data, indent=2, ensure_ascii=False))
            except json.JSONDecodeError:
                print("❌ Error: La respuesta no es JSON válido")
                print("📄 Respuesta raw:")
                print(response.text)
        else:
            print(f"❌ Error HTTP {response.status_code}")
            print("📄 Respuesta:")
            print(response.text)
            
    except requests.exceptions.ConnectionError:
        print("❌ Error de conexión - ¿Está el servidor ejecutándose?")
    except requests.exceptions.Timeout:
        print("⏰ Timeout - El servidor no responde")
    except Exception as e:
        print(f"❌ Error inesperado: {e}")

def get_service_status():
    """Obtiene el estado general del servicio."""
    url = f"{API_BASE_URL}/api/budget-analysis/status"
    
    try:
        print("🔍 Consultando estado del servicio...")
        response = requests.get(url, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            print("✅ Estado del servicio:")
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            print(f"❌ Error {response.status_code}: {response.text}")
            
    except Exception as e:
        print(f"❌ Error consultando servicio: {e}")

def check_server_logs():
    """Muestra información para verificar logs del servidor."""
    print("\n" + "="*60)
    print("📋 INFORMACIÓN PARA DEBUGGING")
    print("="*60)
    print("🔧 Para ver los logs del servidor, revisa la terminal donde")
    print("   está ejecutándose 'python app/main.py'")
    print("\n💡 Comandos útiles:")
    print("   • Ver procesos Python: ps aux | grep python")
    print("   • Ver puerto 8000: lsof -i :8000")
    print("   • Reiniciar servidor: Ctrl+C y ejecutar 'python app/main.py' de nuevo")

def monitor_analysis(analysis_id: str, max_checks: int = 20):
    """Monitorea un análisis en tiempo real."""
    print(f"\n🔄 Monitoreando análisis {analysis_id}")
    print("Presiona Ctrl+C para detener...")
    
    try:
        for i in range(max_checks):
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Check #{i+1}")
            check_analysis_status(analysis_id)
            
            if i < max_checks - 1:  # No esperar en la última iteración
                print("⏳ Esperando 10 segundos...")
                time.sleep(10)
            
    except KeyboardInterrupt:
        print("\n🛑 Monitoreo detenido por el usuario")

def main():
    """Función principal."""
    if len(sys.argv) < 2:
        print("📖 Uso:")
        print("  python check_analysis.py <analysis_id>          # Verificar estado una vez")
        print("  python check_analysis.py <analysis_id> monitor  # Monitorear continuamente")
        print("  python check_analysis.py status                 # Estado del servicio")
        print("\n📝 Ejemplo:")
        print("  python check_analysis.py 2b94e16a-de03-47aa-9a3f-82e77cc4882e")
        return
    
    command = sys.argv[1]
    
    if command == "status":
        get_service_status()
        check_server_logs()
        return
    
    analysis_id = command
    
    if len(sys.argv) > 2 and sys.argv[2] == "monitor":
        monitor_analysis(analysis_id)
    else:
        check_analysis_status(analysis_id)
        check_server_logs()

if __name__ == "__main__":
    main()
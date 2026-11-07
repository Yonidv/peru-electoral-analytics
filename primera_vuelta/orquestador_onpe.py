import subprocess
import time
import sys
import os

# Configuración de los archivos
SCRIPTS_FONDO = [
    "extractor_onpe.py",
    "Analizador de Tendencia Regional ONPE 2026.py"
]
SCRIPT_PRINCIPAL = "simulador_onpe.py"

def ejecutar_sistema():
    procesos_fondo = []
    
    print("="*60)
    print("SISTEMA ELECTORAL ONPE 2026 - INICIANDO ORQUESTADOR")
    print("="*60)

    try:
        # 1. Lanzar scripts de fondo (Loop infinito)
        for script in SCRIPTS_FONDO:
            print(f"[+] Iniciando proceso de fondo: {script}...")
            # Usamos Popen para que corran sin bloquear este script
            p = subprocess.Popen([sys.executable, script], 
                                 creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0)
            procesos_fondo.append(p)
        
        # 2. Esperar unos segundos para que generen los primeros archivos (Excel/JSON)
        print("\n[*] Esperando 10 segundos para sincronización de datos...")
        time.sleep(10)

        # 3. Ejecutar el simulador
        print(f"\n[!] Lanzando {SCRIPT_PRINCIPAL}...\n")
        # Aquí usamos run() porque queremos que la terminal se quede en el simulador
        subprocess.run([sys.executable, SCRIPT_PRINCIPAL])

    except KeyboardInterrupt:
        print("\n\n[!] Deteniendo sistema por el usuario...")
    finally:
        # Limpieza: Intentar cerrar los procesos de fondo al salir
        print("[*] Cerrando procesos de fondo...")
        for p in procesos_fondo:
            p.terminate()
        print("[OK] Sistema apagado.")

if __name__ == "__main__":
    ejecutar_sistema()
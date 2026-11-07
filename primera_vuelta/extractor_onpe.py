import requests
import pandas as pd
import time
from datetime import datetime

# URLs oficiales de la ONPE 2026
URL_TOTALES = "https://resultadoelectoral.onpe.gob.pe/presentacion-backend/resumen-general/totales?idEleccion=10&tipoFiltro=eleccion"
URL_PARTICIPANTES = "https://resultadoelectoral.onpe.gob.pe/presentacion-backend/resumen-general/participantes?idEleccion=10&tipoFiltro=eleccion"
URL_PARTICIPACION = "https://resultadoelectoral.onpe.gob.pe/presentacion-backend/participacion-ciudadana/totales?tipoFiltro=total"

ARCHIVO_EXCEL = 'resultados_vivo.xlsx'

# Mapeo exacto basado en el JSON de la ONPE
# Mapeo actualizado con Wolfgang y Mario
MAPEO_CANDIDATOS = {
    "FUERZA POPULAR": "Keiko Fujimori",
    "RENOVACIÓN POPULAR": "Rafael López Aliaga",
    "PARTIDO PAÍS PARA TODOS": "Carlos Álvarez",
    "PARTIDO CÍVICO OBRAS": "Ricardo Belmont",
    "JUNTOS POR EL PERÚ": "Roberto Sánchez",
    "PARTIDO DEL BUEN GOBIERNO": "Jorge Nieto",
    "AHORA NACIÓN - AN": "Alfonso López Chau",
    "PRIMERO LA GENTE – COMUNIDAD, ECOLOGÍA, LIBERTAD Y PROGRESO": "Marisol Pérez Tello",
    "ALIANZA PARA EL PROGRESO": "César Acuña",
    "PARTIDO POLÍTICO COOPERACIÓN POPULAR": "Yonhy Lescano",
    "PARTIDO POLÍTICO INTEGRIDAD DEMOCRÁTICA": "Wolfgang Grozo",
    "PARTIDO POLÍTICO PERÚ PRIMERO": "Mario Vizcarra"
}

def obtener_datos_json():
    headers = {
    "accept": "*/*",
    "accept-language": "es-419,es;q=0.6",
    "content-type": "application/json",
    # El 'cf_clearance' es tu pase de oro. Úsalo tal cual lo copiaste.
    "cookie": "cf_clearance=i4nGwXNKji16Jv6M8MMY2dpSs7yuidB7hvSj9AOq9VQ-1775185278-1.2.1.1-27wYdl6j7INgpNxggk8UBrrNIbbG7X9rSwhwcoNmF0FkDY.mEl7oM35e92y6Cr_0TYxZcxp1PIZbr5A2oHpADuOPac72qTSTeEN6xckHqyc1MJREArhpbIAW8adFshsMCsR_xixoJiKrMNL9XUcty8mtwyOs8IAxIJeJdBwPpZOKXKKtQV7Ml6d25FOM7.IBa4OERIriSKGQZ1yKAZ2wg7M8YBDfPVQ957UjyXozJik",
    "priority": "u=1, i",
    "referer": "https://resultadoelectoral.onpe.gob.pe/main/senadores-distrito-nacional-unico",
    "sec-ch-ua": '"Brave";v="147", "Not.A/Brand";v="8", "Chromium";v="147"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "sec-gpc": "1",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
}
    
    try:
        # 1. Datos generales de avance
        res_totales = requests.get(URL_TOTALES, headers=headers, timeout=10)
        res_totales.raise_for_status()
        data_totales = res_totales.json().get('data', {})
        
        avance = float(data_totales.get('actasContabilizadas', 0)) / 100.0
        emitidos = int(data_totales.get('totalVotosEmitidos', 0))
        validos = int(data_totales.get('totalVotosValidos', 0))

        # 2. Participación ciudadana en vivo
        res_part = requests.get(URL_PARTICIPACION, headers=headers, timeout=10)
        res_part.raise_for_status()
        data_part = res_part.json().get('data', {})
        
        asistentes = int(data_part.get('totalAsistentes', 0))
        ausentes = int(data_part.get('totalAusentes', 0))
        # Si no hay datos, usamos el histórico por defecto
        participacion_vivo = asistentes / (asistentes + ausentes) if (asistentes + ausentes) > 0 else 0.70048

        # 3. Votos por candidato
        res_participantes = requests.get(URL_PARTICIPANTES, headers=headers, timeout=10)
        res_participantes.raise_for_status()
        data_participantes = res_participantes.json().get('data', [])
        
        votos_candidatos = {}
        for item in data_participantes:
            agrupacion = str(item.get('nombreAgrupacionPolitica', '')).strip()
            if agrupacion in MAPEO_CANDIDATOS:
                nombre_corto = MAPEO_CANDIDATOS[agrupacion]
                votos = int(item.get('totalVotosValidos', 0))
                votos_candidatos[nombre_corto] = votos

        return {
            'Hora': datetime.now().strftime('%H:%M:%S'),
            'Avance_Actas': avance,
            'Votos_Emitidos_Totales': emitidos,
            'Votos_Validos_Totales': validos,
            'Participacion_Vivo': participacion_vivo,
            **votos_candidatos
        }

    except Exception as e:
        print(f"Error conectando a la ONPE: {e}")
        return None

def actualizar_excel(nuevos_datos):
    try:
        df = pd.read_excel(ARCHIVO_EXCEL, sheet_name='Hoja1', header=None)
        
        # Heredar Fuerza_Rural_Faltante de la última columna
        fuerza_rural_heredada = 0.0
        for index, row in df.iterrows():
            if str(row[0]).strip() == 'Fuerza_Rural_Faltante':
                try:
                    fuerza_rural_heredada = float(row.iloc[-1])
                except Exception:
                    pass
                break
        
        nuevos_datos['Fuerza_Rural_Faltante'] = fuerza_rural_heredada
        
        # Construir la nueva columna según las etiquetas de la Columna A
        nueva_columna = []
        for etiqueta in df[0]:
            clave = str(etiqueta).strip()
            nueva_columna.append(nuevos_datos.get(clave, 0))
            
        df[df.shape[1]] = nueva_columna
        df.to_excel(ARCHIVO_EXCEL, index=False, header=False, sheet_name='Hoja1')
        print(f"[{nuevos_datos['Hora']}] Excel OK! Avance: {nuevos_datos['Avance_Actas']*100:.2f}% | Participación: {nuevos_datos['Participacion_Vivo']*100:.2f}%")
        
    except PermissionError:
        print("ERROR: Cierra el Excel para poder guardar los datos.")
    except Exception as e:
        print(f"Error en Excel: {e}")

if __name__ == "__main__":
    print("Iniciando Extractor ONPE Inteligente...")
    
    ultimo_avance_registrado = -1.0
    try:
        df_init = pd.read_excel(ARCHIVO_EXCEL, sheet_name='Hoja1', header=None)
        for _, row in df_init.iterrows():
            if str(row[0]).strip() == 'Avance_Actas':
                val_str = str(row.iloc[-1]).replace('%', '').replace(',', '.').strip()
                av = float(val_str)
                ultimo_avance_registrado = av / 100.0 if av > 1.0 else av
                break
        print(f"Último avance en Excel: {ultimo_avance_registrado*100:.2f}%")
    except Exception:
        print("Iniciando desde cero.")

    while True:
        datos = obtener_datos_json()
        if datos:
            if datos['Avance_Actas'] > ultimo_avance_registrado:
                actualizar_excel(datos)
                ultimo_avance_registrado = datos['Avance_Actas']
            else:
                print(f"[{datos['Hora']}] Sin cambios ({datos['Avance_Actas']*100:.2f}%). Esperando...")
        
        time.sleep(1800) # Revisa cada 30 min
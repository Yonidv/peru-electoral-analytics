import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import json
import os

# ==========================================
# 1. CONSTANTES HISTÓRICAS Y CONFIGURACIÓN
# ==========================================

# Perfil PEX extraído de tu JSON (Tendencia Real Actualizada)
PERFIL_PEX_REAL = {
    "Rafael López Aliaga": 0.25978,
    "Keiko Fujimori": 0.16358,
    "Jorge Nieto": 0.11124,
    "Carlos Álvarez": 0.10612,
    "Ricardo Belmont": 0.09013,
    "Alfonso López Chau": 0.06947,
    "Roberto Sánchez": 0.025,
    "Otros": 0.1535
}

def calcular_remanente_pex_dinamico(votos_validos_totales):
    """
    Calcula cuánto falta del extranjero basándose en la participación 
    histórica y los electores hábiles fuera (1.2M).
    """
    # Electores en el extranjero: 1,210,813
    # Participación estimada (históricamente baja en PEX): 35% - 40%
    VOTOS_PEX_ESPERADOS = 1210813 * 0.38 
    
    try:
        if not os.path.exists('estado_regional_v3.json'):
            return 0
        
        with open('estado_regional_v3.json', 'r') as f:
            estado_reg = json.load(f)
        
        # Lo que la ONPE ya contó en las 25 regiones nacionales
        votos_nacionales_contados = sum(d['total_val'] for d in estado_reg.values())
        
        # Lo que queda es el PEX ya procesado por ONPE
        votos_pex_contados = max(0, votos_validos_totales - votos_nacionales_contados)
        
        # El remanente real del extranjero
        remanente_pex = max(0, VOTOS_PEX_ESPERADOS - votos_pex_contados)
        return remanente_pex
    except:
        return 0 # Si falla, no asumimos votos extra para no sesgar

ELECTORES_2026 = 27325432
PARTICIPACION_HISTORICA = 0.70048
PCT_VALIDOS_HISTORICO = 0.81296

# --- DATOS ACTUALIZADOS ---
PRIORS_ENCUESTAS = {
    "Keiko Fujimori": 0.1695,
    "Rafael López Aliaga": 0.121,
    "Jorge Nieto": 0.1115,
    "Ricardo Belmont": 0.101,
    "Roberto Sánchez": 0.109,
    "Carlos Álvarez": 0.081,
    "Alfonso López Chau": 0.077,
    "Marisol Pérez Tello": 0.025,
    "César Acuña": 0.020,
    "Yonhy Lescano": 0.015,
    "Wolfgang Grozo": 0.008,
    "Mario Vizcarra": 0.008
}

suma_priors_top = sum(PRIORS_ENCUESTAS.values())
PRIORS_ENCUESTAS["Otros"] = max(0.01, 1.0 - suma_priors_top)

PERFIL_RURAL = {
    "Keiko Fujimori": 0.30,
    "Roberto Sánchez": 0.40,
    "Alfonso López Chau": 0.120,
    "Ricardo Belmont": 0.067,
    "César Acuña": 0.01,
    "Rafael López Aliaga": 0.01,
    "Carlos Álvarez": 0.05,
    "Jorge Nieto": 0.20,
    "Marisol Pérez Tello": 0.027,
    "Luna": 0.0
}

suma_rural_top = sum(PERFIL_RURAL.values())
PERFIL_RURAL["Otros"] = max(0.01, 1.0 - suma_rural_top)

MASTER_KEYS = list(PRIORS_ENCUESTAS.keys())

# ==========================================
# 2. TABLA DE RURALIDAD Y CÁLCULO DINÁMICO
# ==========================================

# Tabla de ruralidad real por departamento (Basada en datos INEI)
TABLA_RURALIDAD = {
    "010000": 0.55, "020000": 0.41, "030000": 0.50, "040000": 0.09,
    "050000": 0.47, "060000": 0.57, "240000": 0.01, "070000": 0.40,
    "080000": 0.65, "090000": 0.47, "100000": 0.12, "110000": 0.31,
    "120000": 0.25, "130000": 0.14, "140000": 0.05, "150000": 0.40,
    "160000": 0.25, "170000": 0.15, "180000": 0.40, "190000": 0.25,
    "200000": 0.51, "210000": 0.36, "220000": 0.10, "230000": 0.10,
    "250000": 0.30
}

def calcular_fuerza_rural_dinamica():
    """Calcula el peso rural real de las actas que faltan basándose en el analizador regional."""
    if not os.path.exists('estado_regional_v3.json'):
        return None
    
    try:
        with open('estado_regional_v3.json', 'r') as f:
            estado = json.load(f)
        
        votos_pendientes_rurales = 0
        votos_pendientes_totales = 0
        
        for ubigeo, data in estado.items():
            avance = data['avance']
            # Estimamos votos totales del departamento basándonos en lo contado
            total_estimado_dep = data['total_val'] / avance if avance > 0.05 else 100000
            pendientes_dep = total_estimado_dep * (1 - avance)
            
            ruralidad_dep = TABLA_RURALIDAD.get(ubigeo, 0.30) # 30% por defecto si no está
            
            votos_pendientes_rurales += (pendientes_dep * ruralidad_dep)
            votos_pendientes_totales += pendientes_dep
            
        if votos_pendientes_totales == 0: return 0.30
        
        fuerza_calculada = votos_pendientes_rurales / votos_pendientes_totales
        return np.clip(fuerza_calculada, 0.0, 1.0)
    except Exception as e:
        print(f"Error calculando fuerza rural dinámica: {e}")
        return None

# ==========================================
# 3. LECTURA DE DATOS BARRIDO TOTAL
# ==========================================
def leer_excel_historial(ruta='resultados_vivo.xlsx'):
    try:
        df = pd.read_excel(ruta, sheet_name='Hoja1', header=None)
        df.dropna(how='all', inplace=True)
        
        historial_datos = []
        historial_candidatos = []
        
        for col_idx in range(1, df.shape[1]):
            col_data = df.iloc[:, [0, col_idx]].copy()
            col_data.columns = ['Etiqueta', 'Valor']
            col_data.dropna(inplace=True)
            
            if col_data.empty: continue
            
            datos = {'Fuerza_Rural_Faltante': 0.0}
            candidatos = {}
            
            for _, row in col_data.iterrows():
                llave = str(row['Etiqueta']).strip()
                valor = row['Valor']
                
                if llave == 'Hora': datos['Hora'] = str(valor)
                elif llave == 'Avance_Actas':
                    val_str = str(valor).replace('%', '').replace(',', '.').strip()
                    try:
                        av = float(val_str)
                        datos['Avance'] = av / 100.0 if av > 1.0 else av
                    except ValueError:
                        datos['Avance'] = 0.01
                elif llave == 'Votos_Emitidos_Totales': datos['Votos_Emitidos'] = int(valor)
                elif llave == 'Votos_Validos_Totales': datos['Votos_Validos'] = int(valor)
                elif llave == 'Fuerza_Rural_Faltante': 
                    try:
                        datos['Fuerza_Rural_Faltante'] = float(str(valor).replace(',', '.'))
                    except ValueError:
                        datos['Fuerza_Rural_Faltante'] = 0.0
                else: candidatos[llave] = int(valor)
                    
            if 'Votos_Emitidos' in datos and 'Votos_Validos' in datos:
                historial_datos.append(datos)
                historial_candidatos.append(candidatos)
                
        return historial_datos, historial_candidatos
    except Exception as e:
        print(f"Error leyendo Excel: {e}")
        return None, None

# ==========================================
# 4. MOTOR MONTE CARLO (SEGREGADO NAC/PEX)
# ==========================================
def simular_eleccion(datos, candidatos_excel, iteraciones=10000, imprimir_reporte=False):
    avance = datos['Avance']
    votos_validos_totales = datos.get('Votos_Validos', 0)
    votos_emitidos_totales = datos.get('Votos_Emitidos', 0)
    
    # --- AUTOMATIZACIÓN DE FUERZA RURAL ---
    fuerza_dinamica = calcular_fuerza_rural_dinamica()
    if fuerza_dinamica is not None:
        fuerza_rural = fuerza_dinamica
        fuente_rural = "DINÁMICO (Regional)"
    else:
        fuerza_rural = np.clip(datos.get('Fuerza_Rural_Faltante', 0.30), 0.0, 1.0)
        fuente_rural = "MANUAL (Excel)"

    if avance <= 0 or avance > 1: return {}

    pct_validos_vivo = votos_validos_totales / votos_emitidos_totales if votos_emitidos_totales > 0 else PCT_VALIDOS_HISTORICO
    pct_validos_esperado = (PCT_VALIDOS_HISTORICO * (1 - avance)) + (pct_validos_vivo * avance)
    
    participacion_actual = datos.get('Participacion_Vivo', PARTICIPACION_HISTORICA)
    participacion_esperada = (PARTICIPACION_HISTORICA * (1 - avance)) + (participacion_actual * avance)
    
    votos_validos_base = ELECTORES_2026 * participacion_esperada * pct_validos_esperado
    
    if avance == 1.0:
        votos_esperados_finales = votos_validos_totales
        votos_restantes = 0
    else:
        proyeccion_actual = votos_validos_totales / avance
        votos_esperados_finales = (votos_validos_base * (1 - avance)) + (proyeccion_actual * avance)
        votos_restantes = max(votos_validos_totales * 0.01, votos_esperados_finales - votos_validos_totales)
    
    # --- CÁLCULO DE REMANENTES SEGREGADOS ---
    remanente_pex = calcular_remanente_pex_dinamico(votos_validos_totales)
    remanente_nacional = max(0, votos_restantes - remanente_pex)
    
    candidatos_sim = {cand: candidatos_excel.get(cand, 0) for cand in MASTER_KEYS if cand != "Otros"}
    votos_top_real = sum(candidatos_sim.values())
    candidatos_sim["Otros"] = max(0, votos_validos_totales - votos_top_real)
    
    peso_encuesta = np.exp(-2.0 * avance)
    modificador_litigio = 0.1 if avance >= 0.96 else 1.0
    
    resultados = {cand: {'victorias': 0, 'votos_simulados': np.zeros(iteraciones)} for cand in MASTER_KEYS}
    
    for i in range(iteraciones):
        sorteos_nacionales = {}
        sorteos_pex = {}
        
        for cand in MASTER_KEYS:
            # 1. Componente Nacional (Híbrido Urbano/Rural del Analizador)
            prior_nacional = PRIORS_ENCUESTAS.get(cand, 0.01)
            prior_rural = PERFIL_RURAL.get(cand, 0.01)
            
            # Cálculo de esperanza nacional (igual que antes)
            esperanza_estandar = (peso_encuesta * prior_nacional) + ((1 - peso_encuesta) * (candidatos_sim[cand] / votos_validos_totales if votos_validos_totales > 0 else 0))
            esp_nac = (esperanza_estandar * (1 - fuerza_rural)) + (prior_rural * fuerza_rural)
            
            desv_nac = 0.028 * np.sqrt(1 - avance) * modificador_litigio
            sorteos_nacionales[cand] = np.clip(np.random.normal(esp_nac, desv_nac), 0.0001, 1.0)
            
            # 2. Componente PEX (Voto Extranjero)
            esp_pex = PERFIL_PEX_REAL.get(cand, 0.01)
            desv_pex = 0.045 # Mayor volatilidad por ser muestra pequeña
            sorteos_pex[cand] = np.clip(np.random.normal(esp_pex, desv_pex), 0.0001, 1.0)

        # Normalización
        sum_nac = sum(sorteos_nacionales.values())
        sum_pex = sum(sorteos_pex.values())
        
        votos_finales_iteracion = {}
        for cand in MASTER_KEYS:
            # Distribución de remanentes
            v_nac = (sorteos_nacionales[cand] / sum_nac) * remanente_nacional
            v_pex = (sorteos_pex[cand] / sum_pex) * remanente_pex
            
            # Voto final = Contado + Proyección Nacional + Proyección PEX
            votos_finales_iteracion[cand] = candidatos_sim[cand] + v_nac + v_pex
            resultados[cand]['votos_simulados'][i] = votos_finales_iteracion[cand]
            
        ranking = sorted([(c, v) for c, v in votos_finales_iteracion.items() if c != "Otros"], key=lambda x: x[1], reverse=True)
        
        if len(ranking) >= 1: resultados[ranking[0][0]]['victorias'] += 1
        if len(ranking) >= 2: resultados[ranking[1][0]]['victorias'] += 1

    salida = []
    probabilidades = {'Hora': datos.get('Hora', 'N/A'), 'Avance': avance}
    
    for cand, data in resultados.items():
        if cand == "Otros": continue
        prob = (data['victorias'] / iteraciones) * 100
        media_votos = np.mean(data['votos_simulados'])
        piso_votos = np.percentile(data['votos_simulados'], 16)
        salida.append((cand, prob, media_votos, piso_votos))
        probabilidades[cand] = prob
        
    salida.sort(key=lambda x: x[1], reverse=True)
    
    if imprimir_reporte:
        print("\n" + "="*80)
        print(f"SIMULADOR ONPE V8 - ({datos['Hora']}) | Avance: {avance*100:.2f}%")
        print(f"Peso Rural: {fuerza_rural*100:.1f}% [{fuente_rural}] | Votos PEX Pendientes Est.: {int(remanente_pex):,}")
        print(f"Proyección Valid Final: {int(votos_esperados_finales):,}")
        print("="*80)
        print(f"{'Candidato':<22} | {'Prob. Top 2':<11} | {'Media Proyectada':<18} | {'Escenario Ácido (-1 SD)'}")
        print("-" * 80)
        for cand, prob, media, piso in salida:
            if prob >= 0.1 or media > (votos_validos_totales * 0.01):
                prob_str = f"{prob:>8.1f}%" if prob >= 0.1 else "< 0.1%"
                print(f"{cand:<22} | {prob_str:<11} | {int(media):<18,} | {int(piso):,}")
        print("="*80)
        
    return probabilidades

# ==========================================
# 5. EJECUCIÓN PRINCIPAL Y DASHBOARD VISUAL
# ==========================================
if __name__ == "__main__":
    h_datos, h_candidatos = leer_excel_historial()
    
    if h_datos and h_candidatos:
        print("Recalculando historial completo desde Excel...")
        historial_completo = []
        total_columnas = len(h_datos)
        
        for i in range(total_columnas):
            datos = h_datos[i]
            cands = h_candidatos[i]
            es_ultimo = (i == total_columnas - 1)
            
            probs = simular_eleccion(datos, cands, iteraciones=10000, imprimir_reporte=es_ultimo)
            if probs: historial_completo.append(probs)
            
        df_historial = pd.DataFrame(historial_completo)
        df_historial.fillna(0.0, inplace=True)
        df_historial.to_csv('historial_probabilidades.csv', index=False)
        
      # --- GENERAR DASHBOARD (CON ZOOM DE RECENCIA) ---
        plt.style.use('dark_background')
        
        # 1. Aplicamos el zoom: Solo tomamos los últimos 20 puntos de tiempo
        df_plot = df_historial.tail(20).copy()
        horas_str = df_plot['Hora'].astype(str).tolist()
        
        ancho_dinamico = 12 # Al ser 20 puntos, el ancho puede ser fijo y cómodo
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(ancho_dinamico, 14), gridspec_kw={'height_ratios': [2, 1.2]})
        fig.suptitle('DETALLE DE TENDENCIA: ÚLTIMOS 20 CORTES', fontsize=18, fontweight='bold', y=0.96)
        
        candidatos_plot = [c for c in df_plot.columns if c not in ['Hora', 'Avance', 'Otros']]
        colores = plt.cm.tab20.colors
        posiciones_x = list(range(len(horas_str)))
        
        # --- PANEL 1: TENDENCIAS (LÍNEAS CON ZOOM Y-AXIS) ---
        ax1.axhline(y=50, color='white', linestyle='--', alpha=0.3)
        
        for idx, cand in enumerate(candidatos_plot):
            color_cand = colores[idx % len(colores)]
            
            # Solo graficamos si el candidato tiene presencia real en este zoom
            if df_plot[cand].max() >= 0.1: 
                ax1.plot(posiciones_x, df_plot[cand], marker='o', markersize=6, linewidth=2.5, label=cand, color=color_cand)
        
        # 2. Zoom dinámico en el Eje Y para ver la pelea Sánchez vs Aliaga
        # Buscamos el valor mínimo y máximo en el rango de los candidatos competitivos
        competitivos = ["Roberto Sánchez", "Rafael López Aliaga"]
        val_min = df_plot[competitivos].min().min()
        val_max = df_plot[competitivos].max().max()
        
        # Ajustamos el límite: un poco por debajo del mínimo y un poco por encima del máximo
        ax1.set_ylim(max(0, val_min - 5), min(105, val_max + 10))
                
        ax1.set_title('Evolución de Probabilidades (Zona de Combate)', fontsize=14, pad=15)
        ax1.set_ylabel('Probabilidad (%)', fontsize=12)
        ax1.set_xticks(posiciones_x)
        ax1.set_xticklabels(horas_str, fontsize=11, rotation=45, ha='right')
        ax1.legend(loc='center left', bbox_to_anchor=(1.02, 0.5))

        # --- PANEL 2: SNAPSHOT EXACTO (Se mantiene igual pero con df_plot) ---
        ultimo_corte = df_plot.iloc[-1].drop(['Hora', 'Avance'], errors='ignore')
        # ... resto de tu código de barras ...
        if 'Otros' in ultimo_corte: ultimo_corte = ultimo_corte.drop('Otros')
        
        ultimo_corte = ultimo_corte[ultimo_corte >= 0.1].astype(float).sort_values(ascending=True)
        colores_barras = [colores[candidatos_plot.index(c) % len(colores)] for c in ultimo_corte.index]
        
        barras = ax2.barh(ultimo_corte.index, ultimo_corte.values, color=colores_barras, alpha=0.85, edgecolor='white', linewidth=0.5)
        
        for barra, val in zip(barras, ultimo_corte.values):
            ax2.text(val + 0.8, barra.get_y() + barra.get_height()/2, f'{val:.1f}%', va='center', fontsize=11, fontweight='bold', color='white')
            
        ax2.set_title(f'Estado Actual - Corte de las {horas_str[-1]}', fontsize=14, pad=15)
        ax2.set_xlabel('Probabilidad Actual (%)', fontsize=12)
        ax2.set_xlim(0, 108)
        ax2.grid(True, axis='x', linestyle='--', alpha=0.3)
        ax2.grid(False, axis='y')
        ax2.spines['top'].set_visible(False)
        ax2.spines['right'].set_visible(False)
        
        fig.text(0.98, 0.02, 'Simulador V8 • Modelo Bayesiano', fontsize=9, ha='right', va='bottom', alpha=0.4, style='italic')
        
        plt.tight_layout(rect=[0, 0.03, 1, 0.95])
        plt.savefig('tendencias.png', dpi=200, facecolor=fig.get_facecolor(), bbox_inches='tight')
        plt.close()
        print("\n=> Dashboard 'tendencias.png' generado exitosamente. Revisa la imagen.")
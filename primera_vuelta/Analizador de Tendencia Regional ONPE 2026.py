import requests
import time
import json
import os
import pandas as pd
import numpy as np
import unicodedata
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib import font_manager
import datetime

# ==========================================
# 1. CONFIGURACIÓN Y CONSTANTES
# ==========================================
DEPARTAMENTOS = {
    "010000": "AMAZONAS", "020000": "ANCASH", "030000": "APURIMAC",
    "040000": "AREQUIPA", "050000": "AYACUCHO", "060000": "CAJAMARCA",
    "240000": "CALLAO", "070000": "CUSCO", "080000": "HUANCAVELICA",
    "090000": "HUANUCO", "100000": "ICA", "110000": "JUNIN",
    "120000": "LA LIBERTAD", "130000": "LAMBAYEQUE", "140000": "LIMA",
    "150000": "LORETO", "160000": "MADRE DE DIOS", "170000": "MOQUEGUA",
    "180000": "PASCO", "190000": "PIURA", "200000": "PUNO",
    "210000": "SAN MARTIN", "220000": "TACNA", "230000": "TUMBES",
    "250000": "UCAYALI"
}

def norm(t):
    return "".join(c for c in unicodedata.normalize('NFD', t) if unicodedata.category(c) != 'Mn').upper().strip()

CANDIDATOS_MAP = {
    "RLA": norm("RAFAEL BERNARDO LÓPEZ ALIAGA CAZORLA"),
    "NIETO": norm("JORGE NIETO MONTESINOS"),
    "SANCHEZ": norm("ROBERTO HELBERT SANCHEZ PALOMINO")
}

COLORES = {
    "RLA":    "#3b82f6",   # Azul
    "SANCHEZ":"#22c55e",   # Verde
    "NIETO":  "#f59e0b",   # Amber
}

FILE_ESTADO  = "estado_regional_v4.json"
FILE_LOG     = "historial_tendencias_v4.csv"
FILE_GRAFICO_LINEAS = "tendencias_linea.png"
FILE_GRAFICO_DUELO  = "tendencias_duelo.png"

COL_AV = "AVANCE_NAC"
COL_TS = "TS"

# ================================
# ⚠️ PEGA TU COOKIE AQUÍ ABAJO
# ================================
# ================================
# ⚠️ CONFIGURACIÓN DE SESIÓN (BRAVE)
# ================================
# Pega aquí el valor que sigue a cf_clearance= hasta el final de las comillas
COOKIE_STRING = "cf_clearance=i4nGwXNKji16Jv6M8MMY2dpSs7yuidB7hvSj9AOq9VQ-1775185278-1.2.1.1-27wYdl6j7INgpNxggk8UBrrNIbbG7X9rSwhwcoNmF0FkDY.mEl7oM35e92y6Cr_0TYxZcxp1PIZbr5A2oHpADuOPac72qTSTeEN6xckHqyc1MJREArhpbIAW8adFshsMCsR_xixoJiKrMNL9XUcty8mtwyOs8IAxIJeJdBwPpZOKXKKtQV7Ml6d25FOM7.IBa4OERIriSKGQZ1yKAZ2wg7M8YBDfPVQ957UjyXozJik"

HEADERS = {
    "accept": "*/*",
    "accept-language": "es-419,es;q=0.6",
    "content-type": "application/json",
    "cookie": COOKIE_STRING,
    "priority": "u=1, i",
    "referer": "https://resultadoelectoral.onpe.gob.pe/main/presidenciales",
    "sec-ch-ua": '"Brave";v="147", "Not.A/Brand";v="8", "Chromium";v="147"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "sec-gpc": "1",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
}

# ==========================================
# 2. PERSISTENCIA (ACTUALIZADO)
# ==========================================
def cargar_estado():
    if os.path.exists(FILE_ESTADO):
        with open(FILE_ESTADO, 'r') as f:
            return json.load(f)
    return {}

def guardar_estado(estado):
    with open(FILE_ESTADO, 'w') as f:
        json.dump(estado, f)

def loggear(data_row):
    df = pd.DataFrame([data_row])
    # Aseguramos que la columna MARGEN_JEE esté en el orden correcto
    cols_order = [COL_AV, COL_TS, "MARGEN_JEE"] + list(CANDIDATOS_MAP.values())
    
    for c in cols_order:
        if c not in df.columns: df[c] = 0
    df = df[cols_order]
    
    # Lógica estricta de creación/adición
    if not os.path.exists(FILE_LOG):
        # Si no existe, lo crea en modo escritura ('w') con cabeceras
        df.to_csv(FILE_LOG, mode='w', header=True, index=False, encoding='utf-8-sig')
    else:
        # Si ya existe, añade la fila ('a') sin repetir cabeceras
        df.to_csv(FILE_LOG, mode='a', header=False, index=False, encoding='utf-8-sig')

# ==========================================
# 3. CORE ANALÍTICO (CÁLCULO DINÁMICO)
# ==========================================
def fetch_data_nacional():
    totales_reales = {k: 0 for k in CANDIDATOS_MAP}
    proyeccion_nac = {k: 0 for k in CANDIDATOS_MAP}
    
    suma_votos_validos_reales = 0
    suma_votos_validos_esperados = 0
    total_votos_disputa_nac = 0 # NUEVO ACUMULADOR
    
    print("\n--- PROCESANDO VOTO NACIONAL (Densidad Dinámica) ---")
    
    for ubigeo, nombre in DEPARTAMENTOS.items():
        try:
            url_t = (f"https://resultadoelectoral.onpe.gob.pe/presentacion-backend/resumen-general/totales"
                     f"?idAmbitoGeografico=1&idEleccion=10&tipoFiltro=ubigeo_nivel_01&idUbigeoDepartamento={ubigeo}")
            url_v = (f"https://resultadoelectoral.onpe.gob.pe/presentacion-backend/eleccion-presidencial/"
                     f"participantes-ubicacion-geografica-nombre?tipoFiltro=ubigeo_nivel_01&idAmbitoGeografico=1"
                     f"&ubigeoNivel1={ubigeo}&idEleccion=10")
            
            r_t = requests.get(url_t, headers=HEADERS, timeout=10)
            r_v = requests.get(url_v, headers=HEADERS, timeout=10)
            
            if r_t.status_code != 200 or r_v.status_code != 200: continue
            
            try:
                d_t = r_t.json().get('data')
                d_v = r_v.json().get('data')
            except ValueError: continue
                
            if not d_t or not d_v: continue
            
            av = float(d_t.get('actasContabilizadas', 0)) / 100.0
            if av == 0: continue
            
            # --- CÁLCULO DINÁMICO DE ACTAS EN EL JEE ---
            enviadas_jee = int(d_t.get('enviadasJee', 0))
            contabilizadas = int(d_t.get('contabilizadas', 1))
            validos_region = float(d_t.get('totalVotosValidos', 0))
            
            # Calculamos la densidad (votos por acta) de esta región en este instante
            if contabilizadas > 0:
                votos_por_acta = validos_region / contabilizadas
                total_votos_disputa_nac += (enviadas_jee * votos_por_acta)
            # -------------------------------------------

            votos_loc = {k: 0 for k in CANDIDATOS_MAP}
            for p in d_v:
                n = norm(p.get('nombreCandidato', ''))
                for k, v_norm in CANDIDATOS_MAP.items():
                    if v_norm in n:
                        votos_loc[k] = int(p.get('totalVotosValidos', 0))
            
            suma_votos_validos_reales += validos_region
            suma_votos_validos_esperados += (validos_region / av)
            
            for k in votos_loc: 
                totales_reales[k] += votos_loc[k]
                proyeccion_nac[k] += int(votos_loc[k] / av)
            
            print(f"{nombre[:15]:<15} | {av*100:>6.2f}% | R:{votos_loc['RLA']:>8,} | S:{votos_loc['SANCHEZ']:>8}")
            
        except Exception: continue
            
    av_nac_real = (suma_votos_validos_reales / suma_votos_validos_esperados) if suma_votos_validos_esperados > 0 else 0
    return totales_reales, proyeccion_nac, av_nac_real, total_votos_disputa_nac

def fetch_data_extranjero():
    print("\n--- PROCESANDO VOTO EXTRANJERO ---")
    url_t = ("https://resultadoelectoral.onpe.gob.pe/presentacion-backend/resumen-general/totales"
             "?idAmbitoGeografico=2&idEleccion=10&tipoFiltro=ambito_geografico")
    url_v = ("https://resultadoelectoral.onpe.gob.pe/presentacion-backend/eleccion-presidencial/"
             "participantes-ubicacion-geografica-nombre?tipoFiltro=ambito_geografico"
             "&idAmbitoGeografico=2&listRegiones=TODOS,PER%C3%9A,EXTRANJERO&idEleccion=10")
    
    try:
        r_t = requests.get(url_t, headers=HEADERS, timeout=15)
        r_v = requests.get(url_v, headers=HEADERS, timeout=15)
        
        if r_t.status_code != 200 or r_v.status_code != 200: return None, 0, 0
        
        d_t = r_t.json().get('data', {})
        data_v = r_v.json().get('data', [])
        
        av_pex = float(d_t.get('actasContabilizadas', 0)) / 100.0
        
        # --- CÁLCULO DINÁMICO DE ACTAS EN EL JEE (PEX) ---
        enviadas_jee = int(d_t.get('enviadasJee', 0))
        contabilizadas = int(d_t.get('contabilizadas', 1))
        validos_pex = float(d_t.get('totalVotosValidos', 0))
        
        votos_disputa_pex = 0
        if contabilizadas > 0:
            votos_por_acta = validos_pex / contabilizadas
            votos_disputa_pex = enviadas_jee * votos_por_acta
        # -------------------------------------------------

        votos_ext = {k: 0 for k in CANDIDATOS_MAP}
        
        for p in data_v:
            n = norm(p.get('nombreCandidato', ''))
            for k, v_norm in CANDIDATOS_MAP.items():
                if v_norm in n:
                    votos_ext[k] = int(p.get('totalVotosValidos', 0))
        
        print(f"{'EXTRANJERO':<15} | {av_pex*100:>6.2f}% | R:{votos_ext['RLA']:>8,} | S:{votos_ext['SANCHEZ']:>8}")
        return votos_ext, av_pex, votos_disputa_pex
    except Exception: return None, 0, 0

# ==========================================
# 4. GENERACIÓN DE GRÁFICOS (ACTUALIZADO)
# ==========================================
def generar_grafico_lineas():
    if not os.path.exists(FILE_LOG): return
    # Cambia esto en ambas funciones de gráficos:
    df = pd.read_csv(FILE_LOG, encoding='utf-8-sig', on_bad_lines='skip')
    df.columns = df.columns.str.strip()
    
    c_rla = CANDIDATOS_MAP["RLA"]
    c_nieto = CANDIDATOS_MAP["NIETO"]
    c_sanchez = CANDIDATOS_MAP["SANCHEZ"]
    
    df[COL_TS] = pd.to_numeric(df[COL_TS], errors='coerce')
    df = df.dropna(subset=[COL_TS]).reset_index(drop=True)

    # Filtramos puntos irrelevantes y tomamos últimos 20 registros
    df = df[df[c_rla] > 1500000].tail(20).reset_index(drop=True)

    if len(df) < 2: return
    
    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(12, 6))
    
    x = range(len(df))
    horas = df[COL_TS].apply(lambda t: time.strftime('%H:%M', time.localtime(t)))
    
    # Líneas principales
    ax.plot(x, df[c_rla], label="López Aliaga", color=COLORES["RLA"], lw=2.5, marker='o', markersize=4)
    ax.plot(x, df[c_nieto], label="Nieto", color=COLORES["NIETO"], lw=2, ls='--', alpha=0.7)
    ax.plot(x, df[c_sanchez], label="Sánchez", color=COLORES["SANCHEZ"], lw=2.5, marker='s', markersize=4)
    
    # --- SOMBRAS DE INCERTIDUMBRE (MARGEN JEE) ---
    if "MARGEN_JEE" in df.columns:
        margen_jee_serie = df["MARGEN_JEE"]
        # Relleno para RLA (hacia arriba y abajo)
        ax.fill_between(x, df[c_rla] - margen_jee_serie, df[c_rla] + margen_jee_serie, color=COLORES["RLA"], alpha=0.15, linewidth=0)
        # Relleno para SANCHEZ
        ax.fill_between(x, df[c_sanchez] - margen_jee_serie, df[c_sanchez] + margen_jee_serie, color=COLORES["SANCHEZ"], alpha=0.15, linewidth=0)
    else:
        margen_jee_serie = pd.Series([0] * len(df))

    # MEGA ZOOM DINÁMICO
    ymin_global = min((df[c_rla] - margen_jee_serie).min(), (df[c_sanchez] - margen_jee_serie).min())
    ymax_global = max((df[c_rla] + margen_jee_serie).max(), (df[c_sanchez] + margen_jee_serie).max())
    ax.set_ylim(ymin_global - 1500, ymax_global + 1500)

    labels_av = [f"{v:.1f}%" for v in df[COL_AV]]
    
    ax.set_title('ZONA DE COMBATE + INCERTIDUMBRE LEGAL (JEE)', fontsize=14, fontweight='bold')
    ax.set_ylabel('Votos Proyectados')
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{int(x):,}"))
    ax.set_xticks(x)
    ax.set_xticklabels([f"{h}\n({a})" for h, a in zip(horas, labels_av)], rotation=45, ha='right', fontsize=8)
    ax.legend(loc='upper left')
    ax.grid(axis='y', linestyle='--', alpha=0.2)
    
    plt.tight_layout()
    plt.savefig(FILE_GRAFICO_LINEAS, dpi=150)
    plt.close()

def generar_grafico_duelo():
    if not os.path.exists(FILE_LOG): return
    # Cambia esto en ambas funciones de gráficos:
    df = pd.read_csv(FILE_LOG, encoding='utf-8-sig', on_bad_lines='skip')
    df.columns = df.columns.str.strip()
    
    c_rla = CANDIDATOS_MAP["RLA"]
    c_sanchez = CANDIDATOS_MAP["SANCHEZ"]
    
    required = [COL_TS, COL_AV, c_rla, c_sanchez]
    if not all(c in df.columns for c in required): return
    
    df[COL_TS] = pd.to_numeric(df[COL_TS], errors='coerce')
    df[COL_AV] = pd.to_numeric(df[COL_AV], errors='coerce')
    df = df.dropna(subset=required).reset_index(drop=True)
    
    if len(df) < 2: return

    # ==========================================================
    # 🎯 VENTANA DINÁMICA DE AVANCE MÍNIMO (Anti-Goteo)
    # ==========================================================
    # Buscamos un 1.0% atrás, pero exigimos al menos 0.1% para que el gráfico sea real
    TARGET_DELTA = 1.0  
    MINIMO_EXIGIDO = 0.10 
    
    current_av = df[COL_AV].iloc[-1]
    
    # Buscamos el punto ideal (1% atrás)
    ideales = df[df[COL_AV] <= (current_av - TARGET_DELTA)]
    
    if not ideales.empty:
        start_index = ideales.index[-1]
    else:
        # Si no hay 1%, buscamos lo más antiguo que garantice el MINIMO_EXIGIDO
        validos = df[df[COL_AV] <= (current_av - MINIMO_EXIGIDO)]
        if not validos.empty:
            start_index = validos.index[-1]
        else:
            # Si la ONPE está muerta, usamos todo el log disponible
            start_index = 0

    recent = df.loc[start_index:].copy()
    
    av_start = recent[COL_AV].iloc[0]
    av_end = recent[COL_AV].iloc[-1]
    av_delta = av_end - av_start
    
    av_delta_safe = max(av_delta, 0.001)
    
    nuevos_rla = recent[c_rla].iloc[-1] - recent[c_rla].iloc[0]
    nuevos_sanchez = recent[c_sanchez].iloc[-1] - recent[c_sanchez].iloc[0]
    
    speed_rla = nuevos_rla / av_delta_safe
    speed_sanchez = nuevos_sanchez / av_delta_safe
    
    total_nuevos_abs = abs(nuevos_rla) + abs(nuevos_sanchez)
    total_nuevos = max(total_nuevos_abs, 1)
    
    fuerza_rla = (nuevos_rla / total_nuevos) * 100
    fuerza_sanchez = (nuevos_sanchez / total_nuevos) * 100
    
    def get_arrow(votos_delta, avance_delta):
        if avance_delta < 0.01: return "-> ESTABLE"
        tasa = votos_delta / avance_delta
        if tasa > 50000:  return "↑↑↑ SUBIDON ACELERADO"
        if tasa > 15000:  return "↑↑ SUBIENDO MUCHO"
        if tasa > 2000:   return "↑ SUBIENDO"
        if tasa > -2000:  return "↗ ESTABLE +"
        if tasa > -15000: return "↓ BAJANDO"
        if tasa > -50000: return "↓↓ BAJANDO MUCHO"
        return "↓↓↓ BAJON ACELERADO"
    
    arrow_rla = get_arrow(nuevos_rla, av_delta)
    arrow_sanchez = get_arrow(nuevos_sanchez, av_delta)
    brecha_actual = recent[c_rla].iloc[-1] - recent[c_sanchez].iloc[-1]
    
    plt.style.use('dark_background')
    fig = plt.figure(figsize=(10, 6), facecolor='#111827')
    gs = fig.add_gridspec(2, 2, width_ratios=[1.5, 1], height_ratios=[1, 1])
    ax1 = fig.add_subplot(gs[:, 0])
    ax1.set_facecolor('#1f2937')
    
    y_pos = [0, 1]
    fuerzas = [fuerza_rla, fuerza_sanchez]
    colores = [COLORES["RLA"], COLORES["SANCHEZ"]]
    labels = ["López Aliaga", "Sánchez"]
    
    bars = ax1.barh(y_pos, fuerzas, color=colores, height=0.5, alpha=0.8)
    ax1.set_yticks(y_pos)
    ax1.set_yticklabels(labels, fontsize=14, fontweight='bold')
    ax1.set_xlim(-100, 100)
    ax1.axvline(0, color='white', linewidth=1)
    
    for bar, val in zip(bars, fuerzas):
        width = bar.get_width()
        label_x = width + 5 if width >= 0 else width - 5
        ax1.text(label_x, bar.get_y() + bar.get_height()/2, f"{val:.1f}%", 
                 ha='left' if width >=0 else 'right', va='center', color='white', fontsize=12, fontweight='bold')
    
    title_str = f'FUERZA DE TENDENCIA (Basado en +{av_delta:.2f}% Avance)'
    ax1.set_title(title_str, fontsize=14, color='white', pad=10)
    
    ax2 = fig.add_subplot(gs[:, 1])
    ax2.axis('off')
    
    texto_duelo = (
        f"ANÁLISIS DE DUELO\n"
        f"--------------------------\n\n"
        f"RANGO ANALIZADO:\n"
        f"Desde {av_start:.2f}% hasta {av_end:.2f}%\n"
        f"(Delta: {av_delta:.2f}%)\n\n"
        f"EFICIENCIA (Votos/1%):\n"
        f" [RLA]:   {speed_rla:>+10,.0f}\n"
        f" [SANC]:  {speed_sanchez:>+10,.0f}\n\n"
        f"TENDENCIA:\n"
        f"RLA:   {arrow_rla}\n"
        f"SANC:  {arrow_sanchez}\n\n"
        f"--------------------------\n"
        f"BRECHA ACTUAL:\n{int(brecha_actual):+,} votos"
    )
    
    ax2.text(0.5, 0.5, texto_duelo, transform=ax2.transAxes, fontsize=11,
             verticalalignment='center', horizontalalignment='center',
             fontfamily='sans-serif', color='white',
             bbox=dict(boxstyle='round', facecolor='#374151', edgecolor='white', alpha=0.9))
    
    plt.suptitle('⚡ DASHBOARD DE TENDENCIA EN VIVO ⚡', fontsize=16, color='white', y=0.98)
    plt.tight_layout(rect=[0, 0, 1, 0.95])
    plt.savefig(FILE_GRAFICO_DUELO, dpi=150, facecolor='#111827')
    plt.close()

# ==========================================
# 5. CICLO PRINCIPAL (INTEGRADO)
# ==========================================
def analizar():
    if "TU_COOKIE_AQUI" in COOKIE_STRING or len(COOKIE_STRING) < 50:
        print("\n[!!!] ERROR: Cookie no configurada.")
        return

    print(f"\n[{time.strftime('%H:%M:%S')}] INICIANDO ANÁLISIS FORENSE")

    # 1. Obtener datos Nacionales (Reales + Proyección + Disputa)
    votos_nac_reales, proyeccion_nac, av_nac, disputa_nac = fetch_data_nacional()
    
    if av_nac == 0:
        print("[!] Nacional retornó 0%. Posible bloqueo.")
        return

    # 2. Obtener datos Extranjero
    votos_ext_reales, av_pex, disputa_pex = fetch_data_extranjero()
    
    # Respaldo conservador si PEX falla
    if av_pex <= 0: av_pex = 0.50 

    # 3. Consolidar Totales
    totales_reales = {}
    proyeccion_final = {}
    
    for k in CANDIDATOS_MAP:
        nac_real = votos_nac_reales.get(k, 0)
        ext_real = votos_ext_reales.get(k, 0) if votos_ext_reales else 0
        totales_reales[k] = nac_real + ext_real
        
        # Proyección Final = Granular Nac + Proyección PEX
        proj_ext = int(ext_real / av_pex)
        proyeccion_final[k] = proyeccion_nac.get(k, 0) + proj_ext

# --- CÁLCULO DE INCERTIDUMBRE LEGAL REAL ---
    total_votos_en_disputa = disputa_nac + disputa_pex
    
    # 1. Volatilidad total (8% de las actas cambian de estado/se rescatan en el JEE)
    volatilidad_total = total_votos_en_disputa * 0.08
    
    # 2. Ventaja Neta Legal (Un buen equipo legal rescata el 65% vs el 35% del rival)
    # Diferencia neta a favor en el marcador = 30% del pozo volátil
    TASA_VENTAJA_NETA = 0.30 
    
    margen_abogados = int(volatilidad_total * TASA_VENTAJA_NETA)
    
    log_data = {
        COL_AV: round(av_nac * 100, 2),
        COL_TS: int(time.time()),
        "MARGEN_JEE": margen_abogados,
        **{CANDIDATOS_MAP[k]: proyeccion_final[k] for k in CANDIDATOS_MAP}
    }
    
    loggear(log_data)
    
    # === REPORTE DE CONSOLA: DUELO FINAL Y ESCENARIOS ===
    rla_base = proyeccion_final['RLA']
    sanc_base = proyeccion_final['SANCHEZ']
    brecha_base = rla_base - sanc_base
    
    print("\n" + "="*55)
    print(f"📊 PROYECCIÓN Y ESCENARIOS JEE (Avance Nacional {av_nac*100:.2f}%)")
    print("="*55)
    print(f"[ESTADO BASE - EXTRAPOLACIÓN PURA]")
    print(f"LÓPEZ ALIAGA : {rla_base:>12,} votos")
    print(f"SÁNCHEZ      : {sanc_base:>12,} votos")
    
    color_brecha = "\033[92m" if brecha_base > 0 else "\033[91m"
    print(f"BRECHA ACTUAL: {color_brecha}{brecha_base:>+12,}\033[0m votos\n")
    
    print(f"⚖️   GUERRA DE ABOGADOS (Impacto est. ±{margen_abogados:,} votos)")
    print(f"   [Masa total en JEE: {int(total_votos_en_disputa):,} votos]")
    print("-" * 55)
    
    # Escenario RLA+ (Gana actas impugnadas)
    brecha_rla = brecha_base + margen_abogados
    res_rla = "RLA PASA" if brecha_rla > 0 else "SANC SE MANTIENE"
    print(f"▶ Escenario RLA Favorable: {brecha_rla:>+10,} -> [{res_rla}]")
    
    # Escenario SANC+ (Gana actas impugnadas)
    brecha_sanc = brecha_base - margen_abogados
    res_sanc = "SANC PASA" if brecha_sanc < 0 else "RLA SE MANTIENE"
    print(f"▶ Escenario SANC Favorable: {brecha_sanc:>+10,} -> [{res_sanc}]")
    print("="*55)
    
    generar_grafico_lineas()
    generar_grafico_duelo()

if __name__ == "__main__":
    while True:
        try:
            analizar()
        except Exception as e:
            print(f"Error loop: {e}")
        time.sleep(900) # Chequeo cada 5 minutos
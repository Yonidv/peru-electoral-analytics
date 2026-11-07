"""
ONPE 2026 — Segunda Vuelta
Análisis con corrección de sesgo urbano/rural + calibración de redistribución de votos.

El lean de primera vuelta (K vs R en duelo directo) es un PRIOR.
Los resultados 2rv ya disponibles CALIBRAN ese prior: ajustamos α + β·lean_1rv
de modo que la redistribución del 82% restante quede implícita en la regresión.

Fuentes:
  - onpe_sv_resultados.db       : datos segunda vuelta
  - onpe_prov_proyeccion_*1530* : snapshot final 1ra vuelta (100% avance) → prior
"""

import sqlite3, os, sys
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as mticker
import matplotlib.patches as mpatches
from matplotlib.gridspec import GridSpec
from matplotlib.lines import Line2D
from datetime import datetime

# ── Config ─────────────────────────────────────────────────────────────────────
DB_PATH      = "onpe_sv_resultados.db"
PV_FINAL_CSV = "onpe_prov_proyeccion_20260516_1530.csv"

KEIKO   = "KEIKO SOFIA FUJIMORI HIGUCHI"
ROBERTO = "ROBERTO HELBERT SANCHEZ PALOMINO"

C_K  = "#C0392B"
C_R  = "#1565C0"
C_KL = "#E57373"   # keiko claro (estimado)
C_RL = "#64B5F6"   # roberto claro (estimado)
C_AV = "#546E7A"

# ── 1. Prior de 1ra vuelta ─────────────────────────────────────────────────────
def cargar_prior():
    if not os.path.exists(PV_FINAL_CSV):
        print(f"WARN: no se encontró {PV_FINAL_CSV}")
        return {}

    df = pd.read_csv(PV_FINAL_CSV, encoding="utf-8-sig")
    k = df[df["candidato"] == KEIKO][["departamento","provincia","votos_validos","total_actas","pct_actas_contab"]].rename(columns={"votos_validos":"vk"})
    r = df[df["candidato"] == ROBERTO][["departamento","provincia","votos_validos"]].rename(columns={"votos_validos":"vr"})
    # total votos todos los candidatos por unidad (para detectar lugares sin votación)
    tot_all = df.groupby(["departamento","provincia"])["votos_validos"].sum().reset_index().rename(columns={"votos_validos":"tot_all"})
    m = k.merge(r, on=["departamento","provincia"], how="outer").fillna(0)
    m = m.merge(tot_all, on=["departamento","provincia"], how="left")
    m["lean_kr"] = np.where((m["vk"]+m["vr"]) > 0, m["vk"]/(m["vk"]+m["vr"]), 0.5)

    # Unidades que escrutaron al 100% en 1rv y tuvieron 0 votos → sin votación real
    # (Venezuela, Kuwait, Irán, etc.) — se proyectan como 0 en 2rv
    sin_voto = set()
    prior = {}
    for _, row in m.iterrows():
        key = (row["departamento"], row["provincia"])
        es_void = (row["pct_actas_contab"] >= 99.9) and (row["tot_all"] == 0)
        if es_void:
            sin_voto.add(key)
        prior[key] = {
            "lean_kr":         row["lean_kr"],
            "total_actas_1rv": row["total_actas"],
            "tot_kr_1rv":      int(row["vk"] + row["vr"]),
            "sin_voto_1rv":    es_void,   # True → no hubo votación real en 1rv
        }
    print(f"Prior 1ra vuelta: {len(prior)} unidades  ({len(sin_voto)} sin votacion en 1rv: {sorted(p for _,p in sin_voto)})")
    return prior


# ── 2. Cargar SQLite ──────────────────────────────────────────────────────────
def cargar_sv():
    if not os.path.exists(DB_PATH):
        print(f"No existe {DB_PATH}. Ejecuta segunda_vuelta_proyeccion.py primero.")
        return pd.DataFrame(), pd.DataFrame()

    conn = sqlite3.connect(DB_PATH)
    corridas = pd.read_sql("SELECT * FROM corridas ORDER BY ts", conn)
    if corridas.empty:
        conn.close()
        return corridas, pd.DataFrame()

    resultados = pd.read_sql(f"""
        SELECT r.corrida_id, r.ts, r.departamento, r.provincia,
               r.pct_actas, r.actas_cont, r.total_actas,
               r.candidato, r.votos_validos
        FROM resultados r
        WHERE r.candidato IN ('{KEIKO}', '{ROBERTO}')
        ORDER BY r.corrida_id, r.departamento, r.provincia
    """, conn)
    conn.close()
    print(f"SQLite: {len(corridas)} corridas, {len(resultados)} filas (K+R)")
    return corridas, resultados


# ── 3. Calibración WLS: lean_2rv ~ α + β·lean_1rv  (ponderada por votos) ──────
def calibrar(piv, prior):
    """
    WLS ponderada por sqrt(votos_contados): provincias grandes pesan más pero
    ninguna domina de forma absoluta. Retorna (alpha, beta, r2, n) o None.
    """
    rep = piv[piv["pct_actas"] > 0].copy()
    data = []
    for _, row in rep.iterrows():
        key = (row["departamento"], row["provincia"])
        if key not in prior:
            continue
        total_sv = row[KEIKO] + row[ROBERTO]
        if total_sv < 20:
            continue
        lean_2rv = row[KEIKO] / total_sv
        lean_1rv = prior[key]["lean_kr"]
        # peso = sqrt(votos) → amortigua dominancia de Lima sin ignorarla
        peso = float(np.sqrt(total_sv))
        data.append((lean_1rv, lean_2rv, peso))

    if len(data) < 3:
        return None

    xs = np.array([d[0] for d in data])
    ys = np.array([d[1] for d in data])
    ws = np.array([d[2] for d in data])
    n  = len(xs)
    W  = ws.sum()

    # WLS: minimiza Σ w·(y - α - β·x)²
    xm = (ws * xs).sum() / W
    ym = (ws * ys).sum() / W
    Sxx = (ws * (xs - xm)**2).sum()
    Sxy = (ws * (xs - xm) * (ys - ym)).sum()
    if Sxx == 0:
        return None
    beta  = Sxy / Sxx
    alpha = ym - beta * xm

    y_pred = alpha + beta * xs
    ss_res = (ws * (ys - y_pred)**2).sum()
    ss_tot = (ws * (ys - ym)**2).sum()
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0

    return alpha, beta, r2, n


def aplicar_lean(lean_1rv, calib):
    """Lean calibrado o prior si no hay suficientes datos."""
    if calib is None:
        return lean_1rv
    alpha, beta, r2, n = calib
    return float(np.clip(alpha + beta * lean_1rv, 0.02, 0.98))


# ── 4. Calcular series por corrida ────────────────────────────────────────────
def calcular_series(corridas, resultados, prior):
    series = []

    for _, corrida in corridas.iterrows():
        cid        = int(corrida["id"])
        ts         = pd.to_datetime(corrida["ts"])
        avance_nac = corrida["avance_nac"] or 0.0
        total_nac  = corrida["total_actas_nac"] or 0

        df_c = resultados[resultados["corrida_id"] == cid].copy()
        if df_c.empty:
            continue

        # Pivot por unidad
        piv = df_c.pivot_table(
            index=["departamento","provincia","pct_actas","actas_cont","total_actas"],
            columns="candidato", values="votos_validos", aggfunc="sum"
        ).reset_index()
        piv.columns.name = None
        for c in [KEIKO, ROBERTO]:
            if c not in piv.columns:
                piv[c] = 0
        piv[KEIKO]   = piv[KEIKO].fillna(0)
        piv[ROBERTO] = piv[ROBERTO].fillna(0)
        piv["pct_actas"] = piv["pct_actas"].fillna(0)

        # RAW
        rep  = piv[piv["pct_actas"] > 0]
        unrp = piv[piv["pct_actas"] == 0]
        vk_raw = rep[KEIKO].sum()
        vr_raw = rep[ROBERTO].sum()
        tot_raw = vk_raw + vr_raw
        pct_k_raw = vk_raw/tot_raw*100 if tot_raw > 0 else 0
        pct_r_raw = 100 - pct_k_raw    if tot_raw > 0 else 0

        # avg votos por acta nacional (fallback para unidades sin prior de 1rv)
        vv_rep      = vk_raw + vr_raw
        act_rep     = rep["actas_cont"].fillna(0).sum()
        avg_vv_acta = vv_rep / act_rep if act_rep > 0 else 0

        # Uplift por unidad (para las ya al 100%) y por grupo (departamento / continente).
        # Grupo Perú  = nombre del departamento.
        # Grupo Extran= "EXTRANJERO/<continente>" → usa el continente como grupo.
        def _grupo(dep):
            return dep if not dep.startswith("EXTRANJERO") else dep  # continente completo

        uplift_por_unidad = {}   # key -> uplift propio
        uplift_listas     = {}   # grupo -> [uplifts de unidades 100% en ese grupo]

        for _, row_u in piv[piv["pct_actas"] >= 99.9].iterrows():
            key_u = (row_u["departamento"], row_u["provincia"])
            if key_u not in prior:
                continue
            tot_2rv = row_u[KEIKO] + row_u[ROBERTO]
            tot_1rv = prior[key_u].get("tot_kr_1rv", 0)
            if tot_1rv < 50:
                continue
            u = float(np.clip(tot_2rv / tot_1rv, 1.0, 6.0))
            uplift_por_unidad[key_u] = u
            grupo = _grupo(row_u["departamento"])
            uplift_listas.setdefault(grupo, []).append(u)

        uplift_grupo  = {g: float(np.median(v)) for g, v in uplift_listas.items()}
        uplift_global = float(np.median(list(uplift_por_unidad.values()))) \
                        if uplift_por_unidad else 1.0

        # Calibración WLS
        calib = calibrar(piv, prior)

        # Estimación para votos aún no contados:
        #   - 0%  → K+R_1rv × uplift_grupo (mismo dep o continente); fallback global
        #   - >0% y <100% → escalar desde el ritmo propio de la unidad en 2rv
        pendientes = []
        vk_est = vr_est = 0.0

        for _, row in piv.iterrows():
            pct   = row["pct_actas"] or 0
            total = row["total_actas"] or 0
            cont  = row["actas_cont"]  or 0
            actas_pend = max(0, total - cont)
            if actas_pend == 0:
                continue

            key      = (row["departamento"], row["provincia"])
            lean_1rv = prior[key]["lean_kr"] if key in prior else 0.5
            lean_est = aplicar_lean(lean_1rv, calib)

            # Unidades sin votación real en 1rv (Venezuela, Kuwait, etc.) → proyectar 0
            if key in prior and prior[key].get("sin_voto_1rv", False):
                est = 0.0
                upl = None
                pendientes.append({
                    "departamento": row["departamento"],
                    "provincia":    row["provincia"],
                    "actas_pend":   actas_pend,
                    "est":          0.0,
                    "est_k":        0.0,
                    "est_r":        0.0,
                    "lean_1rv":     lean_1rv,
                    "lean_cal":     lean_est,
                })
                continue

            if pct == 0:
                # Sin datos: usar K+R_1rv × uplift de su mismo grupo geográfico
                tot_kr_1rv = prior[key].get("tot_kr_1rv", 0) if key in prior else 0
                grupo      = _grupo(row["departamento"])
                upl        = uplift_grupo.get(grupo, uplift_global)
                est = tot_kr_1rv * upl if tot_kr_1rv > 0 else actas_pend * avg_vv_acta
            else:
                # Parcial: escalar desde el ritmo propio de esta unidad en 2rv
                vv_actual = row[KEIKO] + row[ROBERTO]
                est = vv_actual / (pct / 100.0) * (1.0 - pct / 100.0)
                upl = None  # no aplica — usa datos reales

            ek = est * lean_est
            er = est * (1 - lean_est)
            vk_est += ek
            vr_est += er
            pendientes.append({
                "dep_prov":     f"{key[0]} / {key[1]}",
                "departamento": key[0],
                "provincia":    key[1],
                "actas":        actas_pend,
                "pct_actual":   pct,
                "lean_1rv":     lean_1rv,
                "lean_est":     lean_est,
                "est_k":        ek,
                "est_r":        er,
            })

        vk_corr  = vk_raw + vk_est
        vr_corr  = vr_raw + vr_est
        tot_corr = vk_corr + vr_corr
        pct_k_corr = vk_corr/tot_corr*100 if tot_corr > 0 else 0
        pct_r_corr = 100 - pct_k_corr     if tot_corr > 0 else 0

        n_completas  = (piv["pct_actas"] >= 99.9).sum()
        n_parciales  = ((piv["pct_actas"] > 0) & (piv["pct_actas"] < 99.9)).sum()
        n_sin_datos  = (piv["pct_actas"] == 0).sum()

        # Avance Perú vs Extranjero
        is_ext  = piv["departamento"].str.startswith("EXTRANJERO")
        piv_pe  = piv[~is_ext]
        piv_ext = piv[is_ext]

        def _avance_seg(seg):
            total = seg["total_actas"].fillna(0).sum()
            cont  = seg["actas_cont"].fillna(0).sum()
            n_r   = int(((seg["pct_actas"] > 0)).sum())
            n_u   = int(((seg["pct_actas"] == 0)).sum())
            pct   = cont / total * 100 if total > 0 else 0.0
            return {"pct": pct, "n_rep": n_r, "n_unrp": n_u,
                    "total_actas": int(total), "actas_cont": int(cont)}

        av_peru = _avance_seg(piv_pe)
        av_ext  = _avance_seg(piv_ext)

        series.append({
            "ts":           ts,
            "avance_nac":   avance_nac,
            "n_rep":        int(n_completas + n_parciales),
            "n_unrp":       int(n_sin_datos),
            "n_parciales":  int(n_parciales),
            "av_peru":      av_peru,
            "av_ext":       av_ext,
            "vk_raw":       vk_raw,   "vr_raw":   vr_raw,
            "vk_est":       vk_est,   "vr_est":   vr_est,
            "vk_corr":      vk_corr,  "vr_corr":  vr_corr,
            "pct_k_raw":    pct_k_raw, "pct_r_raw": pct_r_raw,
            "pct_k_corr":   pct_k_corr,"pct_r_corr":pct_r_corr,
            "correc_k_pts": pct_k_corr - pct_k_raw,
            "calib":         calib,
            "uplift_global": uplift_global,
            "uplift_grupo":  uplift_grupo,
            "n_uplift":      len(uplift_por_unidad),
            "avg_vv_acta":   avg_vv_acta,
            "pendientes":   pd.DataFrame(pendientes),
            "rep_piv":      rep,
        })

    return series


# ── 5. Componentes visuales didácticos ───────────────────────────────────────

def _marcador(ax_k, ax_r, ultima):
    """Marcador estilo TV: card Keiko | card Roberto con real vs proyectado."""
    u = ultima
    datos = [
        (ax_k, "KEIKO FUJIMORI",     "Fuerza Popular",      C_K, "#FFF0F0",
         u["pct_k_raw"], u["pct_k_corr"], u["pct_k_corr"] - u["pct_k_raw"]),
        (ax_r, "ROBERTO SÁNCHEZ",    "Juntos por el Perú",  C_R, "#EEF4FF",
         u["pct_r_raw"], u["pct_r_corr"], u["pct_r_corr"] - u["pct_r_raw"]),
    ]
    for ax, nombre, partido, col, bg, pct_r, pct_c, delta in datos:
        ax.set_facecolor(bg)
        for sp in ax.spines.values():
            sp.set_edgecolor(col); sp.set_linewidth(2.5)
        ax.set_xticks([]); ax.set_yticks([])

        # Nombre + partido
        ax.text(0.5, 0.96, nombre, transform=ax.transAxes,
                ha="center", va="top", fontsize=12, fontweight="bold", color=col)
        ax.text(0.5, 0.83, partido, transform=ax.transAxes,
                ha="center", va="top", fontsize=8, color="#888")

        # Línea divisoria horizontal
        ax.plot([0.05, 0.95], [0.77, 0.77], transform=ax.transAxes,
                color=col, lw=0.8, alpha=0.35, clip_on=False)

        # — Columna izquierda: REAL ——
        ax.text(0.22, 0.72, "VOTOS REALES\nCONTADOS", transform=ax.transAxes,
                ha="center", va="top", fontsize=7, color="#777", fontweight="bold",
                linespacing=1.3)
        ax.text(0.22, 0.47, f"{pct_r:.3f}%", transform=ax.transAxes,
                ha="center", va="center", fontsize=18, fontweight="bold", color="#333")
        ax.text(0.22, 0.20, "de lo contado\nhasta ahora", transform=ax.transAxes,
                ha="center", va="center", fontsize=7, color="#aaa", linespacing=1.3)

        # — Línea divisoria vertical ——
        ax.plot([0.50, 0.50], [0.12, 0.76], transform=ax.transAxes,
                color=col, lw=0.8, alpha=0.35, clip_on=False)

        # — Centro: flecha de ajuste ——
        arrow_col = "#1a9e50" if delta >= 0 else "#cc2200"
        arrow_sym = "▲" if delta >= 0 else "▼"
        ax.text(0.50, 0.54, f"{arrow_sym}", transform=ax.transAxes,
                ha="center", va="center", fontsize=13, color=arrow_col, fontweight="bold")
        ax.text(0.50, 0.38, f"{abs(delta):.2f}\npts", transform=ax.transAxes,
                ha="center", va="center", fontsize=8.5, color=arrow_col, fontweight="bold",
                linespacing=1.1)
        ax.text(0.50, 0.20, "ajuste", transform=ax.transAxes,
                ha="center", va="center", fontsize=7, color="#bbb")

        # — Columna derecha: PROYECTADO ——
        ax.text(0.78, 0.72, "PROYECCIÓN\nAL 100%", transform=ax.transAxes,
                ha="center", va="top", fontsize=7, color=col, fontweight="bold",
                linespacing=1.3)
        ax.text(0.78, 0.47, f"{pct_c:.3f}%", transform=ax.transAxes,
                ha="center", va="center", fontsize=18, fontweight="bold", color=col)
        estado = "GANARÍA  ✓" if pct_c > 50 else "PERDERÍA"
        ecol   = "#1a9e50" if pct_c > 50 else "#cc2200"
        ax.text(0.78, 0.20, estado, transform=ax.transAxes,
                ha="center", va="center", fontsize=8, color=ecol, fontweight="bold")


def _barra_avance(ax, ultima):
    """3 barras de progreso: Total | Perú | Extranjero."""
    av     = ultima["avance_nac"]
    n_rep  = ultima["n_rep"]
    n_unrp = ultima["n_unrp"]
    ts_str = ultima["ts"].strftime("%H:%M")
    av_pe  = ultima["av_peru"]
    av_ex  = ultima["av_ext"]

    C_PE  = C_AV          # gris pizarra — Perú
    C_EXT = "#78909C"     # gris azulado — Extranjero
    C_TOT = "#37474F"     # gris oscuro  — Total

    filas   = [2, 1, 0]   # y positions: Total arriba, Perú medio, Extranjero abajo
    alturas = [0.55, 0.55, 0.55]

    datos = [
        (av,            n_rep,          n_unrp,          C_TOT, "TOTAL",       "provincias/países"),
        (av_pe["pct"],  av_pe["n_rep"], av_pe["n_unrp"], C_PE,  "PERÚ",        "regiones/provincias"),
        (av_ex["pct"],  av_ex["n_rep"], av_ex["n_unrp"], C_EXT, "EXTRANJERO",  "continentes/países"),
    ]

    ax.set_xlim(0, 116)
    ax.set_ylim(-0.5, 2.7)
    ax.axis("off")

    for y, h, (pct, nr, nu, col, etiq, unidad) in zip(filas, alturas, datos):
        pend = 100 - pct
        ax.barh([y], [pct],  color=col,     height=h, alpha=0.88)
        ax.barh([y], [pend], left=[pct],    color="#DDDDDD", height=h, alpha=0.65)

        # Etiqueta izquierda (contado)
        lbl = f"{etiq}  {pct:.3f}%  ({nr} {unidad})"
        if pct >= 18:
            ax.text(pct / 2, y, lbl,
                    ha="center", va="center", fontsize=8.5, fontweight="bold", color="white")
        else:
            ax.text(pct + 0.8, y + 0.18, lbl,
                    ha="left", va="center", fontsize=8, fontweight="bold", color=col)

        # Etiqueta derecha (pendiente) — solo si hay algo pendiente
        if pend > 0.01:
            lbl_p = f"pendiente {pend:.3f}%  ({nu} {unidad})"
            ax.text(pct + pend / 2, y, lbl_p,
                    ha="center", va="center", fontsize=7.5, color="#555")

    ax.text(103, 1, f"Actualiz.\n{ts_str}",
            ha="left", va="center", fontsize=7.5, color="#999", linespacing=1.3)


def _caja_explicacion(ax, ultima):
    """Caja inferior con explicación en lenguaje simple del ajuste."""
    u     = ultima
    pend  = u["pendientes"]
    calib = u["calib"]

    lean_med = (pend["lean_est"] * pend["actas"]).sum() / pend["actas"].sum() \
               if not pend.empty and pend["actas"].sum() > 0 else 0.5

    upl         = u.get("uplift_global", 1.0)
    correc      = u["correc_k_pts"]
    quien_gana  = "Roberto" if correc < 0 else "Keiko"
    quien_pierde = "Keiko" if correc < 0 else "Roberto"

    if calib:
        a, b, r2, n_cal = calib
        linea_calib = (
            f"  • Calibración: ajustamos el lean con los resultados reales de las {n_cal} provincias que ya "
            f"reportaron (R²={r2:.2f}).  Fórmula:  lean_proyectado = {a:.3f} + {b:.3f} × lean_1ra_vuelta"
        )
    else:
        linea_calib = (
            f"  • Calibración: aún no hay suficientes provincias para calibrar. "
            f"Usando lean puro de 1ra vuelta (K/(K+R) por provincia)."
        )

    texto = (
        f"¿POR QUÉ LA PROYECCIÓN DIFIERE DE LOS VOTOS REALES?\n\n"
        f"  • Solo {u['n_rep']} de 273 provincias han enviado actas. "
        f"Las primeras en llegar son las más cercanas a los centros de cómputo de la ONPE, no representan al país completo.\n"
        f"  • Las {u['n_unrp']} provincias que FALTAN tienen en promedio {lean_med*100:.3f}% de voto a Keiko "
        f"según el patrón calibrado — eso significa que {quien_gana} recibe la mayoría de los votos pendientes.\n"
        f"  • Estimamos votos pendientes: para unidades sin dato usamos votos_1rv × {upl:.2f} (uplift 2rv/1rv); "
        f"para parciales escalamos desde su propio ritmo actual × lean_proyectado\n"
        f"{linea_calib}\n"
        f"  • Efecto neto del ajuste: {quien_pierde} baja {abs(correc):.3f} pts · {quien_gana} sube {abs(correc):.3f} pts  "
        f"(corrección de sesgo de llegada temprana)"
    )
    ax.text(0.5, 0.5, texto, transform=ax.transAxes,
            ha="center", va="center", fontsize=8.2, linespacing=1.65,
            bbox=dict(boxstyle="round,pad=0.6", fc="#F7F7F7", ec="#BBBBBB", lw=1.5),
            fontfamily="monospace")
    ax.axis("off")


# ── DEPRECATED (kept as stub so code below doesn't break) ────────────────────
def _panel_estado(fig, ultima):
    """
    Banda superior fija en la figura con:
      avance | votos reales | proyección | por qué difieren
    """
    u      = ultima
    pk_raw = u["pct_k_raw"]
    pr_raw = u["pct_r_raw"]
    pk_cor = u["pct_k_corr"]
    pr_cor = u["pct_r_corr"]
    av     = u["avance_nac"]
    n_rep  = u["n_rep"]
    n_unrp = u["n_unrp"]
    calib  = u["calib"]

    lider_raw  = "KEIKO" if pk_raw > pr_raw else "ROBERTO"
    lider_cor  = "KEIKO" if pk_cor > pr_cor else "ROBERTO"
    col_raw    = C_K if pk_raw > pr_raw else C_R
    col_cor    = C_K if pk_cor > pr_cor else C_R

    # ── Línea 1: avance + votos reales ────────────────────────────────────────
    linea1 = (
        f"AVANCE: {av:.2f}%   |   "
        f"Provincias: {n_rep} reportadas  /  {n_unrp} pendientes   |   "
        f"VOTOS REALES CONTADOS:  Keiko {pk_raw:.2f}%  —  Roberto {pr_raw:.2f}%  "
        f"({'Keiko gana' if pk_raw>pr_raw else 'Roberto gana'} en lo contado)"
    )

    # ── Línea 2: proyección ───────────────────────────────────────────────────
    linea2 = (
        f"PROYECCION AL 100%:  Keiko {pk_cor:.2f}%  —  Roberto {pr_cor:.2f}%   "
        f"({'Keiko ganaría' if pk_cor>pr_cor else 'Roberto ganaría'}  "
        f"por {abs(pk_cor-pr_cor):.2f} pts si el patrón se mantiene)"
    )

    # ── Línea 3: explicación simple ───────────────────────────────────────────
    if calib:
        a, b, r2, n_cal = calib
        pend = u["pendientes"]
        lean_med = (pend["lean_est"]*pend["actas"]).sum() / pend["actas"].sum() \
                   if not pend.empty and pend["actas"].sum() > 0 else 0.5
        corr_dir = "sube" if u["correc_k_pts"] >= 0 else "baja"
        quien    = "Keiko" if u["correc_k_pts"] >= 0 else "Roberto"
        linea3 = (
            f"POR QUE DIFIERE:  Las {n_unrp} provincias pendientes tienen en promedio "
            f"{lean_med*100:.1f}% a favor de Keiko segun la 1ra vuelta (ajustado). "
            f"Estimamos sus votos = actas × votos/acta × lean. "
            f"Eso {corr_dir} a {quien} {abs(u['correc_k_pts']):.2f} pts vs el conteo parcial. "
            f"Calibracion sobre {n_cal} prov. con datos: R²={r2:.2f}"
        )
    else:
        pend = u["pendientes"]
        lean_med = (pend["lean_1rv"]*pend["actas"]).sum() / pend["actas"].sum() \
                   if not pend.empty and pend["actas"].sum() > 0 else 0.5
        linea3 = (
            f"POR QUE DIFIERE:  Las {n_unrp} provincias pendientes tienen en promedio "
            f"{lean_med*100:.1f}% a favor de Keiko segun la 1ra vuelta (lean puro, sin calibrar aun). "
            f"Estimamos sus votos = actas pendientes × votos/acta × lean."
        )

    # Pintar las tres líneas con colores
    fig.text(0.5, 0.985, linea1, ha="center", va="top", fontsize=9,
             color=col_raw, fontweight="bold",
             bbox=dict(boxstyle="round,pad=0.3", fc="#FFF8F8" if col_raw==C_K else "#F0F4FF",
                       ec=col_raw, alpha=0.9, lw=1.5))
    fig.text(0.5, 0.960, linea2, ha="center", va="top", fontsize=9,
             color=col_cor, fontweight="bold",
             bbox=dict(boxstyle="round,pad=0.3", fc="#FFF8F8" if col_cor==C_K else "#F0F4FF",
                       ec=col_cor, alpha=0.9, lw=1.5))
    fig.text(0.5, 0.933, linea3, ha="center", va="top", fontsize=7.8,
             color="#444",
             bbox=dict(boxstyle="round,pad=0.3", fc="#F5F5F5", ec="#CCCCCC", alpha=0.9))


# ── 6. GRÁFICO 1: Curvas electorales ─────────────────────────────────────────
def _curvas(series, ax_curvas, ax_avance):
    df = pd.DataFrame([{k: v for k, v in s.items()
                        if k not in ("calib","pendientes","rep_piv")} for s in series])
    ultima = series[-1]
    ts     = df["ts"]

    # Fondo ganador
    if len(df) > 1:
        ax_curvas.fill_between(ts, df["pct_k_corr"], df["pct_r_corr"],
                               where=df["pct_k_corr"] >= df["pct_r_corr"],
                               alpha=0.07, color=C_K)
        ax_curvas.fill_between(ts, df["pct_k_corr"], df["pct_r_corr"],
                               where=df["pct_k_corr"] < df["pct_r_corr"],
                               alpha=0.07, color=C_R)

    ax_curvas.axhline(50, color="#888", lw=0.9, ls=":", zorder=1)
    ax_curvas.text(ts.iloc[0], 50.4, "50% — umbral de victoria",
                   fontsize=7.5, color="#999", va="bottom")

    # RAW punteado
    ax_curvas.plot(ts, df["pct_k_raw"], color=C_K, lw=1.3, ls="--", alpha=0.45, zorder=2)
    ax_curvas.plot(ts, df["pct_r_raw"], color=C_R, lw=1.3, ls="--", alpha=0.45, zorder=2)

    # Corregido sólido grueso
    ax_curvas.plot(ts, df["pct_k_corr"], color=C_K, lw=2.8, marker="o", ms=6, zorder=3)
    ax_curvas.plot(ts, df["pct_r_corr"], color=C_R, lw=2.8, marker="o", ms=6, zorder=3)

    # Anotación del último punto real y proyectado
    t_last = ts.iloc[-1]
    rng    = ts.max() - ts.min()
    t_proj = t_last + (pd.Timedelta(minutes=55) if rng.total_seconds() < 120 else rng * 0.30)
    pk, pr = ultima["pct_k_corr"], ultima["pct_r_corr"]

    ax_curvas.plot([t_last, t_proj], [pk, pk], color=C_K, lw=1.4, ls=":", alpha=0.65)
    ax_curvas.plot([t_last, t_proj], [pr, pr], color=C_R, lw=1.4, ls=":", alpha=0.65)
    ax_curvas.scatter([t_proj], [pk], color=C_K, s=100, marker="D", zorder=5)
    ax_curvas.scatter([t_proj], [pr], color=C_R, s=100, marker="D", zorder=5)

    ax_curvas.annotate(f"proy. {pk:.3f}%", xy=(t_proj, pk),
                       xytext=(9, 0), textcoords="offset points",
                       fontsize=10.5, fontweight="bold", color=C_K, va="center")
    ax_curvas.annotate(f"proy. {pr:.3f}%", xy=(t_proj, pr),
                       xytext=(9, 0), textcoords="offset points",
                       fontsize=10.5, fontweight="bold", color=C_R, va="center")

    # Etiquetas real en último punto
    pk_r = df["pct_k_raw"].iloc[-1]
    pr_r = df["pct_r_raw"].iloc[-1]
    ax_curvas.annotate(f"real {pk_r:.3f}%", xy=(t_last, pk_r),
                       xytext=(-50, 10), textcoords="offset points",
                       fontsize=8, color=C_K, alpha=0.7,
                       arrowprops=dict(arrowstyle="-", color=C_K, alpha=0.25, lw=0.8))
    ax_curvas.annotate(f"real {pr_r:.3f}%", xy=(t_last, pr_r),
                       xytext=(-50, -13), textcoords="offset points",
                       fontsize=8, color=C_R, alpha=0.7,
                       arrowprops=dict(arrowstyle="-", color=C_R, alpha=0.25, lw=0.8))

    # Leyenda
    leyenda = [
        Line2D([0],[0], color=C_K, lw=2.8, marker="o", ms=6,
               label="Keiko — proyección corregida"),
        Line2D([0],[0], color=C_R, lw=2.8, marker="o", ms=6,
               label="Roberto — proyección corregida"),
        Line2D([0],[0], color="#aaa", lw=1.3, ls="--",
               label="punteado = votos reales contados (sin corrección)"),
        Line2D([0],[0], color="#aaa", lw=1.4, ls=":", marker="D", ms=6,
               markerfacecolor="#aaa", label="◆ = resultado proyectado al 100%"),
    ]
    ax_curvas.legend(handles=leyenda, loc="upper left", fontsize=8.5,
                     framealpha=0.93, edgecolor="#ccc")

    all_v = pd.concat([df["pct_k_corr"], df["pct_r_corr"],
                       df["pct_k_raw"],  df["pct_r_raw"]])
    pad = max(3.5, (all_v.max() - all_v.min()) * 0.28)
    ax_curvas.set_ylim(max(0, all_v.min()-pad), min(100, all_v.max()+pad))
    ax_curvas.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.3f%%"))
    ax_curvas.set_ylabel("% votos válidos", fontsize=10)
    ax_curvas.set_title("Evolución corrida a corrida  (línea sólida = proyección corregida · punteada = conteo real)",
                        fontsize=10, fontweight="bold", pad=7)
    ax_curvas.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax_curvas.xaxis.set_major_locator(mdates.AutoDateLocator())
    plt.setp(ax_curvas.xaxis.get_majorticklabels(), rotation=30, ha="right")
    for sp in ["top","right"]:
        ax_curvas.spines[sp].set_visible(False)

    # Sub-panel avance nacional en el tiempo
    av = ultima["avance_nac"]
    ax_avance.fill_between(ts, df["avance_nac"], alpha=0.28, color=C_AV)
    ax_avance.plot(ts, df["avance_nac"], color=C_AV, lw=2.2, marker="o", ms=5)
    ax_avance.set_ylim(0, 102)
    ax_avance.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.3f%%"))
    ax_avance.set_ylabel("% actas\ncontadas", fontsize=8.5)
    ax_avance.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax_avance.xaxis.set_major_locator(mdates.AutoDateLocator())
    plt.setp(ax_avance.xaxis.get_majorticklabels(), rotation=30, ha="right")
    ax_avance.set_xlabel("Hora de extracción", fontsize=9)
    ax_avance.set_title("Avance del cómputo nacional", fontsize=9, pad=4)
    ax_avance.annotate(f"{av:.3f}%", xy=(ts.iloc[-1], av),
                       xytext=(0, 9), textcoords="offset points",
                       fontsize=10, fontweight="bold", color=C_AV, ha="center")
    for sp in ["top","right"]:
        ax_avance.spines[sp].set_visible(False)


# ── 7. GRÁFICO adicional: curvas por % avance ────────────────────────────────
def _curvas_por_avance(series, ax):
    """Curvas % candidato vs % avance nacional (X = avance, no tiempo)."""
    df = pd.DataFrame([{k: v for k, v in s.items()
                        if k not in ("calib","pendientes","rep_piv")} for s in series])
    df = df[df["avance_nac"] > 0].copy()
    ultima = series[-1]

    av  = df["avance_nac"]
    pk  = ultima["pct_k_corr"]
    pr  = ultima["pct_r_corr"]

    # Fondo ganador
    if len(df) > 1:
        ax.fill_between(av, df["pct_k_corr"], df["pct_r_corr"],
                        where=df["pct_k_corr"] >= df["pct_r_corr"],
                        alpha=0.07, color=C_K)
        ax.fill_between(av, df["pct_k_corr"], df["pct_r_corr"],
                        where=df["pct_k_corr"] < df["pct_r_corr"],
                        alpha=0.07, color=C_R)

    ax.axhline(50, color="#888", lw=0.9, ls=":", zorder=1)
    ax.text(df["avance_nac"].min() + 0.5, 50.25, "50% — umbral de victoria",
            fontsize=7, color="#999", va="bottom")

    # RAW punteado
    ax.plot(av, df["pct_k_raw"], color=C_K, lw=1.1, ls="--", alpha=0.4, zorder=2)
    ax.plot(av, df["pct_r_raw"], color=C_R, lw=1.1, ls="--", alpha=0.4, zorder=2)

    # Corregido sólido
    ax.plot(av, df["pct_k_corr"], color=C_K, lw=2.5, marker="o", ms=5, zorder=3)
    ax.plot(av, df["pct_r_corr"], color=C_R, lw=2.5, marker="o", ms=5, zorder=3)

    # Punto final con etiqueta
    av_last = av.iloc[-1]
    ax.scatter([av_last], [pk], color=C_K, s=90, marker="D", zorder=5)
    ax.scatter([av_last], [pr], color=C_R, s=90, marker="D", zorder=5)
    ax.annotate(f"{pk:.3f}%", xy=(av_last, pk),
                xytext=(5, 2), textcoords="offset points",
                fontsize=8.5, fontweight="bold", color=C_K, va="bottom")
    ax.annotate(f"{pr:.3f}%", xy=(av_last, pr),
                xytext=(5, -10), textcoords="offset points",
                fontsize=8.5, fontweight="bold", color=C_R, va="top")

    all_v = pd.concat([df["pct_k_corr"], df["pct_r_corr"],
                       df["pct_k_raw"],  df["pct_r_raw"]])
    pad = max(3.0, (all_v.max() - all_v.min()) * 0.30)
    ax.set_ylim(max(0, all_v.min()-pad), min(100, all_v.max()+pad))
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.3f%%"))
    ax.xaxis.set_major_formatter(mticker.FormatStrFormatter("%.1f%%"))
    ax.set_xlabel("Avance del cómputo nacional (%)", fontsize=9)
    ax.set_ylabel("% votos válidos", fontsize=9)
    ax.set_title("Evolución por avance\n(eje X = % actas contadas)", fontsize=9,
                 fontweight="bold", pad=6)
    for sp in ["top","right"]:
        ax.spines[sp].set_visible(False)


# ── 8. GRÁFICO 2: Desglose ───────────────────────────────────────────────────
def _desglose(series, ax_barras, ax_pendientes):
    ultima = series[-1]
    vk_r, vr_r = ultima["vk_raw"],  ultima["vr_raw"]
    vk_e, vr_e = ultima["vk_est"],  ultima["vr_est"]
    vk_t, vr_t = ultima["vk_corr"], ultima["vr_corr"]
    tot_r = vk_r + vr_r
    tot_t = vk_t + vr_t

    # ── Barras apiladas (reales + estimados) ──────────────────────────────────
    y = [1, 0]
    ax_barras.barh(y, [vk_r, vr_r], color=[C_K,  C_R],  height=0.52,
                   label="Votos reales ya contados")
    ax_barras.barh(y, [vk_e, vr_e], left=[vk_r, vr_r],
                   color=[C_KL, C_RL], height=0.52,
                   label="Estimados para provincias que faltan")

    ax_barras.set_yticks(y)
    ax_barras.set_yticklabels(
        [f"KEIKO\nreal {vk_r/tot_r*100:.3f}%  →  proyectado {vk_t/tot_t*100:.3f}%",
         f"ROBERTO\nreal {vr_r/tot_r*100:.3f}%  →  proyectado {vr_t/tot_t*100:.3f}%"],
        fontsize=9, fontweight="bold"
    )
    ax_barras.xaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f"{x/1e6:.2f}M" if x >= 1e6 else f"{int(x/1e3)}k")
    )
    for i, (vr, ve, col) in enumerate([(vk_r, vk_e, "white"), (vr_r, vr_e, "white")]):
        if vr > 300:
            ax_barras.text(vr/2, y[i], f"{vr:,.0f}\ncontados",
                          ha="center", va="center", fontsize=7.5,
                          color=col, fontweight="bold")
        if ve > 300:
            ax_barras.text(vr+ve/2, y[i], f"~{ve:,.0f}\nestimados",
                          ha="center", va="center", fontsize=7.5,
                          color="#222", fontweight="bold")

    ax_barras.legend(fontsize=8.5, loc="lower right", framealpha=0.92)
    ax_barras.set_xlabel("Votos válidos", fontsize=9)
    ax_barras.set_title(
        f"Votos reales vs estimados — total proyectado: {tot_t:,.0f}",
        fontsize=10, fontweight="bold"
    )
    for sp in ["top","right"]:
        ax_barras.spines[sp].set_visible(False)

    # ── Panel provincias pendientes ───────────────────────────────────────────
    pend = ultima["pendientes"]
    if pend.empty:
        ax_pendientes.text(0.5, 0.5, "Todas las provincias ya reportaron ✓",
                           ha="center", va="center", transform=ax_pendientes.transAxes,
                           fontsize=12, color="#1a9e50", fontweight="bold")
        ax_pendientes.axis("off")
        return

    top    = pend.nlargest(20, "actas").sort_values("lean_est")
    colors = [C_K if x >= 0.5 else C_R for x in top["lean_est"]]

    bars = ax_pendientes.barh(range(len(top)), top["lean_est"]*100 - 50, left=50,
                              color=colors, alpha=0.83, height=0.76)
    ax_pendientes.axvline(50, color="#333", lw=1.2, ls="--", alpha=0.6)
    ax_pendientes.text(50.4, len(top)-0.5, "50%", fontsize=7.5, color="#555")

    ax_pendientes.set_yticks(range(len(top)))
    ax_pendientes.set_yticklabels(
        [f"{r['departamento'][:10]}/{r['provincia'][:12]}  ({int(r['actas']):,})"
         for _, r in top.iterrows()],
        fontsize=7
    )
    ax_pendientes.set_xlim(12, 92)
    ax_pendientes.xaxis.set_major_formatter(mticker.FormatStrFormatter("%.0f%%"))
    ax_pendientes.set_xlabel("% Keiko proyectado  (rojo→Keiko · azul→Roberto)", fontsize=9)

    lean_med = (pend["lean_est"]*pend["actas"]).sum() / pend["actas"].sum()
    correc   = ultima["correc_k_pts"]
    efecto   = f"{'sube' if correc>=0 else 'baja'} Keiko {abs(correc):.3f} pts"
    ax_pendientes.set_title(
        f"Top 20 provincias pendientes por volumen de actas\n"
        f"Lean medio ponderado: {lean_med*100:.3f}% Keiko  |  Efecto neto del ajuste: {efecto}",
        fontsize=9, fontweight="bold"
    )
    for sp in ["top","right"]:
        ax_pendientes.spines[sp].set_visible(False)


# ── 8. Figura 3: top-20 unidades por ganancia neta ───────────────────────────
def graficar_detalle(series, ts_file):
    """sv_detalle_*.png — top 20 unidades por votos proyectados adicionales (oportunidad)."""
    if not series:
        return
    ultima = series[-1]
    av     = ultima["avance_nac"]
    ts     = ultima["ts"]

    # ── Construir tabla: (dep, prov) → real_k, real_r, proj_k, proj_r ────────
    def _label(dep, prov):
        if dep.startswith("EXTRANJERO"):
            return prov
        return f"{dep[:16]} / {prov[:18]}"

    units = {}

    for _, row in ultima["rep_piv"].iterrows():
        dep, prov = row["departamento"], row["provincia"]
        units[(dep, prov)] = {
            "dep":      dep,
            "prov":     prov,
            "label":    _label(dep, prov),
            "pct_avance": float(row.get("pct_actas", 0)),
            "real_k":   float(row[KEIKO]),
            "real_r":   float(row[ROBERTO]),
            "proj_k":   0.0, "proj_r": 0.0,
        }

    for _, row in ultima["pendientes"].iterrows():
        dep, prov = row["departamento"], row["provincia"]
        key = (dep, prov)
        if key not in units:
            units[key] = {"dep": dep, "prov": prov,
                          "label": _label(dep, prov),
                          "pct_avance": 0.0,
                          "real_k": 0.0, "real_r": 0.0,
                          "proj_k": 0.0, "proj_r": 0.0}
        units[key]["proj_k"] += float(row["est_k"])
        units[key]["proj_r"] += float(row["est_r"])

    df_u = pd.DataFrame([{
        "departamento":   v["dep"],
        "provincia":      v["prov"],
        "label":          v["label"],
        "pct_avance":     round(v["pct_avance"], 3),
        "real_k":         int(v["real_k"]),   "real_r":  int(v["real_r"]),
        "ganancia_k":     int(v["proj_k"]),   "ganancia_r": int(v["proj_r"]),
        "proyectado_k":   int(v["real_k"] + v["proj_k"]),
        "proyectado_r":   int(v["real_r"] + v["proj_r"]),
    } for v in units.values()])

    # ── Exportar CSVs por candidato ──────────────────────────────────────────
    cols_base = ["departamento", "provincia", "pct_avance"]
    for cand, c_real, c_gan, c_proy in [
        ("keiko",   "real_k",   "ganancia_k",   "proyectado_k"),
        ("roberto", "real_r",   "ganancia_r",   "proyectado_r"),
    ]:
        df_csv = df_u[cols_base + [c_real, c_gan, c_proy]].copy()
        df_csv.columns = ["departamento", "provincia", "pct_avance",
                          "votos_reales", "ganancia", "votos_proyectados"]
        df_csv = df_csv.sort_values("ganancia", ascending=False).reset_index(drop=True)
        fname_csv = f"sv_unidades_{cand}_{ts_file}.csv"
        df_csv.to_csv(fname_csv, index=False, encoding="utf-8-sig")
        print(f"CSV guardado: {fname_csv}")

    TOP_N = 20
    # top por votos proyectados adicionales (la "oportunidad" de cada candidato)
    top_k = df_u[df_u["ganancia_k"] > 0].nlargest(TOP_N, "ganancia_k").iloc[::-1].reset_index(drop=True)
    top_r = df_u[df_u["ganancia_r"] > 0].nlargest(TOP_N, "ganancia_r").iloc[::-1].reset_index(drop=True)

    # ── Layout: 2 paneles verticales ─────────────────────────────────────────
    fig3 = plt.figure(figsize=(16, 23), facecolor="#FAFAFA")
    fig3.suptitle(
        f"ONPE 2026 — Segunda Vuelta | Top 20 unidades por votos proyectados adicionales\n"
        f"Avance {av:.3f}%  —  {ts.strftime('%Y-%m-%d %H:%M')}",
        fontsize=12, fontweight="bold", y=0.997, color="#222",
    )
    gs3 = fig3.add_gridspec(2, 1, hspace=0.20)
    ax_k = fig3.add_subplot(gs3[0])
    ax_r = fig3.add_subplot(gs3[1])

    def _panel(ax, top, c_real, c_proj, c_win, titulo):
        """Una barra por unidad: longitud = votos adicionales proyectados (ganancia).
        Texto a la derecha: real | +ganancia | proy (= real + ganancia)."""
        labels = top["label"].tolist()
        is_k   = c_win == C_K
        real_w = top["real_k" if is_k else "real_r"].values.astype(float)
        proj_w = top["ganancia_k" if is_k else "ganancia_r"].values.astype(float)
        total_w = real_w + proj_w

        ypos  = np.arange(len(labels))
        max_p = proj_w.max() if proj_w.max() > 0 else 1

        # Barra = votos proyectados adicionales (la ganancia/oportunidad)
        ax.barh(ypos, proj_w, height=0.62, color=c_proj, alpha=0.85,
                label="Votos proyectados adicionales (actas pendientes)")

        for i, (rw, pw, tw) in enumerate(zip(real_w, proj_w, total_w)):
            # Valor dentro de la barra si cabe
            if pw > max_p * 0.07:
                ax.text(pw / 2, i, f"+{pw:,.0f}",
                        ha="center", va="center", fontsize=7.5,
                        color="white", fontweight="bold")
            # Tres cifras a la derecha: real | +ganancia | proy
            ax.text(pw + max_p * 0.025, i,
                    f"real {rw:,.0f}   +{pw:,.0f}   proy {tw:,.0f}",
                    ha="left", va="center", fontsize=8.5, color="#222")

        ax.set_yticks(ypos)
        ax.set_yticklabels(labels, fontsize=9)
        ax.set_xlim(0, max_p * 2.1)
        ax.set_ylim(-0.6, len(labels) - 0.4)
        ax.set_xlabel("Votos proyectados adicionales (actas pendientes)   |   cifras: real  +ganancia  proy", fontsize=8.5)
        ax.set_title(titulo, fontsize=10.5, fontweight="bold", pad=7, color=c_real)
        ax.legend(loc="lower right", fontsize=8.5, framealpha=0.85)
        ax.xaxis.set_major_formatter(
            mticker.FuncFormatter(
                lambda x, _: f"{x/1e6:.1f}M" if x >= 1e6 else f"{x/1e3:.0f}K"))
        ax.grid(axis="x", alpha=0.22, linestyle="--", color="#999")
        for sp in ["top", "right"]:
            ax.spines[sp].set_visible(False)
        ax.text(0.99, 0.01,
                f"Total ganancia top 20: +{proj_w.sum():,.0f} votos",
                transform=ax.transAxes, ha="right", va="bottom", fontsize=8.5,
                color=c_real, fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.3", fc="white", ec=c_proj))

    vk_tot = int(ultima["vk_corr"]); vr_tot = int(ultima["vr_corr"])
    pk = ultima["pct_k_corr"];       pr = ultima["pct_r_corr"]

    _panel(ax_k, top_k, C_K, C_KL, C_K,
           f"KEIKO FUJIMORI — top 20 unidades por votos adicionales proyectados  |  total proyectado {vk_tot:,} votos ({pk:.3f}%)")
    _panel(ax_r, top_r, C_R, C_RL, C_R,
           f"ROBERTO SÁNCHEZ PALOMINO — top 20 unidades por votos adicionales proyectados  |  total proyectado {vr_tot:,} votos ({pr:.3f}%)")

    fig3.patch.set_facecolor("#FAFAFA")
    out3 = f"sv_detalle_{ts_file}.png"
    fig3.savefig(out3, dpi=150, bbox_inches="tight")
    print(f"Grafico 3 guardado: {out3}")


# ── 9. Generar ambos gráficos ─────────────────────────────────────────────────
def graficar(series):
    if not series:
        print("Sin datos para graficar.")
        return

    ts_file = datetime.now().strftime("%Y%m%d_%H%M")
    ultima  = series[-1]

    # ─── FIGURA 1: Curvas ────────────────────────────────────────────────────
    fig1 = plt.figure(figsize=(15, 14), facecolor="#FAFAFA")
    fig1.suptitle("ONPE 2026 — Segunda Vuelta Presidencial",
                  fontsize=15, fontweight="bold", y=0.995)
    # 3 columnas: curvas tiempo (ancha) | curvas avance (media)
    gs1 = fig1.add_gridspec(5, 3,
                             height_ratios=[2.0, 0.75, 3.8, 0.9, 1.3],
                             width_ratios=[2.2, 0.05, 1.4],
                             hspace=0.55, wspace=0.28)

    ax_k1    = fig1.add_subplot(gs1[0, 0])
    ax_r1    = fig1.add_subplot(gs1[0, 2])
    ax_av1   = fig1.add_subplot(gs1[1, :])
    ax_cur   = fig1.add_subplot(gs1[2, 0])
    ax_avpct = fig1.add_subplot(gs1[2:4, 2])  # ← abarca filas 2 y 3
    ax_avc   = fig1.add_subplot(gs1[3, 0])
    ax_why1  = fig1.add_subplot(gs1[4, :])
    fig1.patch.set_facecolor("#FAFAFA")
    for ax in (ax_cur, ax_avc, ax_avpct):
        ax.set_facecolor("#FAFAFA")
    # ocultar columna separadora
    fig1.add_subplot(gs1[2:4, 1]).set_visible(False)

    _marcador(ax_k1, ax_r1, ultima)
    _barra_avance(ax_av1, ultima)
    _curvas(series, ax_cur, ax_avc)
    _curvas_por_avance(series, ax_avpct)
    _caja_explicacion(ax_why1, ultima)

    out1 = f"sv_curvas_{ts_file}.png"
    fig1.savefig(out1, dpi=150, bbox_inches="tight")
    print(f"Grafico 1 guardado: {out1}")

    # ─── FIGURA 2: Desglose ──────────────────────────────────────────────────
    fig2 = plt.figure(figsize=(17, 14), facecolor="#FAFAFA")
    fig2.suptitle("ONPE 2026 — Segunda Vuelta Presidencial",
                  fontsize=15, fontweight="bold", y=0.995)
    gs2 = fig2.add_gridspec(4, 2,
                             height_ratios=[2.0, 0.75, 5.0, 1.3],
                             hspace=0.55, wspace=0.38)

    ax_k2   = fig2.add_subplot(gs2[0, 0])
    ax_r2   = fig2.add_subplot(gs2[0, 1])
    ax_av2  = fig2.add_subplot(gs2[1, :])
    ax_bar  = fig2.add_subplot(gs2[2, 0])
    ax_pend = fig2.add_subplot(gs2[2, 1])
    ax_why2 = fig2.add_subplot(gs2[3, :])
    fig2.patch.set_facecolor("#FAFAFA")
    for ax in (ax_bar, ax_pend):
        ax.set_facecolor("#FAFAFA")

    _marcador(ax_k2, ax_r2, ultima)
    _barra_avance(ax_av2, ultima)
    _desglose(series, ax_bar, ax_pend)
    _caja_explicacion(ax_why2, ultima)

    out2 = f"sv_proyeccion_{ts_file}.png"
    fig2.savefig(out2, dpi=150, bbox_inches="tight")
    print(f"Grafico 2 guardado: {out2}")

    # ─── FIGURA 3: Top-20 unidades por candidato ─────────────────────────────
    graficar_detalle(series, ts_file)

    plt.show()


# ── 8. Resumen consola ────────────────────────────────────────────────────────
def resumen(series, corridas):
    sep = "=" * 72
    if not series:
        print(f"\n{sep}\n  Sin corridas con datos de votos todavía.\n{sep}")
        return

    u = series[-1]
    print(f"\n{sep}")
    print(f"  SEGUNDA VUELTA 2026 — {u['ts'].strftime('%Y-%m-%d %H:%M')}")
    print(f"  Avance: {u['avance_nac']:.3f}%   |   Corridas en DB: {len(corridas)}")
    print(sep)
    print(f"  {'':34} {'RAW':>10} {'CORREGIDO':>12}")
    print(f"  {'-'*58}")
    print(f"  {'Keiko Fujimori':<34} {u['pct_k_raw']:>9.3f}% {u['pct_k_corr']:>11.3f}%")
    print(f"  {'Roberto Sanchez Palomino':<34} {u['pct_r_raw']:>9.3f}% {u['pct_r_corr']:>11.3f}%")
    print(f"  {'-'*58}")
    c = u["correc_k_pts"]
    print(f"  Correccion de sesgo (Keiko): {'+'if c>=0 else ''}{c:.3f} pts")
    print(f"  Unidades: {u['n_rep']} reportadas  /  {u['n_unrp']} pendientes")

    calib = u["calib"]
    if calib:
        a, b, r2, n = calib
        print(f"\n  Calibracion WLS (n={n} provincias, ponderada por sqrt(votos)):")
        print(f"    lean_2rv = {a:.4f} + {b:.4f} x lean_1rv   (R2 = {r2:.3f})")
        print(f"    -> Redistribucion del 'otros': {'favorece a Roberto' if b < 1 else 'amplifica diferencias'}")
    else:
        print(f"\n  Sin calibracion aun (< 3 provincias con votos >= 20)")

    upl_g  = u.get("uplift_global", 1.0)
    n_upl  = u.get("n_uplift", 0)
    grupos = u.get("uplift_grupo", {})
    print(f"  Uplift 2rv/1rv global (n={n_upl} unidades al 100%): {upl_g:.3f}x")
    # Mostrar uplift de grupos con pendientes relevantes
    for dep_pend in ["LIMA", "CUSCO", "EXTRANJERO/AMERICA", "EXTRANJERO/EUROPA", "EXTRANJERO/ASIA"]:
        if dep_pend in grupos:
            print(f"    {dep_pend:<28}: {grupos[dep_pend]:.3f}x")

    if len(series) >= 2:
        p = series[-2]
        dk  = u["pct_k_corr"] - p["pct_k_corr"]
        dr  = u["pct_r_corr"] - p["pct_r_corr"]
        dav = u["avance_nac"] - p["avance_nac"]
        print(f"\n  Delta vs corrida anterior (+{dav:.3f}% actas):")
        print(f"    Keiko  {'arriba' if dk>=0 else 'abajo'} {dk:+.3f} pts    "
              f"Roberto {'arriba' if dr>=0 else 'abajo'} {dr:+.3f} pts")

    # Tendencia de las últimas corridas (voto real)
    n_tend = min(len(series), 5)
    if n_tend >= 3:
        tend_raw = [s["pct_k_raw"] for s in series[-n_tend:]]
        tend_cor = [s["pct_k_corr"] for s in series[-n_tend:]]
        delta_raw = tend_raw[-1] - tend_raw[0]
        delta_cor = tend_cor[-1] - tend_cor[0]
        dir_raw = "v baja" if delta_raw < -0.05 else ("^ sube" if delta_raw > 0.05 else "= estable")
        dir_cor = "v baja" if delta_cor < -0.05 else ("^ sube" if delta_cor > 0.05 else "= estable")
        print(f"\n  Tendencia ultimas {n_tend} corridas (voto real Keiko):")
        print(f"    Conteo real:   {dir_raw}  ({delta_raw:+.3f} pts)")
        print(f"    Proyeccion:    {dir_cor}  ({delta_cor:+.3f} pts)")
        if delta_raw < -0.1 and delta_cor < -0.05:
            print(f"    ALERTA: tendencia sostenida a favor de Roberto — revisar pendientes rurales")

    pend = u["pendientes"]
    if not pend.empty:
        print(f"\n  Top 5 pendientes por actas:")
        print(f"  {'Unidad':<42} {'Actas':>6}  {'lean_1rv':>9}  {'lean_cal':>9}")
        print(f"  {'-'*68}")
        for _, r in pend.nlargest(5, "actas").iterrows():
            print(f"  {r['dep_prov']:<42} {int(r['actas']):>6,}  "
                  f"{r['lean_1rv']*100:>9.3f}%  {r['lean_est']*100:>9.3f}%")
    print(sep)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print(f"\n{'='*72}")
    print(f"  ONPE 2026 - Analisis Segunda Vuelta  |  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*72}")

    prior    = cargar_prior()
    corridas, resultados = cargar_sv()

    if corridas.empty:
        print("DB vacia. Ejecuta segunda_vuelta_proyeccion.py primero.")
        return

    series = calcular_series(corridas, resultados, prior)
    resumen(series, corridas)
    graficar(series)


if __name__ == "__main__":
    main()

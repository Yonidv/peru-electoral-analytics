"""
ONPE 2026 — SEGUNDA VUELTA — Proyección lineal por PROVINCIA + EXTRANJERO por PAÍS
Descarga datos de las 196 provincias del Perú y los ~77 países del exterior,
proyecta cada unidad con su propio avance al 100% y totaliza a nivel:
  provincia → departamento → Perú
  país      → continente  → Extranjero
  TOTAL = Perú + Extranjero

Uso: python segunda_vuelta_proyeccion.py
"""
import urllib.request, json, time, csv, sqlite3
from datetime import datetime

ID_ELECCION = 10
DB_PATH     = "onpe_sv_resultados.db"

BASE = "https://resultadosegundavuelta.onpe.gob.pe/presentacion-backend"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://resultadosegundavuelta.onpe.gob.pe/main/resumen",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
}

# (dep_ubigeo, dep_nombre, prov_ubigeo, prov_nombre)  — 196 provincias
PROVINCIAS = [
    # AMAZONAS
    ("010000","AMAZONAS",      "010100","CHACHAPOYAS"),
    ("010000","AMAZONAS",      "010200","BAGUA"),
    ("010000","AMAZONAS",      "010300","BONGARÁ"),
    ("010000","AMAZONAS",      "010400","CONDORCANQUI"),
    ("010000","AMAZONAS",      "010500","LUYA"),
    ("010000","AMAZONAS",      "010600","RODRÍGUEZ DE MENDOZA"),
    ("010000","AMAZONAS",      "010700","UTCUBAMBA"),
    # ÁNCASH
    ("020000","ÁNCASH",        "020100","HUARAZ"),
    ("020000","ÁNCASH",        "020200","AIJA"),
    ("020000","ÁNCASH",        "020300","ANTONIO RAYMONDI"),
    ("020000","ÁNCASH",        "020400","ASUNCIÓN"),
    ("020000","ÁNCASH",        "020500","BOLOGNESI"),
    ("020000","ÁNCASH",        "020600","CARHUAZ"),
    ("020000","ÁNCASH",        "020700","CARLOS F. FITZCARRALD"),
    ("020000","ÁNCASH",        "020800","CASMA"),
    ("020000","ÁNCASH",        "020900","CORONGO"),
    ("020000","ÁNCASH",        "021000","HUARI"),
    ("020000","ÁNCASH",        "021100","HUARMEY"),
    ("020000","ÁNCASH",        "021200","HUAYLAS"),
    ("020000","ÁNCASH",        "021300","MARISCAL LUZURIAGA"),
    ("020000","ÁNCASH",        "021400","OCROS"),
    ("020000","ÁNCASH",        "021500","PALLASCA"),
    ("020000","ÁNCASH",        "021600","POMABAMBA"),
    ("020000","ÁNCASH",        "021700","RECUAY"),
    ("020000","ÁNCASH",        "021800","SANTA"),
    ("020000","ÁNCASH",        "021900","SIHUAS"),
    ("020000","ÁNCASH",        "022000","YUNGAY"),
    # APURÍMAC
    ("030000","APURÍMAC",      "030100","ABANCAY"),
    ("030000","APURÍMAC",      "030200","ANDAHUAYLAS"),
    ("030000","APURÍMAC",      "030300","ANTABAMBA"),
    ("030000","APURÍMAC",      "030400","AYMARAES"),
    ("030000","APURÍMAC",      "030500","COTABAMBAS"),
    ("030000","APURÍMAC",      "030600","CHINCHEROS"),
    ("030000","APURÍMAC",      "030700","GRAU"),
    # AREQUIPA
    ("040000","AREQUIPA",      "040100","AREQUIPA"),
    ("040000","AREQUIPA",      "040200","CAMANÁ"),
    ("040000","AREQUIPA",      "040300","CARAVELÍ"),
    ("040000","AREQUIPA",      "040400","CASTILLA"),
    ("040000","AREQUIPA",      "040500","CAYLLOMA"),
    ("040000","AREQUIPA",      "040600","CONDESUYOS"),
    ("040000","AREQUIPA",      "040700","ISLAY"),
    ("040000","AREQUIPA",      "040800","LA UNIÓN"),
    # AYACUCHO
    ("050000","AYACUCHO",      "050100","HUAMANGA"),
    ("050000","AYACUCHO",      "050200","CANGALLO"),
    ("050000","AYACUCHO",      "050300","HUANCA SANCOS"),
    ("050000","AYACUCHO",      "050400","HUANTA"),
    ("050000","AYACUCHO",      "050500","LA MAR"),
    ("050000","AYACUCHO",      "050600","LUCANAS"),
    ("050000","AYACUCHO",      "050700","PARINACOCHAS"),
    ("050000","AYACUCHO",      "050800","PÁUCAR DEL SARA SARA"),
    ("050000","AYACUCHO",      "050900","SUCRE"),
    ("050000","AYACUCHO",      "051000","VÍCTOR FAJARDO"),
    ("050000","AYACUCHO",      "051100","VILCAS HUAMÁN"),
    # CAJAMARCA
    ("060000","CAJAMARCA",     "060100","CAJAMARCA"),
    ("060000","CAJAMARCA",     "060200","CAJABAMBA"),
    ("060000","CAJAMARCA",     "060300","CELENDÍN"),
    ("060000","CAJAMARCA",     "060400","CHOTA"),
    ("060000","CAJAMARCA",     "060500","CONTUMAZÁ"),
    ("060000","CAJAMARCA",     "060600","CUTERVO"),
    ("060000","CAJAMARCA",     "060700","HUALGAYOC"),
    ("060000","CAJAMARCA",     "060800","JAÉN"),
    ("060000","CAJAMARCA",     "060900","SAN IGNACIO"),
    ("060000","CAJAMARCA",     "061000","SAN MARCOS"),
    ("060000","CAJAMARCA",     "061100","SAN MIGUEL"),
    ("060000","CAJAMARCA",     "061200","SAN PABLO"),
    ("060000","CAJAMARCA",     "061300","SANTA CRUZ"),
    # CALLAO
    ("240000","CALLAO",        "240100","CALLAO"),
    # CUSCO
    ("070000","CUSCO",         "070100","CUSCO"),
    ("070000","CUSCO",         "070200","ACOMAYO"),
    ("070000","CUSCO",         "070300","ANTA"),
    ("070000","CUSCO",         "070400","CALCA"),
    ("070000","CUSCO",         "070500","CANAS"),
    ("070000","CUSCO",         "070600","CANCHIS"),
    ("070000","CUSCO",         "070700","CHUMBIVILCAS"),
    ("070000","CUSCO",         "070800","ESPINAR"),
    ("070000","CUSCO",         "070900","LA CONVENCIÓN"),
    ("070000","CUSCO",         "071000","PARURO"),
    ("070000","CUSCO",         "071100","PAUCARTAMBO"),
    ("070000","CUSCO",         "071200","QUISPICANCHI"),
    ("070000","CUSCO",         "071300","URUBAMBA"),
    # HUANCAVELICA
    ("080000","HUANCAVELICA",  "080100","HUANCAVELICA"),
    ("080000","HUANCAVELICA",  "080200","ACOBAMBA"),
    ("080000","HUANCAVELICA",  "080300","ANGARAES"),
    ("080000","HUANCAVELICA",  "080400","CASTROVIRREYNA"),
    ("080000","HUANCAVELICA",  "080500","CHURCAMPA"),
    ("080000","HUANCAVELICA",  "080600","HUAYTARÁ"),
    ("080000","HUANCAVELICA",  "080700","TAYACAJA"),
    # HUÁNUCO
    ("090000","HUÁNUCO",       "090100","HUÁNUCO"),
    ("090000","HUÁNUCO",       "090200","AMBO"),
    ("090000","HUÁNUCO",       "090300","DOS DE MAYO"),
    ("090000","HUÁNUCO",       "090400","HUACAYBAMBA"),
    ("090000","HUÁNUCO",       "090500","HUAMALÍES"),
    ("090000","HUÁNUCO",       "090600","LEONCIO PRADO"),
    ("090000","HUÁNUCO",       "090700","MARAÑÓN"),
    ("090000","HUÁNUCO",       "090800","PACHITEA"),
    ("090000","HUÁNUCO",       "090900","PUERTO INCA"),
    ("090000","HUÁNUCO",       "091000","LAURICOCHA"),
    ("090000","HUÁNUCO",       "091100","YAROWILCA"),
    # ICA
    ("100000","ICA",           "100100","ICA"),
    ("100000","ICA",           "100200","CHINCHA"),
    ("100000","ICA",           "100300","NASCA"),
    ("100000","ICA",           "100400","PALPA"),
    ("100000","ICA",           "100500","PISCO"),
    # JUNÍN  (9 provincias confirmadas via API)
    ("110000","JUNÍN",         "110100","HUANCAYO"),
    ("110000","JUNÍN",         "110200","CONCEPCIÓN"),
    ("110000","JUNÍN",         "110300","CHANCHAMAYO"),
    ("110000","JUNÍN",         "110400","JUNÍN"),
    ("110000","JUNÍN",         "110500","SATIPO"),
    ("110000","JUNÍN",         "110600","TARMA"),
    ("110000","JUNÍN",         "110700","YAULI"),
    ("110000","JUNÍN",         "110800","CHUPACA"),
    ("110000","JUNÍN",         "110900","JUNÍN-P9"),   # nombre a verificar
    # LA LIBERTAD
    ("120000","LA LIBERTAD",   "120100","TRUJILLO"),
    ("120000","LA LIBERTAD",   "120200","ASCOPE"),
    ("120000","LA LIBERTAD",   "120300","BOLÍVAR"),
    ("120000","LA LIBERTAD",   "120400","CHEPÉN"),
    ("120000","LA LIBERTAD",   "120500","JULCÁN"),
    ("120000","LA LIBERTAD",   "120600","OTUZCO"),
    ("120000","LA LIBERTAD",   "120700","PACASMAYO"),
    ("120000","LA LIBERTAD",   "120800","PATAZ"),
    ("120000","LA LIBERTAD",   "120900","SÁNCHEZ CARRIÓN"),
    ("120000","LA LIBERTAD",   "121000","SANTIAGO DE CHUCO"),
    ("120000","LA LIBERTAD",   "121100","GRAN CHIMÚ"),
    ("120000","LA LIBERTAD",   "121200","VIRÚ"),
    # LAMBAYEQUE
    ("130000","LAMBAYEQUE",    "130100","CHICLAYO"),
    ("130000","LAMBAYEQUE",    "130200","FERREÑAFE"),
    ("130000","LAMBAYEQUE",    "130300","LAMBAYEQUE"),
    # LIMA
    ("140000","LIMA",          "140100","LIMA"),
    ("140000","LIMA",          "140200","BARRANCA"),
    ("140000","LIMA",          "140300","CAJATAMBO"),
    ("140000","LIMA",          "140400","CANTA"),
    ("140000","LIMA",          "140500","CAÑETE"),
    ("140000","LIMA",          "140600","HUARAL"),
    ("140000","LIMA",          "140700","HUAROCHIRÍ"),
    ("140000","LIMA",          "140800","HUAURA"),
    ("140000","LIMA",          "140900","OYÓN"),
    ("140000","LIMA",          "141000","YAUYOS"),
    # LORETO  (nota: salta 150800 — no existe en ONPE)
    ("150000","LORETO",        "150100","MAYNAS"),
    ("150000","LORETO",        "150200","ALTO AMAZONAS"),
    ("150000","LORETO",        "150300","LORETO"),
    ("150000","LORETO",        "150400","MARISCAL RAMÓN CASTILLA"),
    ("150000","LORETO",        "150500","REQUENA"),
    ("150000","LORETO",        "150600","UCAYALI"),
    ("150000","LORETO",        "150700","DATEM DEL MARAÑÓN"),
    ("150000","LORETO",        "150900","PUTUMAYO"),
    # MADRE DE DIOS
    ("160000","MADRE DE DIOS", "160100","TAMBOPATA"),
    ("160000","MADRE DE DIOS", "160200","MANU"),
    ("160000","MADRE DE DIOS", "160300","TAHUAMANU"),
    # MOQUEGUA
    ("170000","MOQUEGUA",      "170100","MARISCAL NIETO"),
    ("170000","MOQUEGUA",      "170200","GENERAL SÁNCHEZ CERRO"),
    ("170000","MOQUEGUA",      "170300","ILO"),
    # PASCO
    ("180000","PASCO",         "180100","PASCO"),
    ("180000","PASCO",         "180200","DANIEL ALCIDES CARRIÓN"),
    ("180000","PASCO",         "180300","OXAPAMPA"),
    # PIURA
    ("190000","PIURA",         "190100","PIURA"),
    ("190000","PIURA",         "190200","AYABACA"),
    ("190000","PIURA",         "190300","HUANCABAMBA"),
    ("190000","PIURA",         "190400","MORROPÓN"),
    ("190000","PIURA",         "190500","PAITA"),
    ("190000","PIURA",         "190600","SULLANA"),
    ("190000","PIURA",         "190700","TALARA"),
    ("190000","PIURA",         "190800","SECHURA"),
    # PUNO
    ("200000","PUNO",          "200100","PUNO"),
    ("200000","PUNO",          "200200","AZÁNGARO"),
    ("200000","PUNO",          "200300","CARABAYA"),
    ("200000","PUNO",          "200400","CHUCUITO"),
    ("200000","PUNO",          "200500","EL COLLAO"),
    ("200000","PUNO",          "200600","HUANCANÉ"),
    ("200000","PUNO",          "200700","LAMPA"),
    ("200000","PUNO",          "200800","MELGAR"),
    ("200000","PUNO",          "200900","MOHO"),
    ("200000","PUNO",          "201000","SAN ANTONIO DE PUTINA"),
    ("200000","PUNO",          "201100","SAN ROMÁN"),
    ("200000","PUNO",          "201200","SANDIA"),
    ("200000","PUNO",          "201300","YUNGUYO"),
    # SAN MARTÍN
    ("210000","SAN MARTÍN",    "210100","MOYOBAMBA"),
    ("210000","SAN MARTÍN",    "210200","BELLAVISTA"),
    ("210000","SAN MARTÍN",    "210300","EL DORADO"),
    ("210000","SAN MARTÍN",    "210400","HUALLAGA"),
    ("210000","SAN MARTÍN",    "210500","LAMAS"),
    ("210000","SAN MARTÍN",    "210600","MARISCAL CÁCERES"),
    ("210000","SAN MARTÍN",    "210700","PICOTA"),
    ("210000","SAN MARTÍN",    "210800","RIOJA"),
    ("210000","SAN MARTÍN",    "210900","SAN MARTÍN"),
    ("210000","SAN MARTÍN",    "211000","TOCACHE"),
    # TACNA
    ("220000","TACNA",         "220100","TACNA"),
    ("220000","TACNA",         "220200","CANDARAVE"),
    ("220000","TACNA",         "220300","JORGE BASADRE"),
    ("220000","TACNA",         "220400","TARATA"),
    # TUMBES
    ("230000","TUMBES",        "230100","TUMBES"),
    ("230000","TUMBES",        "230200","CONTRALMIRANTE VILLAR"),
    ("230000","TUMBES",        "230300","ZARUMILLA"),
    # UCAYALI
    ("250000","UCAYALI",       "250100","CORONEL PORTILLO"),
    ("250000","UCAYALI",       "250200","ATALAYA"),
    ("250000","UCAYALI",       "250300","PADRE ABAD"),
    ("250000","UCAYALI",       "250400","PURÚS"),
]

LIST_R = "TODOS,PER%C3%9A,EXTRANJERO"

# Continentes EXTRANJERO (ubigeos 91xxxx–95xxxx)
CONTINENTES_EXT = [
    ("910000", "EXTRANJERO/AFRICA"),
    ("920000", "EXTRANJERO/AMERICA"),
    ("930000", "EXTRANJERO/ASIA"),
    ("940000", "EXTRANJERO/EUROPA"),
    ("950000", "EXTRANJERO/OCEANIA"),
]

# ─── URLs — Perú ──────────────────────────────────────────────────────────────
def u_cand_nac():
    return f"{BASE}/eleccion-presidencial/participantes-ubicacion-geografica-nombre?idEleccion={ID_ELECCION}&tipoFiltro=eleccion"

def u_res_nac():
    return f"{BASE}/resumen-general/totales?idEleccion={ID_ELECCION}&tipoFiltro=eleccion"

def u_cand_prov(dep_ubigeo, prov_ubigeo):
    return (f"{BASE}/eleccion-presidencial/participantes-ubicacion-geografica-nombre"
            f"?tipoFiltro=ubigeo_nivel_02&idAmbitoGeografico=1"
            f"&ubigeoNivel1={dep_ubigeo}&ubigeoNivel2={prov_ubigeo}"
            f"&listRegiones={LIST_R}&idEleccion={ID_ELECCION}")

def u_res_prov(dep_ubigeo, prov_ubigeo):
    return (f"{BASE}/resumen-general/totales"
            f"?idAmbitoGeografico=1&idEleccion={ID_ELECCION}&tipoFiltro=ubigeo_nivel_02"
            f"&idUbigeoDepartamento={dep_ubigeo}&idUbigeoProvincia={prov_ubigeo}")

# ─── URLs — Extranjero ────────────────────────────────────────────────────────
def u_paises_continente(cont_ubigeo):
    return (f"{BASE}/ubigeos/provincias"
            f"?idEleccion={ID_ELECCION}&idAmbitoGeografico=2&idUbigeoDepartamento={cont_ubigeo}")

def u_cand_cont(cont_ubigeo):
    """Agregado del continente (votos totales del continente)."""
    return (f"{BASE}/eleccion-presidencial/participantes-ubicacion-geografica-nombre"
            f"?tipoFiltro=ubigeo_nivel_01&idAmbitoGeografico=2"
            f"&ubigeoNivel1={cont_ubigeo}&idEleccion={ID_ELECCION}")

def u_res_cont(cont_ubigeo):
    return (f"{BASE}/resumen-general/totales"
            f"?idAmbitoGeografico=2&idEleccion={ID_ELECCION}"
            f"&tipoFiltro=ubigeo_nivel_01&idUbigeoDepartamento={cont_ubigeo}")

def u_cand_pais(cont_ubigeo, pais_ubigeo):
    return (f"{BASE}/eleccion-presidencial/participantes-ubicacion-geografica-nombre"
            f"?tipoFiltro=ubigeo_nivel_02&idAmbitoGeografico=2"
            f"&ubigeoNivel1={cont_ubigeo}&ubigeoNivel2={pais_ubigeo}"
            f"&listRegiones={LIST_R}&idEleccion={ID_ELECCION}")

def u_res_pais(cont_ubigeo, pais_ubigeo):
    return (f"{BASE}/resumen-general/totales"
            f"?idAmbitoGeografico=2&idEleccion={ID_ELECCION}&tipoFiltro=ubigeo_nivel_02"
            f"&idUbigeoDepartamento={cont_ubigeo}&idUbigeoProvincia={pais_ubigeo}")

# ─── HTTP ──────────────────────────────────────────────────────────────────────
def get(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as r:
        body = r.read()
        if not body:
            return {}
        return json.loads(body.decode("utf-8"))

def descargar_unidad(url_cands, url_res):
    """Descarga candidatos + resumen para cualquier unidad geográfica."""
    try:
        cands = get(url_cands).get("data", [])
    except:
        cands = []
    try:
        resumen = get(url_res).get("data", {})
    except:
        resumen = {}
    time.sleep(0.2)
    return cands, resumen

def descargar_provincia(dep_ubigeo, prov_ubigeo):
    return descargar_unidad(u_cand_prov(dep_ubigeo, prov_ubigeo),
                             u_res_prov(dep_ubigeo, prov_ubigeo))

# ─── Proyección lineal ────────────────────────────────────────────────────────
def proyectar(votos, pct_avance):
    if pct_avance and pct_avance > 0:
        return round(votos / (pct_avance / 100))
    return None   # avance 0% → no se proyecta

# ─── SQLite ───────────────────────────────────────────────────────────────────
def init_db(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS corridas (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            ts               TEXT    NOT NULL UNIQUE,
            avance_nac       REAL,
            actas_cont_nac   INTEGER,
            total_actas_nac  INTEGER,
            votos_validos_nac  INTEGER,
            votos_emitidos_nac INTEGER
        );
        CREATE TABLE IF NOT EXISTS resultados (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            corrida_id    INTEGER NOT NULL REFERENCES corridas(id),
            ts            TEXT    NOT NULL,
            tipo          TEXT    NOT NULL,
            departamento  TEXT    NOT NULL,
            provincia     TEXT    NOT NULL,
            dep_ubigeo    TEXT,
            prov_ubigeo   TEXT,
            pct_actas     REAL,
            actas_cont    INTEGER,
            total_actas   INTEGER,
            actas_jee     INTEGER,
            actas_pend    INTEGER,
            hora_upd      TEXT,
            candidato     TEXT    NOT NULL,
            partido       TEXT,
            votos_validos INTEGER,
            pct_vv        REAL,
            pct_ve        REAL,
            votos_proy    INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_res_corrida ON resultados(corrida_id);
        CREATE INDEX IF NOT EXISTS idx_res_unidad  ON resultados(departamento, provincia, candidato);
        CREATE INDEX IF NOT EXISTS idx_res_ts_cand ON resultados(ts, candidato);
    """)
    conn.commit()

def insertar_corrida(conn, ts, res_nac):
    cur = conn.execute(
        """INSERT OR IGNORE INTO corridas
           (ts, avance_nac, actas_cont_nac, total_actas_nac, votos_validos_nac, votos_emitidos_nac)
           VALUES (?,?,?,?,?,?)""",
        (ts,
         res_nac.get("actasContabilizadas"),
         res_nac.get("contabilizadas"),
         res_nac.get("totalActas"),
         res_nac.get("totalVotosValidos"),
         res_nac.get("totalVotosEmitidos")),
    )
    conn.commit()
    if cur.lastrowid:
        return cur.lastrowid
    return conn.execute("SELECT id FROM corridas WHERE ts=?", (ts,)).fetchone()[0]

def insertar_resultados(conn, corrida_id, filas):
    ES_EXT = lambda dep: dep.startswith("EXTRANJERO/")
    def _int(v):  return int(v)   if v != "" and v is not None else None
    def _float(v): return float(v) if v != "" and v is not None else None
    rows = []
    for f in filas:
        dep = f["departamento"]
        rows.append((
            corrida_id,
            f["timestamp"],
            "pais" if ES_EXT(dep) else "provincia",
            dep,
            f["provincia"],
            f["dep_ubigeo"],
            f["prov_ubigeo"],
            _float(f["pct_actas_contab"]),
            _int(f["actas_contabilizadas"]),
            _int(f["total_actas"]),
            _int(f["actas_jee"]),
            _int(f["actas_pend"]),
            f["ultima_actualizacion"] if f["ultima_actualizacion"] != "" else None,
            f["candidato"],
            f["partido"],
            _int(f["votos_validos"]),
            _float(f["pct_votos_validos"]),
            _float(f["pct_votos_emitidos"]),
            None,   # votos_proy — proyeccion lineal descontinuada; analisis_sv.py usa su propio modelo
        ))
    conn.executemany(
        """INSERT INTO resultados
           (corrida_id, ts, tipo, departamento, provincia, dep_ubigeo, prov_ubigeo,
            pct_actas, actas_cont, total_actas, actas_jee, actas_pend, hora_upd,
            candidato, partido, votos_validos, pct_vv, pct_ve, votos_proy)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        rows,
    )
    conn.commit()

# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ts_file   = datetime.now().strftime("%Y%m%d_%H%M")
    print(f"\n{'='*75}")
    print(f"  ONPE 2026 — SEGUNDA VUELTA — Proyección por Provincia   |   {timestamp}")
    print(f"{'='*75}")

    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    # ── NACIONAL + agregados Peru/Ext (todos al mismo instante t=0) ──
    print("Descargando NACIONAL...", end="", flush=True)
    try:
        cands_nac  = get(u_cand_nac()).get("data", [])
        res_nac    = get(u_res_nac()).get("data", {})
        # Agregado PERU (ambito=1) y EXTRANJERO (ambito=2) — para cuadrar totales
        cands_peru_agg = get(f"{BASE}/eleccion-presidencial/participantes-ubicacion-geografica-nombre"
                             f"?tipoFiltro=ambito_geografico&idAmbitoGeografico=1"
                             f"&listRegiones={LIST_R}&idEleccion={ID_ELECCION}").get("data", [])
        cands_ext_agg  = get(f"{BASE}/eleccion-presidencial/participantes-ubicacion-geografica-nombre"
                             f"?tipoFiltro=ambito_geografico&idAmbitoGeografico=2"
                             f"&listRegiones={LIST_R}&idEleccion={ID_ELECCION}").get("data", [])
    except Exception as e:
        cands_nac, res_nac, cands_peru_agg, cands_ext_agg = [], {}, [], []
        print(f" ERROR: {e}")
    print(" OK")

    if not res_nac and not cands_nac:
        print("API sin datos aún para idEleccion=11. Inténtalo en unos minutos.")
        conn.close()
        return

    corrida_id = insertar_corrida(conn, timestamp, res_nac)

    # Mapas de votos reales autoritativos (t=0, misma snapshot que ONPE muestra)
    votos_nac_map  = {c["nombreCandidato"]: c.get("totalVotosValidos", 0)
                      for c in cands_nac if c.get("nombreCandidato")}
    votos_peru_agg = {c["nombreCandidato"]: c.get("totalVotosValidos", 0)
                      for c in cands_peru_agg if c.get("nombreCandidato")}
    votos_ext_agg  = {c["nombreCandidato"]: c.get("totalVotosValidos", 0)
                      for c in cands_ext_agg if c.get("nombreCandidato")}

    # ── 196 PROVINCIAS ──
    print(f"Descargando 196 provincias", end="", flush=True)
    datos = {}   # (dep_nombre, prov_nombre) -> (dep_ubigeo, prov_ubigeo, cands, resumen)
    dep_actual = None
    for dep_ubigeo, dep_nombre, prov_ubigeo, prov_nombre in PROVINCIAS:
        if dep_nombre != dep_actual:
            print(f"\n  {dep_nombre:<20}", end="", flush=True)
            dep_actual = dep_nombre
        cands, resumen = descargar_provincia(dep_ubigeo, prov_ubigeo)
        datos[(dep_nombre, prov_nombre)] = (dep_ubigeo, prov_ubigeo, cands, resumen)
        print(".", end="", flush=True)
    print("\nDescarga Perú completada.")

    # ── EXTRANJERO: agregado por continente + desglose por país ──
    print(f"Descargando EXTRANJERO por continente y país", end="", flush=True)
    n_paises_total  = 0
    datos_cont_ext  = {}   # cont_nombre -> (cont_ubigeo, cands_agg, res_agg)
    votos_cont_sum  = {}   # acumula suma de los 5 agregados de continente

    for cont_ubigeo, cont_nombre in CONTINENTES_EXT:
        print(f"\n  {cont_nombre:<28}", end="", flush=True)

        # 1. Agregado del continente (fuente autoritativa de votos y avance)
        cands_agg, res_agg = descargar_unidad(u_cand_cont(cont_ubigeo),
                                               u_res_cont(cont_ubigeo))
        datos_cont_ext[cont_nombre] = (cont_ubigeo, cands_agg, res_agg)
        votos_agg = {c["nombreCandidato"]: c.get("totalVotosValidos", 0)
                     for c in cands_agg if c.get("nombreCandidato")}
        pct_cont  = res_agg.get("actasContabilizadas")
        # Acumular para detectar votos sin continente asignado
        for nc, v in votos_agg.items():
            votos_cont_sum[nc] = votos_cont_sum.get(nc, 0) + v

        # 2. Países individuales
        try:
            paises = get(u_paises_continente(cont_ubigeo)).get("data", [])
        except:
            paises = []

        votos_paises = {}   # cand -> suma votos de todos los países del continente
        for p in paises:
            pais_ubigeo = p["ubigeo"]
            pais_nombre = p["nombre"]
            cands_p, res_p = descargar_unidad(
                u_cand_pais(cont_ubigeo, pais_ubigeo),
                u_res_pais(cont_ubigeo, pais_ubigeo),
            )
            datos[(cont_nombre, pais_nombre)] = (cont_ubigeo, pais_ubigeo, cands_p, res_p)
            for c in cands_p:
                nc = c.get("nombreCandidato", "")
                if nc:
                    votos_paises[nc] = votos_paises.get(nc, 0) + c.get("totalVotosValidos", 0)
            print(".", end="", flush=True)
            n_paises_total += 1

        # 3. Gap: votos en el agregado del continente que no aparecen en ningún país
        cands_sin_pais = []
        for nc, v_agg in votos_agg.items():
            diff = v_agg - votos_paises.get(nc, 0)
            if diff > 0:
                cands_sin_pais.append({
                    "nombreCandidato":          nc,
                    "nombreAgrupacionPolitica": "",
                    "totalVotosValidos":        diff,
                    "porcentajeVotosValidos":   0,
                    "porcentajeVotosEmitidos":  0,
                })
        if cands_sin_pais:
            # Usa el avance del continente para proyectar estos votos sin país
            res_sin = {"actasContabilizadas": pct_cont, "contabilizadas": 0, "totalActas": 0}
            datos[(cont_nombre, "SIN PAÍS IDENTIFICADO")] = (
                cont_ubigeo, "000000", cands_sin_pais, res_sin
            )

    # 4. Gap nivel superior: votos en el total EXTRANJERO sin continente asignado
    #    votos_ext_agg (t=0) vs suma de los 5 agregados de continente
    cands_sin_cont = []
    for nc, v_ext in votos_ext_agg.items():
        diff = v_ext - votos_cont_sum.get(nc, 0)
        if diff > 0:
            cands_sin_cont.append({
                "nombreCandidato":          nc,
                "nombreAgrupacionPolitica": "",
                "totalVotosValidos":        diff,
                "porcentajeVotosValidos":   0,
                "porcentajeVotosEmitidos":  0,
            })
    if cands_sin_cont:
        pct_ext_global = res_nac.get("actasContabilizadas")  # usa avance nacional como referencia
        res_sin_cont   = {"actasContabilizadas": pct_ext_global, "contabilizadas": 0, "totalActas": 0}
        datos[("EXTRANJERO/SIN CONTINENTE", "SIN CONTINENTE IDENTIFICADO")] = (
            "990000", "999999", cands_sin_cont, res_sin_cont
        )

    print(f"\nDescarga Extranjero completada ({n_paises_total} países).")

    # ── Construir filas CSV ──
    filas = []
    for (dep_nombre, prov_nombre), (dep_ubigeo, prov_ubigeo, cands, resumen) in datos.items():
        pct_avance  = resumen.get("actasContabilizadas")
        actas_cont  = resumen.get("contabilizadas", "")
        total_actas = resumen.get("totalActas", "")
        actas_jee   = resumen.get("enviadasJee", "")
        actas_pend  = resumen.get("pendientesJee", "")
        fecha_act   = resumen.get("fechaActualizacion", "")
        if fecha_act:
            try:
                fecha_act = datetime.fromtimestamp(fecha_act / 1000).strftime("%H:%M:%S")
            except:
                pass

        for c in cands:
            nombre_c = c.get("nombreCandidato", "")
            partido  = c.get("nombreAgrupacionPolitica", "")
            votos    = c.get("totalVotosValidos", 0)
            pct_vv   = c.get("porcentajeVotosValidos", 0)
            pct_ve   = c.get("porcentajeVotosEmitidos", 0)
            proy     = proyectar(votos, pct_avance)

            filas.append({
                "timestamp":           timestamp,
                "departamento":        dep_nombre,
                "provincia":           prov_nombre,
                "dep_ubigeo":          dep_ubigeo,
                "prov_ubigeo":         prov_ubigeo,
                "pct_actas_contab":    pct_avance if pct_avance is not None else "",
                "actas_contabilizadas":actas_cont,
                "total_actas":         total_actas,
                "actas_jee":           actas_jee,
                "actas_pend":          actas_pend,
                "ultima_actualizacion":fecha_act,
                "candidato":           nombre_c,
                "partido":             partido,
                "votos_validos":       votos,
                "pct_votos_validos":   pct_vv,
                "pct_votos_emitidos":  pct_ve,
                "votos_proyectados":   proy if proy is not None else "",
            })

    # ── Guardar CSV ──
    campos = [
        "timestamp","departamento","provincia","dep_ubigeo","prov_ubigeo",
        "pct_actas_contab","actas_contabilizadas","total_actas",
        "actas_jee","actas_pend","ultima_actualizacion",
        "candidato","partido",
        "votos_validos","pct_votos_validos","pct_votos_emitidos","votos_proyectados",
    ]
    csv_path   = f"onpe_sv_prov_{ts_file}.csv"
    csv_latest = "onpe_sv_prov_LATEST.csv"
    for path in [csv_path, csv_latest]:
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=campos)
            w.writeheader()
            w.writerows(filas)

    # ── Guardar JSON raw ──
    json_data = {
        f"{dep}/{prov}": {"candidatos": c, "resumen": r}
        for (dep, prov), (_, _, c, r) in datos.items()
    }
    with open(f"onpe_sv_prov_raw_{ts_file}.json", "w", encoding="utf-8") as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)

    # ── Guardar en SQLite ──
    insertar_resultados(conn, corrida_id, filas)
    conn.close()
    print(f"SQLite: corrida #{corrida_id} guardada en {DB_PATH}  ({len(filas)} filas)")
    print(f"CSV:    {csv_path}  ({len(filas)} filas)")

def _unused_projection_output():
    # Proyecciones lineales propias — no usadas por analisis_sv.py.
    # Conservadas aquí por referencia; nunca se llaman.
    totales_dep = {}   # dep/continente -> {cand -> proy_sum}
    unidades_sin_avance = 0
    unidades_con_avance = 0

    for fila in filas:
        cand = fila["candidato"]
        dep  = fila["departamento"]
        proy = fila["votos_proyectados"]
        if not cand or proy == "" or proy is None:
            continue
        totales_dep.setdefault(dep, {})
        totales_dep[dep][cand] = totales_dep[dep].get(cand, 0) + int(proy)

    # Contar unidades con/sin avance
    vistas = set()
    for fila in filas:
        key = (fila["departamento"], fila["provincia"])
        if key in vistas:
            continue
        vistas.add(key)
        if fila["pct_actas_contab"] == "" or fila["pct_actas_contab"] == 0:
            unidades_sin_avance += 1
        else:
            unidades_con_avance += 1

    # Separar Perú vs Extranjero en los totales
    ES_EXT = lambda dep: dep.startswith("EXTRANJERO/")

    totales_peru = {}
    totales_ext  = {}
    for dep, cd in totales_dep.items():
        destino = totales_ext if ES_EXT(dep) else totales_peru
        for cand, v in cd.items():
            destino[cand] = destino.get(cand, 0) + v

    # Gran total = Perú + Extranjero
    totales_nac = {}
    for cand, v in totales_peru.items():
        totales_nac[cand] = totales_nac.get(cand, 0) + v
    for cand, v in totales_ext.items():
        totales_nac[cand] = totales_nac.get(cand, 0) + v

    total_votos      = sum(totales_nac.values())
    total_votos_peru = sum(totales_peru.values())
    total_votos_ext  = sum(totales_ext.values())
    ranking = sorted(totales_nac.items(), key=lambda x: x[1], reverse=True)

    # ── Clasificación segunda vuelta ──
    pct_avance_nac   = res_nac.get("actasContabilizadas") or 0
    total_nac_actual = sum(votos_nac_map.values())
    if pct_avance_nac and pct_avance_nac > 0:
        votos_restantes = round(total_nac_actual * (100 - pct_avance_nac) / pct_avance_nac)
    else:
        votos_restantes = None

    v1_act = votos_nac_map.get(ranking[0][0], 0) if len(ranking) > 0 else 0
    v2_act = votos_nac_map.get(ranking[1][0], 0) if len(ranking) > 1 else 0
    margen_actual = v1_act - v2_act

    def estado_ganador(pos):
        if votos_restantes is None or pct_avance_nac == 0:
            return ""
        if margen_actual > votos_restantes:
            return "** RESULTADO DEFINIDO **" if pos == 1 else "   resultado definido"
        if pos == 1:
            return f"   GANANDO  margen {margen_actual:,}  (faltan ~{votos_restantes:,})"
        return     f"   PERDIENDO margen {margen_actual:,}  (faltan ~{votos_restantes:,})"

    # ─────────────────────────────────────────────────────────────────────────
    # ── Tabla: avance por departamento (Perú) ──
    # ─────────────────────────────────────────────────────────────────────────
    print(f"\n{'='*90}")
    print(f"  AVANCE POR DEPARTAMENTO — PERU (top 2 candidatos, proyeccion acumulada)")
    print(f"{'='*90}")
    print(f"  {'DEPARTAMENTO':<20} {'UNIDS':>5} {'AVANCE(*)':>10}  {'CANDIDATO':<36} {'PROY':>12}")
    print(f"  {'-'*88}")
    for dep_nombre in sorted(k for k in totales_dep if not ES_EXT(k)):
        total_actas_dep = 0; actas_cont_dep = 0; n_provs = 0
        for (dn, pn), (_, _, _, res) in datos.items():
            if dn != dep_nombre:
                continue
            n_provs += 1
            ta = res.get("totalActas", 0) or 0
            ac = res.get("contabilizadas", 0) or 0
            total_actas_dep += ta
            actas_cont_dep  += ac
        avance_pond = (actas_cont_dep / total_actas_dep * 100) if total_actas_dep > 0 else 0
        ranking_dep = sorted(totales_dep[dep_nombre].items(), key=lambda x: x[1], reverse=True)
        total_dep   = sum(v for _, v in ranking_dep)
        for i, (cand, v) in enumerate(ranking_dep[:2]):
            dep_str    = dep_nombre if i == 0 else ""
            avance_str = f"{avance_pond:.1f}%" if i == 0 else ""
            provs_str  = f"{n_provs}" if i == 0 else ""
            pct_dep    = v / total_dep * 100 if total_dep else 0
            print(f"  {dep_str:<20} {provs_str:>5} {avance_str:>10}  {cand[:34]:<36} {v:>12,}  ({pct_dep:.1f}%)")

    # ─────────────────────────────────────────────────────────────────────────
    # ── Tabla: avance por continente (Extranjero) ──
    # ─────────────────────────────────────────────────────────────────────────
    print(f"\n{'='*90}")
    print(f"  AVANCE POR CONTINENTE — EXTRANJERO (top 2 candidatos, proyeccion acumulada)")
    print(f"{'='*90}")
    print(f"  {'CONTINENTE':<28} {'PAISES':>6} {'AVANCE(*)':>10}  {'CANDIDATO':<36} {'PROY':>10}")
    print(f"  {'-'*88}")
    for cont_ubigeo, cont_nombre in CONTINENTES_EXT:
        if cont_nombre not in totales_dep:
            continue
        _, cands_agg, res_agg = datos_cont_ext[cont_nombre]
        pct_cont_c   = res_agg.get("actasContabilizadas") or 0
        actas_c      = res_agg.get("contabilizadas", 0) or 0
        total_actas_c= res_agg.get("totalActas", 0) or 0
        # Contar sólo países reales (excluir entradas sintéticas)
        n_paises = sum(1 for (dn, pn) in datos
                       if dn == cont_nombre
                       and pn not in ("SIN PAÍS IDENTIFICADO", "SIN CONTINENTE IDENTIFICADO"))
        ranking_c = sorted(totales_dep[cont_nombre].items(), key=lambda x: x[1], reverse=True)
        total_c   = sum(v for _, v in ranking_c)
        label = cont_nombre.split("/")[1]
        for i, (cand, v) in enumerate(ranking_c[:2]):
            c_str = label if i == 0 else ""
            a_str = f"{pct_cont_c:.1f}%" if i == 0 else ""
            p_str = f"{n_paises}" if i == 0 else ""
            pct_c = v / total_c * 100 if total_c else 0
            print(f"  {c_str:<28} {p_str:>6} {a_str:>10}  {cand[:34]:<36} {v:>10,}  ({pct_c:.1f}%)")

    # ─────────────────────────────────────────────────────────────────────────
    # ── Tabla: ranking final PERU + EXTRANJERO ──
    # ─────────────────────────────────────────────────────────────────────────
    col_w = 108
    n_peru = len([k for k in vistas if not ES_EXT(k[0])])
    n_ext  = len([k for k in vistas if ES_EXT(k[0])])
    print(f"\n{'='*col_w}")
    print(f"  PROYECCION TOTAL — PERU ({n_peru} unidades) + EXTRANJERO ({n_ext} paises)")
    print(f"  Avance NACIONAL: {pct_avance_nac:.1f}%  |  Unidades con avance: {unidades_con_avance}  |  sin avance: {unidades_sin_avance}")
    if votos_restantes is not None:
        print(f"  Votos actuales nac.: {total_nac_actual:,}  |  Restantes estimados: {votos_restantes:,}  |  Umbral eliminacion: {v2_act:,}")
    print(f"{'='*col_w}")
    print(f"  {'#':<4} {'CANDIDATO':<42} {'PERU':>13} {'EXTRAN':>10} {'TOTAL':>13} {'%':>7}  ESTADO")
    print(f"  {'-'*col_w}")
    for i, (cand, total) in enumerate(ranking, 1):
        pct_total  = total / total_votos * 100 if total_votos else 0
        v_peru     = totales_peru.get(cand, 0)
        v_ext      = totales_ext.get(cand, 0)
        est        = estado_ganador(i)
        print(f"  {i:<4} {cand[:40]:<42} {v_peru:>13,} {v_ext:>10,} {total:>13,} {pct_total:>6.3f}%  {est}")
    print(f"  {'-'*col_w}")
    print(f"  {'PERU':<46} {total_votos_peru:>13,}")
    print(f"  {'EXTRANJERO':<46} {total_votos_ext:>13,}")
    print(f"  {'TOTAL VOTOS VÁLIDOS PROYECTADOS':<46} {total_votos:>13,}")

    # ─────────────────────────────────────────────────────────────────────────
    # ── Detalle de votos reales + proyectados por unidad — TOP 3 candidatos ──
    # ─────────────────────────────────────────────────────────────────────────
    TOP_N_CANDS  = 3
    TOP_N_UNIDS  = 25  # top 25 unidades por candidato; el resto va a "OTROS"

    # Construir: cand -> (dep, prov) -> [votos_reales, votos_proyectados]
    # actas_unidad: (dep, prov) -> (pct, contabilizadas, enviadas_jee, pendientes_jee, total)
    detalle_unidad = {}
    actas_unidad   = {}
    for fila in filas:
        cand  = fila["candidato"]
        if not cand:
            continue
        dep   = fila["departamento"]
        prov  = fila["provincia"]
        vreal = int(fila["votos_validos"])        if fila["votos_validos"]        else 0
        vproy = int(fila["votos_proyectados"])    if fila["votos_proyectados"] != "" else 0
        key   = (dep, prov)
        detalle_unidad.setdefault(cand, {})
        detalle_unidad[cand].setdefault(key, [0, 0])
        detalle_unidad[cand][key][0] += vreal
        detalle_unidad[cand][key][1] += vproy

    # Actas desde datos (resumen directo — tiene enviadasJee y pendientesJee)
    for (dep, prov), (_, _, cands_u, res_u) in datos.items():
        key  = (dep, prov)
        pct  = res_u.get("actasContabilizadas")
        cont = res_u.get("contabilizadas", 0) or 0
        jee  = res_u.get("enviadasJee", 0) or 0
        pend = res_u.get("pendientesJee", 0) or 0
        tot  = res_u.get("totalActas", 0) or 0
        actas_unidad[key] = (pct, cont, jee, pend, tot)

    col_d = 122
    print(f"\n{'='*col_d}")
    print(f"  DETALLE TOP {TOP_N_CANDS} CANDIDATOS — votos REALES a la fecha + PROYECTADOS al 100%")
    print(f"  (Top {TOP_N_UNIDS} unidades con mayor aporte proyectado; el resto agrupado en OTROS)")
    print(f"{'='*col_d}")

    for pos, (cand, total_proy) in enumerate(ranking[:TOP_N_CANDS], 1):
        v_real_nac    = votos_nac_map.get(cand, 0)      # nacional t=0 = lo que muestra ONPE
        v_real_peru   = votos_peru_agg.get(cand, 0)     # Peru agregado t=0
        v_real_ext    = votos_ext_agg.get(cand, 0)      # Extranjero agregado t=0
        v_proy_total  = total_proy
        v_peru_proy   = totales_peru.get(cand, 0)
        v_ext_proy    = totales_ext.get(cand, 0)
        pct_proy      = v_proy_total / total_votos * 100 if total_votos else 0
        ganancia      = v_proy_total - v_real_nac

        print(f"\n  {'─'*col_d}")
        print(f"  #{pos}  {cand}")
        print(f"  {'─'*col_d}")
        print(f"  {'Votos REALES — Peru:':<46} {v_real_peru:>13,}")
        print(f"  {'Votos REALES — Extranjero:':<46} {v_real_ext:>13,}")
        print(f"  {'Votos REALES TOTAL:':<46} {v_real_nac:>13,}")
        print(f"  {'Votos PROYECTADOS al 100% de actas:':<46} {v_proy_total:>13,}  ({pct_proy:.3f}% del total proyectado)")
        print(f"  {'  -> Ganancia estimada de actas pendientes:':<46} {ganancia:>13,}")
        print()

        # Unidades ordenadas por votos proyectados desc
        unidades = detalle_unidad.get(cand, {})
        unid_sorted = sorted(unidades.items(), key=lambda x: x[1][1] - x[1][0], reverse=True)

        # %GAN usa ganancia del encabezado como denominador.
        # OTROS absorbe también los votos aún no propagados a nivel de provincia
        # (lag de API), calculándose como complemento hasta v_real_nac/v_proy_total.
        # Así %ACUM llega exactamente a 100% y el TOTAL cuadra con el encabezado.
        gan_total_cand = ganancia if ganancia != 0 else 1

        print(f"  {'UNIDAD (Dep / Provincia  o  Continente/País)':<46} {'AVANCE':>7} {'TOTAL':>7} {'CONT':>7} {'JEE':>6} {'PEND':>6} {'REALES':>12} {'PROYECTADOS':>13} {'GANANCIA':>10} {'%GAN':>6} {'%ACUM':>7}")
        print(f"  {'-'*133}")

        acum = 0.0
        suma_top_real = 0; suma_top_proy = 0
        for (dep, prov), (vr, vp) in unid_sorted[:TOP_N_UNIDS]:
            label  = f"{dep.split('/')[1]} / {prov}" if ES_EXT(dep) else f"{dep} / {prov}"
            pct_av, a_cont, a_jee, a_pend, a_tot = actas_unidad.get((dep, prov), (None, 0, 0, 0, 0))
            avance_str = f"{pct_av:.1f}%" if pct_av is not None else "?"
            gan_u   = vp - vr
            pct_gan = gan_u / gan_total_cand * 100
            acum   += pct_gan
            print(f"  {label:<46} {avance_str:>7} {a_tot:>7,} {a_cont:>7,} {a_jee:>6,} {a_pend:>6,} {vr:>12,} {vp:>13,} {gan_u:>10,} {pct_gan:>5.1f}% {acum:>6.1f}%")
            suma_top_real += vr; suma_top_proy += vp

        # OTROS: complemento hasta v_real_nac/v_proy_total — absorbe gap de API
        otros_r = v_real_nac - suma_top_real
        otros_p = v_proy_total - suma_top_proy
        n_otros = len(unid_sorted) - TOP_N_UNIDS
        gan_otros = otros_p - otros_r
        pct_gan_o = gan_otros / gan_total_cand * 100
        if n_otros > 0 or otros_r != 0 or otros_p != 0:
            acum += pct_gan_o
            print(f"  {'OTROS (' + str(n_otros) + ' unidades)':<46} {'':>7} {'':>7} {'':>7} {'':>6} {'':>6} {otros_r:>12,} {otros_p:>13,} {gan_otros:>10,} {pct_gan_o:>5.1f}% {acum:>6.1f}%")

        n_unids = len(unid_sorted)
        print(f"  {'-'*133}")
        print(f"  {'TOTAL (' + str(n_unids) + ' prov/países):':<46} {'':>7} {'':>7} {'':>7} {'':>6} {'':>6} {v_real_nac:>12,} {v_proy_total:>13,} {ganancia:>10,} {'100.0%':>6} {'100.0%':>7}")

    print(f"\n{'='*col_d}")

    # ─────────────────────────────────────────────────────────────────────────
    # ── Unidades con 0% de avance ──
    # ─────────────────────────────────────────────────────────────────────────
    cero_peru = []
    cero_ext  = []
    for (dep, prov), (pct_av, a_cont, a_jee, a_pend, a_tot) in actas_unidad.items():
        if prov in ("SIN PAÍS IDENTIFICADO", "SIN CONTINENTE IDENTIFICADO"):
            continue
        if (pct_av is None or pct_av == 0) and a_tot > 0:
            if ES_EXT(dep):
                cero_ext.append((dep.split("/")[1], prov, a_tot))
            else:
                cero_peru.append((dep, prov, a_tot))

    if cero_peru or cero_ext:
        total_cero = sum(ta for *_, ta in cero_peru) + sum(ta for *_, ta in cero_ext)
        print(f"\n{'='*80}")
        print(f"  UNIDADES CON 0% DE AVANCE ({len(cero_peru)} provincias + {len(cero_ext)} países, {total_cero:,} actas pendientes)")
        print(f"{'='*80}")

    if cero_peru:
        cero_peru.sort(key=lambda x: x[2], reverse=True)
        print(f"\n  PERU — {len(cero_peru)} provincias")
        print(f"  {'DEPARTAMENTO':<22} {'PROVINCIA':<26} {'ACTAS':>6}")
        print(f"  {'-'*56}")
        for dep, prov, ta in cero_peru:
            print(f"  {dep:<22} {prov:<26} {ta:>6,}")
        print(f"  {'-'*56}")
        print(f"  {'TOTAL PERU':<48} {sum(x[2] for x in cero_peru):>6,}")

    if cero_ext:
        cero_ext.sort(key=lambda x: x[2], reverse=True)
        print(f"\n  EXTRANJERO — {len(cero_ext)} países")
        print(f"  {'CONTINENTE':<22} {'PAÍS':<30} {'ACTAS':>6}")
        print(f"  {'-'*60}")
        for cont, pais, ta in cero_ext:
            print(f"  {cont:<22} {pais:<30} {ta:>6,}")
        print(f"  {'-'*60}")
        print(f"  {'TOTAL EXTRANJERO':<52} {sum(x[2] for x in cero_ext):>6,}")

    print(f"\nArchivos generados:")
    print(f"  {csv_path}  ({len(filas)} filas)")
    print(f"  onpe_prov_proyeccion_LATEST.csv")
    print(f"  onpe_prov_raw_{ts_file}.json")

if __name__ == "__main__":
    main()
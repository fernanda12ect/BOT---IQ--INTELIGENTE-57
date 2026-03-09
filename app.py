import streamlit as st
import pandas as pd
import html
import time
from datetime import datetime, timedelta
import pytz
from bot import (
    obtener_activos_abiertos,
    calcular_indicadores,
    evaluar_activo
)
from iqoptionapi.stable_api import IQ_Option

st.set_page_config(layout="wide")
st.title("🤖 IQ OPTION PRO - 5 ESTRATEGIAS INTELIGENTES")

# Inicializar session_state
if 'api' not in st.session_state:
    st.session_state.api = None
if 'activos_reales' not in st.session_state:
    st.session_state.activos_reales = []
if 'activos_otc' not in st.session_state:
    st.session_state.activos_otc = []
if 'escaneando' not in st.session_state:
    st.session_state.escaneando = False
if 'fase' not in st.session_state:
    st.session_state.fase = "seleccion"
if 'activos_seguimiento' not in st.session_state:
    st.session_state.activos_seguimiento = []  # Lista de activos en seguimiento (máx 6)
if 'señales_activas' not in st.session_state:
    st.session_state.señales_activas = []  # Señales confirmadas listas para operar
if 'historial' not in st.session_state:
    st.session_state.historial = []

# Zona horaria Ecuador
ecuador = pytz.timezone("America/Guayaquil")

# Sidebar
with st.sidebar:
    st.header("⚙️ Configuración")
    email = st.text_input("📧 Email")
    password = st.text_input("🔑 Password", type="password")

    # Umbral de fuerza mínima
    umbral_fuerza = st.slider("🎯 Fuerza mínima de señal", 0, 100, 40, 5)

    # Número de activos a seguir
    NUM_ACTIVOS = 6

    # Tiempo de espera entre rondas
    pausa_entre_rondas = st.number_input("⏱️ Pausa entre rondas (seg)", 5, 120, 10)

    col1, col2 = st.columns(2)
    with col1:
        conectar = st.button("🔌 Conectar")
    with col2:
        desconectar = st.button("⛔ Desconectar")

# Lógica de conexión
if conectar:
    if not email or not password:
        st.error("❌ Ingresa email y password")
    else:
        try:
            API = IQ_Option(email, password)
            check, reason = API.connect()
            if check:
                st.session_state.api = API
                real, otc = obtener_activos_abiertos(API)
                st.session_state.activos_reales = real
                st.session_state.activos_otc = otc
                st.session_state.escaneando = True
                st.session_state.fase = "seleccion"
                st.session_state.activos_seguimiento = []
                st.session_state.señales_activas = []
                st.session_state.historial = []
                st.success("✅ Conectado - Iniciando búsqueda...")
                st.rerun()
            else:
                st.error(f"❌ Error de conexión: {reason}")
        except Exception as e:
            st.error(f"Error inesperado: {e}")

if desconectar:
    st.session_state.api = None
    st.session_state.escaneando = False
    st.session_state.activos_seguimiento = []
    st.session_state.señales_activas = []
    st.success("Desconectado")
    st.rerun()

# Área principal
if st.session_state.api is not None:
    real_count = len(st.session_state.activos_reales)
    otc_count = len(st.session_state.activos_otc)
    if real_count > 0:
        st.success(f"🌍 REAL: {real_count} | 📱 OTC: {otc_count}")
    else:
        st.warning(f"⚠️ Solo OTC ({otc_count})")

    # SECCIÓN 1: ACTIVOS EN SEGUIMIENTO (plegable)
    with st.expander("📋 ACTIVOS EN SEGUIMIENTO", expanded=False):
        if st.session_state.activos_seguimiento:
            # Crear una tabla con los datos
            data = []
            for activo in st.session_state.activos_seguimiento:
                data.append({
                    "Activo": activo['asset'],
                    "Estrategia": activo['estrategia'],
                    "Dirección": activo['direccion'],
                    "Fuerza": f"{activo['fuerza']:.1f}%",
                    "Precio actual": f"{activo.get('precio_actual', 0):.5f}",
                    "Nivel clave": f"{activo.get('nivel_clave', 0):.5f}"
                })
            df = pd.DataFrame(data)
            st.dataframe(df, use_container_width=True)
        else:
            st.info("No hay activos en seguimiento.")

    # SECCIÓN 2: SEÑALES LISTAS PARA OPERAR (plegable)
    with st.expander("🎯 SEÑALES LISTAS PARA OPERAR", expanded=False):
        if st.session_state.señales_activas:
            # Mostrar en cuadrícula de 2 columnas
            cols = st.columns(2)
            for idx, senal in enumerate(st.session_state.señales_activas):
                with cols[idx % 2]:
                    asset = senal['asset']
                    if "-OTC" in asset:
                        tipo = "📱 OTC"
                        asset_clean = asset.replace("-OTC", "")
                    else:
                        tipo = "🌍 REAL"
                        asset_clean = asset
                    color = "#006400" if senal['direccion'] == "CALL" else "#8B0000"
                    # Tarjeta cuadrada con información mínima
                    html_code = f"""
                    <div style="background:#111; padding:15px; border-radius:15px; border:3px solid {color}; margin-bottom:10px; width:100%;">
                        <h3 style="margin:0;">{asset_clean} {tipo}</h3>
                        <p style="color:{color}; font-size:2rem; margin:5px 0;">{senal['direccion']}</p>
                        <p><strong>Entrada:</strong> {senal['entry']}</p>
                        <p><strong>Expira:</strong> {senal['expiry']}</p>
                        <p style="color:#0f0;">✅ LISTO PARA OPERAR</p>
                    </div>
                    """
                    st.markdown(html_code, unsafe_allow_html=True)
        else:
            st.info("No hay señales listas.")

    # SECCIÓN 3: HISTORIAL DE EVENTOS (plegable)
    with st.expander("📜 HISTORIAL DE EVENTOS", expanded=False):
        if st.session_state.historial:
            for linea in st.session_state.historial[-30:]:
                st.text(linea)
        else:
            st.info("No hay eventos registrados.")

    # Lógica de escaneo continuo
    if st.session_state.escaneando:
        # FASE DE SELECCIÓN
        if st.session_state.fase == "seleccion":
            st.info("🔍 Buscando activos con señales potenciales...")
            todos_activos = st.session_state.activos_reales + st.session_state.activos_otc
            if not todos_activos:
                st.warning(f"No hay activos disponibles. Reintentando en {pausa_entre_rondas} seg...")
                time.sleep(pausa_entre_rondas)
                real, otc = obtener_activos_abiertos(st.session_state.api)
                st.session_state.activos_reales = real
                st.session_state.activos_otc = otc
                st.rerun()

            candidatos = []
            for asset in todos_activos:
                try:
                    candles = st.session_state.api.get_candles(asset, 60, 100, time.time())
                    if not candles or len(candles) < 50:
                        continue
                    df = pd.DataFrame(candles)
                    for col in ['open', 'max', 'min', 'close', 'volume']:
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                    df.dropna(inplace=True)
                    if len(df) < 50:
                        continue
                    indicators = calcular_indicadores(df)
                    res = evaluar_activo(indicators, umbral_fuerza)
                    if res:
                        direccion, fuerza, estrategia, nivel_clave = res
                        candidatos.append({
                            'asset': asset,
                            'direccion': direccion,
                            'fuerza': fuerza,
                            'estrategia': estrategia,
                            'nivel_clave': nivel_clave,
                            'precio_actual': indicators['close'],
                            'indicators': indicators
                        })
                except Exception as e:
                    st.session_state.historial.append(f"⚠️ Error con {asset}: {str(e)[:50]}")
                    continue
                time.sleep(0.1)

            if candidatos:
                candidatos.sort(key=lambda x: x['fuerza'], reverse=True)
                st.session_state.activos_seguimiento = candidatos[:NUM_ACTIVOS]
                st.session_state.fase = "seguimiento"
                st.session_state.historial.append(f"✅ Seleccionados {len(st.session_state.activos_seguimiento)} activos:")
                for a in st.session_state.activos_seguimiento:
                    st.session_state.historial.append(f"   - {a['asset']} ({a['direccion']}, {a['fuerza']:.1f}%) - {a['estrategia']}")
                time.sleep(2)
                st.rerun()
            else:
                st.session_state.historial.append("⚠️ No se encontraron activos con señales. Reintentando...")
                time.sleep(pausa_entre_rondas)
                st.rerun()

        # FASE DE SEGUIMIENTO
        elif st.session_state.fase == "seguimiento":
            st.info("🔄 Monitoreando activos...")
            nuevos_seguimiento = []
            activos_a_remover = []

            for activo in st.session_state.activos_seguimiento:
                asset = activo['asset']
                try:
                    # Obtener velas recientes para precio actual
                    candles = st.session_state.api.get_candles(asset, 60, 5, time.time())
                    if not candles:
                        continue
                    df = pd.DataFrame(candles)
                    precio_actual = df['close'].iloc[-1]
                    activo['precio_actual'] = precio_actual

                    # Verificar si se alcanzó el nivel clave (con tolerancia)
                    nivel = activo['nivel_clave']
                    if nivel is not None and not pd.isna(nivel):
                        if activo['direccion'] == "CALL" and precio_actual <= nivel * 1.001:
                            # Señal de compra
                            generar_senal(activo, st.session_state, ecuador)
                            activos_a_remover.append(activo)
                            continue
                        elif activo['direccion'] == "PUT" and precio_actual >= nivel * 0.999:
                            generar_senal(activo, st.session_state, ecuador)
                            activos_a_remover.append(activo)
                            continue

                    # Si no alcanzó el nivel, reevaluar con más velas para ver si sigue siendo confiable
                    candles_full = st.session_state.api.get_candles(asset, 60, 100, time.time())
                    if not candles_full or len(candles_full) < 50:
                        activos_a_remover.append(activo)
                        continue
                    df_full = pd.DataFrame(candles_full)
                    for col in ['open', 'max', 'min', 'close', 'volume']:
                        df_full[col] = pd.to_numeric(df_full[col], errors='coerce')
                    df_full.dropna(inplace=True)
                    if len(df_full) < 50:
                        activos_a_remover.append(activo)
                        continue
                    indicators = calcular_indicadores(df_full)
                    res = evaluar_activo(indicators, umbral_fuerza)
                    if res:
                        direccion, fuerza, estrategia, nivel_clave = res
                        # Actualizar datos
                        activo['fuerza'] = fuerza
                        activo['estrategia'] = estrategia
                        activo['nivel_clave'] = nivel_clave
                        activo['precio_actual'] = indicators['close']
                        nuevos_seguimiento.append(activo)
                    else:
                        activos_a_remover.append(activo)
                        st.session_state.historial.append(f"❌ Activo {asset} perdió confianza")
                except Exception as e:
                    st.session_state.historial.append(f"⚠️ Error monitoreando {asset}: {str(e)[:50]}")
                    activos_a_remover.append(activo)

            # Eliminar los que ya no son válidos o dieron señal
            for a in activos_a_remover:
                if a in st.session_state.activos_seguimiento:
                    st.session_state.activos_seguimiento.remove(a)

            # Si hay espacios, volver a selección para buscar reemplazos
            if len(st.session_state.activos_seguimiento) < NUM_ACTIVOS:
                st.session_state.fase = "seleccion"
                st.rerun()
            else:
                time.sleep(pausa_entre_rondas)
                st.rerun()

else:
    st.warning("🔒 Conéctate primero desde el panel izquierdo.")

# Función auxiliar para generar señal
def generar_senal(activo, session, ecuador):
    try:
        server_time = session.api.get_server_time()
        now_utc = datetime.fromtimestamp(server_time, tz=pytz.UTC)
    except:
        now_utc = datetime.now(pytz.UTC)
    entry_dt = now_utc + timedelta(minutes=1)
    entry_dt = entry_dt.replace(second=0, microsecond=0)
    expiry_dt = entry_dt + timedelta(minutes=5)
    entry_local = entry_dt.astimezone(ecuador)
    expiry_local = expiry_dt.astimezone(ecuador)

    señal = {
        'asset': activo['asset'],
        'direccion': activo['direccion'],
        'entry': entry_local.strftime("%H:%M:%S"),
        'expiry': expiry_local.strftime("%H:%M:%S"),
        'estrategia': activo['estrategia'],
        'fuerza': activo['fuerza']
    }
    session.señales_activas.append(señal)
    session.historial.append(f"🎯 Señal {activo['direccion']} para {activo['asset']} a las {entry_local.strftime('%H:%M:%S')} ({activo['estrategia']})")

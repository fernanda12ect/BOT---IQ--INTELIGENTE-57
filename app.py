import streamlit as st
import pandas as pd
import html
import time
from datetime import datetime, timedelta
import pytz
from bot import (
    obtener_activos_abiertos,
    calcular_indicadores,
    evaluar_activo,
    verificar_punto_entrada
)
from iqoptionapi.stable_api import IQ_Option

st.set_page_config(layout="wide")
st.title("🤖 IQ OPTION PRO - 3 ACTIVOS DE ALTA PRECISIÓN")

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
    st.session_state.activos_seguimiento = []  # Máx 3 activos
if 'señales_activas' not in st.session_state:
    st.session_state.señales_activas = []
if 'historial' not in st.session_state:
    st.session_state.historial = []

# Zona horaria Ecuador
ecuador = pytz.timezone("America/Guayaquil")

def generar_senal(activo, nivel_alcanzado):
    try:
        server_time = st.session_state.api.get_server_time()
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
        'estrategia': f"Retroceso {nivel_alcanzado}",
        'fuerza': activo['fuerza']
    }
    st.session_state.señales_activas.append(señal)
    st.session_state.historial.append(f"🎯 Señal {activo['direccion']} para {activo['asset']} a las {entry_local.strftime('%H:%M:%S')} (nivel {nivel_alcanzado})")

# Sidebar
with st.sidebar:
    st.header("⚙️ Configuración")
    email = st.text_input("📧 Email")
    password = st.text_input("🔑 Password", type="password")

    umbral_fuerza = st.slider("🎯 Fuerza mínima de tendencia", 0, 100, 40, 5)
    NUM_ACTIVOS = 3
    pausa_entre_rondas = st.number_input("⏱️ Pausa entre rondas (seg)", 5, 120, 10)

    col1, col2 = st.columns(2)
    with col1:
        conectar = st.button("🔌 Conectar")
    with col2:
        desconectar = st.button("⛔ Desconectar")

    if st.button("🔄 Reiniciar estado"):
        st.session_state.escaneando = False
        st.session_state.activos_seguimiento = []
        st.session_state.señales_activas = []
        st.session_state.historial = []
        st.rerun()

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
                st.success("✅ Conectado")
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

    # Sección 1: Activos en seguimiento
    with st.expander("📌 ACTIVOS EN SEGUIMIENTO", expanded=True):
        if st.session_state.activos_seguimiento:
            data = []
            for a in st.session_state.activos_seguimiento:
                niveles = a.get('niveles_fib', {})
                data.append({
                    "Activo": a['asset'],
                    "Dirección": a['direccion'],
                    "Fuerza": f"{a['fuerza']:.1f}%",
                    "Precio": f"{a.get('precio_actual', 0):.5f}",
                    "23.6%": f"{niveles.get('236', 0):.5f}",
                    "38.2%": f"{niveles.get('382', 0):.5f}",
                    "50%": f"{niveles.get('500', 0):.5f}",
                    "61.8%": f"{niveles.get('618', 0):.5f}"
                })
            df = pd.DataFrame(data)
            st.dataframe(df, use_container_width=True)
        else:
            st.info("No hay activos en seguimiento.")

    # Sección 2: Señales listas
    with st.expander("🚀 SEÑALES LISTAS PARA OPERAR", expanded=True):
        if st.session_state.señales_activas:
            cols = st.columns(2)
            for idx, s in enumerate(st.session_state.señales_activas):
                with cols[idx % 2]:
                    asset = s['asset']
                    if "-OTC" in asset:
                        tipo = "📱 OTC"
                        asset_clean = asset.replace("-OTC", "")
                    else:
                        tipo = "🌍 REAL"
                        asset_clean = asset
                    color = "#006400" if s['direccion'] == "CALL" else "#8B0000"
                    html_code = f"""
                    <div style="background:#111; padding:20px; border-radius:15px; border:3px solid {color}; margin-bottom:10px;">
                        <h3>{asset_clean} {tipo}</h3>
                        <p style="color:{color}; font-size:2rem;">{s['direccion']}</p>
                        <p><strong>Estrategia:</strong> {s['estrategia']}</p>
                        <p><strong>Fuerza:</strong> {s['fuerza']:.1f}%</p>
                        <p><strong>Entrada:</strong> {s['entry']}</p>
                        <p><strong>Expira:</strong> {s['expiry']}</p>
                        <p style="color:#0f0;">✅ LISTO PARA OPERAR</p>
                    </div>
                    """
                    st.markdown(html_code, unsafe_allow_html=True)
        else:
            st.info("No hay señales listas.")

    # Sección 3: Historial
    with st.expander("📋 HISTORIAL DE EVENTOS", expanded=False):
        if st.session_state.historial:
            for linea in st.session_state.historial[-30:]:
                st.text(linea)
        else:
            st.info("No hay eventos registrados.")

    # Lógica de escaneo continuo
    if st.session_state.escaneando:
        try:
            if st.session_state.fase == "seleccion":
                st.info("🔍 Buscando activos con tendencia...")
                todos = st.session_state.activos_reales + st.session_state.activos_otc
                if not todos:
                    st.warning("No hay activos disponibles. Reintentando...")
                    time.sleep(pausa_entre_rondas)
                    real, otc = obtener_activos_abiertos(st.session_state.api)
                    st.session_state.activos_reales = real
                    st.session_state.activos_otc = otc
                    st.rerun()

                candidatos = []
                for asset in todos:
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
                        ind = calcular_indicadores(df)
                        res = evaluar_activo(ind, umbral_fuerza)
                        if res:
                            direccion, fuerza, niveles = res
                            candidatos.append({
                                'asset': asset,
                                'direccion': direccion,
                                'fuerza': fuerza,
                                'niveles_fib': niveles,
                                'precio_actual': ind['close']
                            })
                    except Exception as e:
                        st.session_state.historial.append(f"⚠️ Error con {asset}: {str(e)[:50]}")
                    time.sleep(0.1)

                if candidatos:
                    candidatos.sort(key=lambda x: x['fuerza'], reverse=True)
                    st.session_state.activos_seguimiento = candidatos[:NUM_ACTIVOS]
                    st.session_state.fase = "seguimiento"
                    st.session_state.historial.append(f"✅ Seleccionados {len(st.session_state.activos_seguimiento)} activos:")
                    for a in st.session_state.activos_seguimiento:
                        st.session_state.historial.append(f"   - {a['asset']} ({a['direccion']}, {a['fuerza']:.1f}%)")
                    time.sleep(2)
                    st.rerun()
                else:
                    st.session_state.historial.append("⚠️ No se encontraron activos. Reintentando...")
                    time.sleep(pausa_entre_rondas)
                    st.rerun()

            elif st.session_state.fase == "seguimiento":
                st.info("🔄 Monitoreando activos...")
                nuevos = []
                remover = []
                for activo in st.session_state.activos_seguimiento:
                    try:
                        candles = st.session_state.api.get_candles(activo['asset'], 60, 5, time.time())
                        if not candles:
                            continue
                        df = pd.DataFrame(candles)
                        precio = df['close'].iloc[-1]
                        activo['precio_actual'] = precio

                        alcanzado, nivel = verificar_punto_entrada(activo, precio)
                        if alcanzado:
                            generar_senal(activo, nivel)
                            remover.append(activo)
                            continue

                        # Reevaluar
                        candles_full = st.session_state.api.get_candles(activo['asset'], 60, 100, time.time())
                        if not candles_full or len(candles_full) < 50:
                            remover.append(activo)
                            continue
                        df_full = pd.DataFrame(candles_full)
                        for col in ['open', 'max', 'min', 'close', 'volume']:
                            df_full[col] = pd.to_numeric(df_full[col], errors='coerce')
                        df_full.dropna(inplace=True)
                        if len(df_full) < 50:
                            remover.append(activo)
                            continue
                        ind = calcular_indicadores(df_full)
                        res = evaluar_activo(ind, umbral_fuerza)
                        if res:
                            direccion, fuerza, niveles = res
                            activo['direccion'] = direccion
                            activo['fuerza'] = fuerza
                            activo['niveles_fib'] = niveles
                            activo['precio_actual'] = ind['close']
                            nuevos.append(activo)
                        else:
                            remover.append(activo)
                            st.session_state.historial.append(f"❌ Activo {activo['asset']} perdió calidad")
                    except Exception as e:
                        st.session_state.historial.append(f"⚠️ Error monitoreando {activo['asset']}: {str(e)[:50]}")
                        remover.append(activo)

                for r in remover:
                    if r in st.session_state.activos_seguimiento:
                        st.session_state.activos_seguimiento.remove(r)

                if len(st.session_state.activos_seguimiento) < NUM_ACTIVOS:
                    st.session_state.fase = "seleccion"
                    st.rerun()
                else:
                    time.sleep(pausa_entre_rondas)
                    st.rerun()
        except Exception as e:
            st.session_state.historial.append(f"🔥 Error crítico: {str(e)}")
            time.sleep(pausa_entre_rondas)
            st.rerun()
else:
    st.warning("🔒 Conéctate primero desde el panel izquierdo.")

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
st.title("🤖 BOT OTC - ESTRATEGIA EFECTIVA (SIN LÍMITE)")

# Inicializar session_state
if 'api' not in st.session_state:
    st.session_state.api = None
if 'activos_otc' not in st.session_state:
    st.session_state.activos_otc = []
if 'escaneando' not in st.session_state:
    st.session_state.escaneando = False
if 'fase' not in st.session_state:
    st.session_state.fase = "seleccion"
if 'activos_seguimiento' not in st.session_state:
    st.session_state.activos_seguimiento = []
if 'alertas_anticipadas' not in st.session_state:
    st.session_state.alertas_anticipadas = []
if 'señales_activas' not in st.session_state:
    st.session_state.señales_activas = []
if 'historial' not in st.session_state:
    st.session_state.historial = []

# Zona horaria Ecuador
ecuador = pytz.timezone("America/Guayaquil")

def generar_señal(activo, tipo_nivel, direccion, confirmacion=""):
    try:
        server_time = st.session_state.api.get_server_time()
        now_utc = datetime.fromtimestamp(server_time, tz=pytz.UTC)
    except:
        now_utc = datetime.now(pytz.UTC)
    entry_dt = now_utc + timedelta(minutes=1)
    entry_dt = entry_dt.replace(second=0, microsecond=0)
    expiry_dt = entry_dt + timedelta(minutes=1)
    entry_local = entry_dt.astimezone(ecuador)
    expiry_local = expiry_dt.astimezone(ecuador)

    nueva_señal = {
        'asset': activo['asset'],
        'direccion': direccion,
        'entry': entry_local.strftime("%H:%M:%S"),
        'expiry': expiry_local.strftime("%H:%M:%S"),
        'tipo_nivel': tipo_nivel,
        'confirmacion': confirmacion,
        'fuerza': activo.get('fuerza', 50),
        'timestamp': datetime.now(ecuador)
    }

    st.session_state.señales_activas = [s for s in st.session_state.señales_activas if s['asset'] != activo['asset']]
    st.session_state.señales_activas.append(nueva_señal)
    st.session_state.señales_activas.sort(key=lambda x: x['timestamp'], reverse=True)
    st.session_state.señales_activas = st.session_state.señales_activas[:20]
    st.session_state.historial.append(f"🎯 SEÑAL: {activo['asset']} - {direccion} a las {entry_local.strftime('%H:%M:%S')} ({tipo_nivel})")

# Sidebar
with st.sidebar:
    st.header("⚙️ Configuración")
    email = st.text_input("📧 Email")
    password = st.text_input("🔑 Password", type="password")

    umbral_estabilidad = st.slider("📊 Estabilidad máxima (%)", 1.0, 5.0, 2.5, 0.1) / 100
    umbral_cerca = st.slider("🔍 Alerta anticipada (%)", 0.1, 2.0, 0.5, 0.1) / 100
    fuerza_minima = st.slider("💪 Fuerza mínima", 0, 100, 30, 5)
    pausa_entre_rondas = st.number_input("⏱️ Pausa (seg)", 5, 60, 10)

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
                st.session_state.activos_otc = otc
                st.session_state.escaneando = True
                st.session_state.fase = "seleccion"
                st.session_state.activos_seguimiento = []
                st.session_state.alertas_anticipadas = []
                st.session_state.señales_activas = []
                st.session_state.historial = []
                st.success("✅ Conectado")
                st.rerun()
            else:
                st.error(f"❌ Error de conexión: {reason}")
        except Exception as e:
            st.error(f"Error: {e}")

if desconectar:
    st.session_state.api = None
    st.session_state.escaneando = False
    st.session_state.activos_seguimiento = []
    st.session_state.alertas_anticipadas = []
    st.session_state.señales_activas = []
    st.success("Desconectado")
    st.rerun()

# Área principal
if st.session_state.api is not None:
    st.success(f"📱 OTC disponibles: {len(st.session_state.activos_otc)}")

    with st.expander("📌 ACTIVOS EN SEGUIMIENTO", expanded=True):
        if st.session_state.activos_seguimiento:
            data = []
            for a in st.session_state.activos_seguimiento:
                data.append({
                    "Activo": a['asset'],
                    "Nivel": a['tipo'],
                    "Dir": a['direccion'],
                    "Precio nivel": f"{a['nivel']:.5f}",
                    "Precio actual": f"{a.get('precio_actual', 0):.5f}",
                    "Fuerza": f"{a['fuerza']:.0f}%"
                })
            df = pd.DataFrame(data)
            st.dataframe(df, width='stretch')
        else:
            st.info("No hay activos en seguimiento.")

    with st.expander("🔔 ALERTAS", expanded=True):
        if st.session_state.alertas_anticipadas:
            for alerta in st.session_state.alertas_anticipadas[-10:]:
                st.warning(alerta)
        else:
            st.info("No hay alertas.")

    with st.expander("🚀 SEÑALES (1 MIN ANTES)", expanded=True):
        if st.session_state.señales_activas:
            cols = st.columns(2)
            for idx, senal in enumerate(st.session_state.señales_activas):
                with cols[idx % 2]:
                    asset = senal['asset'].replace("-OTC", "")
                    color = "#006400" if senal['direccion'] == "CALL" else "#8B0000"
                    html_code = f"""
                    <div style="background:#111; padding:15px; border-radius:10px; border:3px solid {color}; margin-bottom:10px;">
                        <h4>{asset} 📱</h4>
                        <p style="color:{color}; font-size:1.8rem;">{senal['direccion']}</p>
                        <p><strong>Entrada:</strong> {senal['entry']}</p>
                        <p><strong>Expira:</strong> {senal['expiry']}</p>
                        <p><strong>Conf:</strong> {senal.get('confirmacion', '')}</p>
                        <p style="color:#0f0;">✅ LISTO</p>
                    </div>
                    """
                    st.markdown(html_code, unsafe_allow_html=True)
        else:
            st.info("No hay señales aún.")

    with st.expander("📋 HISTORIAL", expanded=False):
        if st.session_state.historial:
            for linea in st.session_state.historial[-40:]:
                st.text(linea)
        else:
            st.info("Sin eventos.")

    # Lógica de escaneo continuo
    if st.session_state.escaneando:
        if st.session_state.fase == "seleccion":
            st.info("🔍 Escaneando activos...")
            todos = st.session_state.activos_otc
            if not todos:
                time.sleep(pausa_entre_rondas)
                _, otc = obtener_activos_abiertos(st.session_state.api)
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
                    indicators = calcular_indicadores(df)
                    res = evaluar_activo(indicators, umbral_estabilidad)
                    if res and res['fuerza'] >= fuerza_minima:
                        candidatos.append({
                            'asset': asset,
                            'tipo': res['tipo'],
                            'direccion': res['direccion'],
                            'nivel': res['nivel'],
                            'fuerza': res['fuerza'],
                            'descripcion': res['descripcion'],
                            'precio_actual': indicators['close'],
                            'indicators': indicators
                        })
                except Exception as e:
                    continue  # No llenar historial de errores
                time.sleep(0.2)

            if candidatos:
                candidatos.sort(key=lambda x: x['fuerza'], reverse=True)
                st.session_state.activos_seguimiento = candidatos
                st.session_state.fase = "seguimiento"
                st.session_state.historial.append(f"✅ Seleccionados {len(candidatos)} activos")
                time.sleep(2)
                st.rerun()
            else:
                st.session_state.historial.append("⚠️ Sin activos. Reintentando...")
                time.sleep(pausa_entre_rondas)
                st.rerun()

        elif st.session_state.fase == "seguimiento":
            st.info("🔄 Monitoreando...")
            nuevos = []
            remover = []

            for activo in st.session_state.activos_seguimiento:
                asset = activo['asset']
                try:
                    candles = st.session_state.api.get_candles(asset, 60, 5, time.time())
                    if not candles:
                        continue
                    df_recent = pd.DataFrame(candles)
                    precio_actual = df_recent['close'].iloc[-1]
                    activo['precio_actual'] = precio_actual

                    nivel = activo['nivel']
                    distancia = abs(precio_actual - nivel) / nivel if nivel else 1

                    if distancia < umbral_cerca:
                        alerta = f"🔔 {asset} cerca de {activo['tipo']} ({distancia*100:.2f}%)"
                        if alerta not in st.session_state.alertas_anticipadas:
                            st.session_state.alertas_anticipadas.append(alerta)
                            st.session_state.historial.append(alerta)

                    candles_full = st.session_state.api.get_candles(asset, 60, 100, time.time())
                    if not candles_full or len(candles_full) < 50:
                        continue
                    df_full = pd.DataFrame(candles_full)
                    for col in ['open', 'max', 'min', 'close', 'volume']:
                        df_full[col] = pd.to_numeric(df_full[col], errors='coerce')
                    df_full.dropna(inplace=True)
                    if len(df_full) < 50:
                        continue
                    indicators = calcular_indicadores(df_full)

                    toca = abs(precio_actual - nivel) / nivel < 0.001

                    if toca and indicators['cruce_ema'] and indicators['direccion_cruce'] == activo['direccion']:
                        generar_señal(activo, activo['tipo'], activo['direccion'], "EMA cruzada")
                        remover.append(activo)
                        continue

                    res = evaluar_activo(indicators, umbral_estabilidad)
                    if res and res['fuerza'] >= fuerza_minima:
                        activo['nivel'] = res['nivel']
                        activo['fuerza'] = res['fuerza']
                        nuevos.append(activo)
                    else:
                        remover.append(activo)
                        st.session_state.historial.append(f"❌ {asset} dejó de cumplir")
                except Exception as e:
                    remover.append(activo)

            for a in remover:
                if a in st.session_state.activos_seguimiento:
                    st.session_state.activos_seguimiento.remove(a)

            if len(st.session_state.activos_seguimiento) == 0:
                st.session_state.fase = "seleccion"
                st.rerun()
            else:
                time.sleep(pausa_entre_rondas)
                st.rerun()

else:
    st.warning("🔒 Conéctate primero.")

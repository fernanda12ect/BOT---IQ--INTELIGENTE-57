import streamlit as st
import pandas as pd
import html
import time
from datetime import datetime, timedelta
import pytz
from bot import (
    obtener_activos_abiertos,
    calcular_indicadores,
    calcular_probabilidad,
    REAL_ASSETS,
    OTC_ASSETS
)
from iqoptionapi.stable_api import IQ_Option

# ==================== MONKEY PATCH ====================
# Evita el KeyError 'underlying' en el hilo de opciones digitales
original_get_digital_open = IQ_Option._IQ_Option__get_digital_open

def safe_get_digital_open(self):
    try:
        return original_get_digital_open(self)
    except KeyError as e:
        # Ignorar silenciosamente el error de clave
        pass

IQ_Option._IQ_Option__get_digital_open = safe_get_digital_open
# =======================================================

st.set_page_config(layout="wide")
st.title("🤖 IQ OPTION PRO SIGNAL BOT - ESCANEO AUTOMÁTICO AL CONECTAR")

# Inicializar session_state
if 'api' not in st.session_state:
    st.session_state.api = None
if 'activos_reales' not in st.session_state:
    st.session_state.activos_reales = []
if 'activos_otc' not in st.session_state:
    st.session_state.activos_otc = []
if 'ultima_senal' not in st.session_state:
    st.session_state.ultima_senal = None
if 'cooldown_until' not in st.session_state:
    st.session_state.cooldown_until = None
if 'escaneando' not in st.session_state:
    st.session_state.escaneando = False
if 'indice_activo' not in st.session_state:
    st.session_state.indice_activo = 0
if 'activos_a_escanear' not in st.session_state:
    st.session_state.activos_a_escanear = []
if 'historial' not in st.session_state:
    st.session_state.historial = []

# Zona horaria Ecuador
ecuador = pytz.timezone("America/Guayaquil")

# Sidebar
with st.sidebar:
    st.header("⚙️ Configuración")
    email = st.text_input("📧 Email")
    password = st.text_input("🔑 Password", type="password")

    # Umbral de probabilidad (por defecto 75)
    umbral = st.slider("🎯 Umbral de probabilidad mínima (%)", 50, 95, 75, 5)

    # Tiempo de espera entre rondas completas (segundos)
    pausa_entre_rondas = st.number_input("⏱️ Pausa entre rondas (seg)", min_value=5, max_value=120, value=20)

    col1, col2 = st.columns(2)
    with col1:
        conectar = st.button("🔌 Conectar")
    with col2:
        desconectar = st.button("⛔ Desconectar")

    # Botón para reiniciar escaneo manualmente (si está detenido)
    if st.session_state.api is not None and not st.session_state.escaneando:
        if st.button("▶️ Reiniciar escaneo"):
            real, otc = obtener_activos_abiertos(st.session_state.api)
            st.session_state.activos_reales = real
            st.session_state.activos_otc = otc
            st.session_state.activos_a_escanear = real + otc
            st.session_state.indice_activo = 0
            st.session_state.historial = []
            st.session_state.escaneando = True
            st.rerun()

# Lógica de conexión
if conectar:
    if not email or not password:
        st.error("❌ Por favor ingresa email y password")
    else:
        try:
            API = IQ_Option(email, password)
            check, reason = API.connect()
            if check:
                st.session_state.api = API
                st.session_state.ultima_senal = None
                st.session_state.cooldown_until = None

                # Obtener activos disponibles
                real, otc = obtener_activos_abiertos(API)
                st.session_state.activos_reales = real
                st.session_state.activos_otc = otc
                st.session_state.activos_a_escanear = real + otc
                st.session_state.indice_activo = 0
                st.session_state.historial = []
                # Iniciar escaneo automáticamente
                st.session_state.escaneando = True

                st.success("✅ Conectado a IQ Option - Escaneo automático iniciado")
                st.rerun()
            else:
                st.error(f"❌ Error de conexión: {reason}")
        except Exception as e:
            st.error(f"Error inesperado: {e}")

if desconectar:
    st.session_state.api = None
    st.session_state.activos_reales = []
    st.session_state.activos_otc = []
    st.session_state.ultima_senal = None
    st.session_state.cooldown_until = None
    st.session_state.escaneando = False
    st.session_state.indice_activo = 0
    st.session_state.activos_a_escanear = []
    st.session_state.historial = []
    st.success("Desconectado")
    st.rerun()

# Área principal
if st.session_state.api is not None:
    st.info("🔌 Conectado.")

    # Mostrar estado del mercado
    real_count = len(st.session_state.activos_reales)
    otc_count = len(st.session_state.activos_otc)
    if real_count > 0:
        st.success(f"🌍 Mercado REAL abierto: {real_count} activos | 📱 Mercado OTC abierto: {otc_count} activos")
    else:
        st.warning(f"⚠️ Mercado REAL cerrado - analizando solo activos OTC ({otc_count} disponibles)")

    # Mostrar historial en tiempo real
    if st.session_state.historial:
        with st.expander("📋 Historial de análisis", expanded=True):
            for linea in st.session_state.historial[-20:]:  # últimos 20
                st.text(linea)

    # Lógica de escaneo continuo 1x1
    if st.session_state.escaneando:
        now = datetime.now(ecuador)

        # Verificar cooldown
        if st.session_state.cooldown_until and now < st.session_state.cooldown_until:
            tiempo_restante = (st.session_state.cooldown_until - now).total_seconds()
            st.warning(f"⏳ Cooldown activo. Esperando {tiempo_restante:.0f} segundos...")
            time.sleep(1)
            st.rerun()
        else:
            # Si no hay activos cargados o se terminó la lista, cargar nueva ronda
            if not st.session_state.activos_a_escanear or st.session_state.indice_activo >= len(st.session_state.activos_a_escanear):
                # Obtener activos actualizados
                real, otc = obtener_activos_abiertos(st.session_state.api)
                st.session_state.activos_reales = real
                st.session_state.activos_otc = otc
                st.session_state.activos_a_escanear = real + otc
                st.session_state.indice_activo = 0
                st.session_state.historial.append(f"🔄 Nueva ronda: {len(st.session_state.activos_a_escanear)} activos a escanear")
                # Esperar pausa entre rondas
                if st.session_state.activos_a_escanear:
                    st.info(f"Esperando {pausa_entre_rondas} segundos para iniciar nueva ronda...")
                    time.sleep(pausa_entre_rondas)
                    st.rerun()
                else:
                    st.warning("No hay activos disponibles para escanear.")
                    st.session_state.escaneando = False
                    st.rerun()
            else:
                # Escanear el activo actual
                asset = st.session_state.activos_a_escanear[st.session_state.indice_activo]
                tipo = "🌍 REAL" if "-OTC" not in asset else "📱 OTC"
                st.markdown(f"### 🔍 Analizando: {tipo} {asset}")

                try:
                    # Añadir al historial
                    st.session_state.historial.append(f"{tipo} Analizando {asset}...")

                    candles = st.session_state.api.get_candles(asset, 60, 100, time.time())
                    if not candles or len(candles) < 50:
                        st.session_state.historial.append(f"⏭️ {asset}: datos insuficientes")
                        time.sleep(0.25)
                        st.session_state.indice_activo += 1
                        st.rerun()

                    df = pd.DataFrame(candles)
                    for col in ['open', 'max', 'min', 'close', 'volume']:
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                    df.dropna(inplace=True)

                    if len(df) < 50:
                        st.session_state.historial.append(f"⏭️ {asset}: datos insuficientes después de limpieza")
                        time.sleep(0.25)
                        st.session_state.indice_activo += 1
                        st.rerun()

                    # Calcular indicadores
                    indicators = calcular_indicadores(df)
                    result = calcular_probabilidad(indicators)

                    if result:
                        prob, direction, strategy = result
                        st.session_state.historial.append(f"📊 {asset}: probabilidad {prob}%")

                        if prob >= umbral:
                            # Señal encontrada
                            # Obtener hora servidor
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

                            senal = {
                                "asset": asset,
                                "direction": direction,
                                "prob": prob,
                                "strategy": strategy,
                                "entry": entry_local.strftime("%H:%M:%S"),
                                "expiry": expiry_local.strftime("%H:%M:%S"),
                                "entry_utc": entry_dt.strftime("%Y-%m-%d %H:%M:%S"),
                                "expiry_utc": expiry_dt.strftime("%Y-%m-%d %H:%M:%S")
                            }
                            st.session_state.ultima_senal = senal
                            # Calcular cooldown (entrada + 1 minuto)
                            cooldown = entry_dt + timedelta(minutes=1)
                            st.session_state.cooldown_until = cooldown.astimezone(ecuador)
                            st.session_state.historial.append(f"🎯 ¡Señal encontrada en {asset}!")
                            st.balloons()
                            # Avanzamos índice
                            st.session_state.indice_activo += 1
                            st.rerun()
                        else:
                            st.session_state.historial.append(f"❌ {asset}: no alcanza umbral ({prob}% < {umbral}%)")
                            time.sleep(0.25)
                            st.session_state.indice_activo += 1
                            st.rerun()
                    else:
                        st.session_state.historial.append(f"⚠️ {asset}: sin tendencia clara")
                        time.sleep(0.25)
                        st.session_state.indice_activo += 1
                        st.rerun()

                except Exception as e:
                    st.session_state.historial.append(f"⚠️ Error en {asset}: {str(e)[:50]}")
                    time.sleep(0.25)
                    st.session_state.indice_activo += 1
                    st.rerun()

    # Mostrar última señal si existe
    if st.session_state.ultima_senal:
        signal = st.session_state.ultima_senal
        # Determinar tipo de activo
        asset = signal['asset']
        if "-OTC" in asset:
            tipo_mostrar = "📱 OTC"
            asset_clean = asset.replace("-OTC", "")
        else:
            tipo_mostrar = "🌍 REAL"
            asset_clean = asset

        color = "#006400" if signal["direction"] == "CALL" else "#8B0000"

        asset_display = html.escape(f"{asset_clean} {tipo_mostrar}")
        direction = html.escape(signal['direction'])
        entry = html.escape(signal['entry'])
        expiry = html.escape(signal['expiry'])
        prob = html.escape(str(signal['prob']))
        strategy = html.escape(signal['strategy'])

        html_code = f"""
        <div style="display:flex; justify-content:space-between; background:#111; padding:40px; border-radius:20px; border:4px solid {color}; box-shadow: 0 0 15px rgba(0,0,0,0.5);">
            <div>
                <h1 style="margin-bottom:5px;">{asset_display}</h1>
                <h3 style="color:#ccc;">OPERAR</h3>
                <h2 style="color:#fff;">{entry}</h2>
                <h3 style="color:#ccc;">EXPIRA</h3>
                <h2 style="color:#fff;">{expiry}</h2>
            </div>
            <div style="text-align:right;">
                <h1 style="color:{color}; font-size:4rem; margin:0;">{direction}</h1>
                <h3 style="color:#ccc;">PROBABILIDAD</h3>
                <h1 style="color:#fff;">{prob}%</h1>
                <h4 style="color:#888;">{strategy}</h4>
            </div>
        </div>
        """
        st.markdown(html_code, unsafe_allow_html=True)

        with st.expander("📅 Ver detalles UTC"):
            st.write(f"**Entrada UTC:** {signal['entry_utc']}")
            st.write(f"**Expiración UTC:** {signal['expiry_utc']}")
            if st.session_state.cooldown_until:
                st.write(f"**Próximo escaneo permitido:** {st.session_state.cooldown_until.strftime('%H:%M:%S')} (hora Ecuador)")
    else:
        if st.session_state.api is not None and not st.session_state.escaneando:
            st.info("Presiona 'Reiniciar escaneo' en la barra lateral para comenzar.")
else:
    st.warning("🔒 Por favor, conéctate primero desde el panel izquierdo.")

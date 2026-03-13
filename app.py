import streamlit as st
import pandas as pd
import time
from datetime import datetime, timedelta
import pytz
from iqoptionapi.stable_api import IQ_Option
from bot_1min import evaluar_activo_1min

st.set_page_config(
    page_title="NEUROTRADER 1MIN",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilos CSS (similares a los anteriores)
st.markdown("""
<style>
    .stApp { background-color: #0b0f17; color: #e0e0e0; }
    section[data-testid="stSidebar"] { background-color: #1a1f2b; border-right: 1px solid #2a2f3a; }
    div[data-testid="stMetric"] { background-color: #1e2430; border-radius: 8px; padding: 15px; border-left: 4px solid #00a3ff; }
    .stButton > button { background-color: #2a2f3a; color: white; border: 1px solid #3a4050; border-radius: 5px; padding: 10px 20px; font-weight: 500; }
    .stButton > button:hover { background-color: #3a4050; border-color: #00a3ff; }
    .signal-card {
        background-color: #1e2a3a;
        border-radius: 10px;
        padding: 20px;
        margin: 10px 0;
        border-left: 6px solid;
        box-shadow: 0 4px 8px rgba(0,0,0,0.3);
    }
    .call-card { border-color: #00ff88; }
    .put-card { border-color: #ff4b4b; }
    .waiting-card { border-color: #ffaa00; }
    .alert-card {
        background-color: #2a2a1e;
        border-left: 4px solid #ffaa00;
        padding: 10px;
        margin: 5px 0;
        border-radius: 5px;
    }
</style>
""", unsafe_allow_html=True)

# Inicializar session_state
if 'api' not in st.session_state:
    st.session_state.api = None
if 'conectado' not in st.session_state:
    st.session_state.conectado = False
if 'tipo_cuenta' not in st.session_state:
    st.session_state.tipo_cuenta = "PRACTICE"
if 'saldo' not in st.session_state:
    st.session_state.saldo = 0.0
if 'monitoreando' not in st.session_state:
    st.session_state.monitoreando = False
if 'activo_seleccionado' not in st.session_state:
    st.session_state.activo_seleccionado = None
if 'senal_actual' not in st.session_state:
    st.session_state.senal_actual = None
if 'alerta' not in st.session_state:
    st.session_state.alerta = None
if 'log' not in st.session_state:
    st.session_state.log = []
if 'ultima_evaluacion' not in st.session_state:
    st.session_state.ultima_evaluacion = None

# Zona horaria
ecuador = pytz.timezone("America/Guayaquil")

def conectar(email, password):
    try:
        api = IQ_Option(email, password)
        check, reason = api.connect()
        if check:
            st.session_state.api = api
            st.session_state.conectado = True
            api.change_balance(st.session_state.tipo_cuenta)
            saldo = api.get_balance()
            st.session_state.saldo = saldo if saldo is not None else 0.0
            st.session_state.log.append(f"✅ Conectado - Saldo: {st.session_state.saldo}")
            return True
        else:
            st.error(f"Error: {reason}")
            return False
    except Exception as e:
        st.error(f"Excepción: {e}")
        return False

def desconectar():
    st.session_state.api = None
    st.session_state.conectado = False
    st.session_state.monitoreando = False

# Sidebar
with st.sidebar:
    st.markdown("## ⚡ NEUROTRADER 1MIN")
    st.markdown("---")
    email = st.text_input("📧 Correo electrónico")
    password = st.text_input("🔑 Contraseña", type="password")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔌 CONECTAR", use_container_width=True):
            if email and password:
                conectar(email, password)
            else:
                st.warning("Ingresa credenciales")
    with col2:
        if st.button("⛔ DESCONECTAR", use_container_width=True):
            desconectar()

    st.markdown("---")
    st.markdown("### ⚙️ Configuración")

    # Lista de activos populares (puedes ampliarla)
    activos_sugeridos = ["EURUSD-OTC", "GBPUSD-OTC", "AUDUSD-OTC", "USDJPY-OTC", "EURUSD", "GBPUSD"]
    activo = st.selectbox("Activo a monitorear", activos_sugeridos)
    umbral_adx = st.slider("Umbral ADX", 15, 30, 20, 1)
    anticipacion = st.slider("Anticipación (segundos antes del cierre)", 5, 20, 10, 1)

    st.markdown("---")
    if st.session_state.conectado:
        if not st.session_state.monitoreando:
            if st.button("▶️ INICIAR", use_container_width=True, type="primary"):
                st.session_state.monitoreando = True
                st.session_state.activo_seleccionado = activo
                st.session_state.log.append(f"🚀 Monitoreo iniciado para {activo}")
                st.rerun()
        else:
            if st.button("⏹️ DETENER", use_container_width=True, type="secondary"):
                st.session_state.monitoreando = False
                st.session_state.senal_actual = None
                st.session_state.alerta = None
                st.rerun()

    if st.session_state.conectado:
        st.metric("💰 Saldo", f"${st.session_state.saldo:.2f}")

# Área principal
if st.session_state.conectado:
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Saldo", f"${st.session_state.saldo:.2f}")
    with col2:
        st.metric("Activo", st.session_state.activo_seleccionado or "Ninguno")
    with col3:
        st.metric("Señales generadas", len([s for s in st.session_state.log if "🚀" in s]))

    # Mostrar alerta
    if st.session_state.alerta:
        st.markdown(f'<div class="alert-card">{st.session_state.alerta}</div>', unsafe_allow_html=True)

    # Mostrar señal actual
    if st.session_state.senal_actual:
        s = st.session_state.senal_actual
        card_class = "call-card" if s['direccion'] == "CALL" else "put-card"
        st.markdown(f"""
        <div class="signal-card {card_class}">
            <div class="signal-title">{'🔵 COMPRA (CALL)' if s['direccion'] == 'CALL' else '🔴 VENTA (PUT)'}</div>
            <div class="signal-detail"><strong>Activo:</strong> {s['asset']}</div>
            <div class="signal-detail"><strong>Entrada:</strong> {s['entrada']}</div>
            <div class="signal-detail"><strong>Vencimiento:</strong> 1 minuto</div>
            <div class="signal-detail"><strong>Fuerza:</strong> {s['fuerza']:.1f}%</div>
        </div>
        """, unsafe_allow_html=True)

        now = datetime.now(ecuador)
        if st.session_state.proxima_entrada and now < st.session_state.proxima_entrada:
            segundos = (st.session_state.proxima_entrada - now).total_seconds()
            st.info(f"⏳ Próxima entrada en {int(segundos)} segundos...")
        else:
            st.success("✅ Momento de entrada alcanzado")

    # Log de eventos
    with st.expander("📋 Log de eventos", expanded=True):
        for linea in st.session_state.log[-20:]:
            st.text(linea)

    # Lógica de monitoreo continuo
    if st.session_state.monitoreando and st.session_state.activo_seleccionado:
        now = datetime.now(ecuador)

        # Evaluar cada segundo, pero solo actuar en momentos clave
        # Simulamos un bucle que se ejecuta cada segundo
        # En la práctica, con st.rerun() podemos actualizar la interfaz

        # Obtener el segundo actual
        segundo = now.second

        # Evaluar en el segundo (60 - anticipacion) para dar tiempo a preparar la orden
        segundo_objetivo = 60 - anticipacion
        if segundo >= segundo_objetivo:
            # Estamos cerca del cierre de la vela actual
            resultado = evaluar_activo_1min(st.session_state.api, st.session_state.activo_seleccionado, umbral_adx)
            if resultado:
                if resultado['confirmacion']:
                    # Señal fuerte
                    entrada = now.replace(second=0, microsecond=0) + timedelta(minutes=1)  # próxima vela
                    st.session_state.senal_actual = {
                        'asset': resultado['asset'],
                        'direccion': resultado['direccion'],
                        'entrada': entrada.strftime("%H:%M:%S"),
                        'fuerza': resultado['fuerza']
                    }
                    st.session_state.proxima_entrada = entrada
                    st.session_state.log.append(f"🚀 SEÑAL: {resultado['asset']} - {resultado['direccion']} a las {entrada.strftime('%H:%M:%S')}")
                    st.session_state.alerta = None
                elif resultado['alerta']:
                    st.session_state.alerta = f"🔔 {resultado['asset']} - Posible señal en la próxima vela (fuerza {resultado['fuerza']:.0f}%)"
                    st.session_state.log.append(st.session_state.alerta)
            # Esperar hasta el siguiente minuto para no repetir
            time.sleep(2)
            st.rerun()
        else:
            # Mostrar tiempo restante para la próxima evaluación
            segundos_restantes = segundo_objetivo - segundo
            if segundos_restantes > 0:
                st.info(f"⏳ Próxima evaluación en {segundos_restantes} segundos...")
            time.sleep(1)
            st.rerun()

else:
    st.info("🔒 Conéctate a IQ Option para comenzar.")

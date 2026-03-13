import streamlit as st
import pandas as pd
import time
from datetime import datetime, timedelta
import pytz
from iqoptionapi.stable_api import IQ_Option
from bot import (
    buscar_mejor_senal,
    obtener_activos_abiertos,
    evaluar_activo_senal
)

st.set_page_config(
    page_title="NEUROTRADER GROCK",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilos CSS
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
    .asset-box {
        background-color: #1a2a3a;
        padding: 15px;
        border-radius: 8px;
        margin-bottom: 10px;
        border-left: 4px solid #00a3ff;
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
if 'operacion_en_curso' not in st.session_state:
    st.session_state.operacion_en_curso = None  # dict con datos de la operación actual
if 'proxima_senal' not in st.session_state:
    st.session_state.proxima_senal = None  # dict con la mejor señal encontrada (para siguiente operación)
if 'log' not in st.session_state:
    st.session_state.log = []

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
    st.session_state.operacion_en_curso = None
    st.session_state.proxima_senal = None

# Sidebar
with st.sidebar:
    st.markdown("## 🧠 NEUROTRADER GROCK")
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

    tipo_mercado = st.selectbox("Mercado", ["OTC", "REAL", "AMBOS"], index=2)
    min_fuerza = st.slider("Fuerza mínima para señal", 30, 90, 50, 5,
                           help="Las señales con fuerza inferior se ignoran")
    anticipacion = st.slider("Anticipación de señal (segundos)", 0, 60, 20, 5,
                             help="Tiempo antes del cierre de la vela para mostrar la señal")

    st.markdown("---")
    if st.session_state.conectado:
        if not st.session_state.monitoreando:
            if st.button("▶️ INICIAR MONITOREO", use_container_width=True, type="primary"):
                st.session_state.monitoreando = True
                st.session_state.log.append("🚀 Monitoreo iniciado")
                st.rerun()
        else:
            if st.button("⏹️ DETENER", use_container_width=True, type="secondary"):
                st.session_state.monitoreando = False
                st.rerun()

    if st.session_state.conectado:
        st.metric("💰 Saldo", f"${st.session_state.saldo:.2f}")

# Área principal
if st.session_state.conectado:
    # Métricas
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Saldo", f"${st.session_state.saldo:.2f}")
    with col2:
        if st.session_state.operacion_en_curso:
            st.metric("Operación en curso", st.session_state.operacion_en_curso['asset'])
        else:
            st.metric("Operación en curso", "Ninguna")
    with col3:
        st.metric("Señales generadas", len([s for s in st.session_state.log if "🚀" in s]))

    # Mostrar operación en curso con cuenta regresiva
    if st.session_state.operacion_en_curso:
        op = st.session_state.operacion_en_curso
        now = datetime.now(ecuador)
        vencimiento = datetime.strptime(op['vencimiento'], "%H:%M:%S").time()
        vencimiento_dt = datetime.combine(now.date(), vencimiento)
        if vencimiento_dt < now:
            vencimiento_dt += timedelta(days=1)
        resto = (vencimiento_dt - now).total_seconds()
        mins, segs = divmod(int(resto), 60)
        st.markdown(f"""
        <div class="signal-card waiting-card">
            <div class="signal-title">⏳ OPERACIÓN EN CURSO</div>
            <div class="signal-detail"><strong>Activo:</strong> {op['asset']}</div>
            <div class="signal-detail"><strong>Dirección:</strong> {op['direccion']}</div>
            <div class="signal-detail"><strong>Entrada:</strong> {op['entrada']}</div>
            <div class="signal-detail"><strong>Vencimiento:</strong> {op['vencimiento']}</div>
            <div class="signal-detail"><strong>Tiempo restante:</strong> {mins:02d}:{segs:02d}</div>
        </div>
        """, unsafe_allow_html=True)

    # Mostrar próxima señal si existe (mientras no hay operación)
    if not st.session_state.operacion_en_curso and st.session_state.proxima_senal:
        senal = st.session_state.proxima_senal
        card_class = "call-card" if senal['direccion'] == "CALL" else "put-card"
        st.markdown(f"""
        <div class="signal-card {card_class}">
            <div class="signal-title">{'🔵 COMPRA' if senal['direccion'] == 'CALL' else '🔴 VENTA'}</div>
            <div class="signal-detail"><strong>Activo:</strong> {senal['asset']}</div>
            <div class="signal-detail"><strong>Fuerza:</strong> {senal['fuerza']:.1f}</div>
            <div class="signal-detail"><strong>Nivel Fibonacci:</strong> {senal['nivel_fib']:.5f}</div>
            <div class="signal-detail"><strong>Precio actual:</strong> {senal['precio']:.5f}</div>
            <div class="signal-detail"><strong>Zona de entrada:</strong> {senal['zona'][0]:.5f} - {senal['zona'][1]:.5f}</div>
        </div>
        """, unsafe_allow_html=True)
    elif not st.session_state.operacion_en_curso:
        st.info("Esperando señal...")

    # Log de eventos
    with st.expander("📋 Log de eventos", expanded=True):
        for linea in st.session_state.log[-30:]:
            st.text(linea)

    # Lógica de monitoreo
    if st.session_state.monitoreando:
        now = datetime.now(ecuador)

        # Si hay operación en curso, verificar si ya venció
        if st.session_state.operacion_en_curso:
            vencimiento = datetime.strptime(st.session_state.operacion_en_curso['vencimiento'], "%H:%M:%S").time()
            vencimiento_dt = datetime.combine(now.date(), vencimiento)
            if vencimiento_dt < now:
                vencimiento_dt += timedelta(days=1)
            if now >= vencimiento_dt:
                # Operación vencida, limpiar
                st.session_state.operacion_en_curso = None
                st.session_state.log.append("✅ Operación finalizada")
                # Inmediatamente después de finalizar, ver si hay próxima señal
                if st.session_state.proxima_senal:
                    # Lanzar la próxima señal
                    senal = st.session_state.proxima_senal
                    entrada = now + timedelta(seconds=anticipacion)
                    entrada_str = entrada.strftime("%H:%M:%S")
                    vencimiento_str = (entrada + timedelta(minutes=5)).strftime("%H:%M:%S")
                    st.session_state.operacion_en_curso = {
                        'asset': senal['asset'],
                        'direccion': senal['direccion'],
                        'entrada': entrada_str,
                        'vencimiento': vencimiento_str,
                        'fuerza': senal['fuerza']
                    }
                    st.session_state.proxima_senal = None
                    st.session_state.log.append(f"🚀 SEÑAL EJECUTADA: {senal['asset']} - {senal['direccion']} a las {entrada_str}")
                # Si no hay próxima, seguir buscando
                time.sleep(1)
                st.rerun()
            else:
                # Operación aún activa, mientras tanto buscar próxima señal
                with st.spinner("Buscando próxima oportunidad..."):
                    mejor = buscar_mejor_senal(st.session_state.api, tipo_mercado, min_fuerza)
                    if mejor:
                        st.session_state.proxima_senal = mejor
                        st.session_state.log.append(f"🎯 Próxima señal encontrada: {mejor['asset']} ({mejor['direccion']}, fuerza {mejor['fuerza']:.1f})")
                    else:
                        st.session_state.proxima_senal = None
                time.sleep(5)  # esperar un poco antes de la próxima búsqueda
                st.rerun()
        else:
            # No hay operación, buscar la mejor señal ahora
            mejor = buscar_mejor_senal(st.session_state.api, tipo_mercado, min_fuerza)
            if mejor:
                st.session_state.proxima_senal = mejor
                st.session_state.log.append(f"🎯 Señal encontrada: {mejor['asset']} ({mejor['direccion']}, fuerza {mejor['fuerza']:.1f})")
                # Esperar hasta el momento de entrada (simulado)
                # En un bot real, aquí se ejecutaría la operación automáticamente
                # Nosotros solo mostramos la señal
                st.rerun()
            else:
                st.session_state.log.append("🔍 No se encontraron señales en este ciclo.")
                time.sleep(10)
                st.rerun()

else:
    st.info("🔒 Conéctate a IQ Option para comenzar.")

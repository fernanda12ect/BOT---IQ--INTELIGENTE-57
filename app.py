import streamlit as st
import pandas as pd
import time
from datetime import datetime, timedelta
import pytz
from iqoptionapi.stable_api import IQ_Option
from bot import (
    buscar_mejor_senal,
    obtener_activos_abiertos
)

st.set_page_config(
    page_title="NEUROTRADER - ESTRATEGIA GROK",
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
    st.session_state.operacion_en_curso = False
if 'senal_actual' not in st.session_state:
    st.session_state.senal_actual = None
if 'proxima_entrada' not in st.session_state:
    st.session_state.proxima_entrada = None
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

# Sidebar
with st.sidebar:
    st.markdown("## 🧠 NEUROTRADER")
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
    umbral_adx = st.slider("Umbral ADX mínimo", 15, 30, 20, 1,
                           help="ADX mínimo para confirmar tendencia")
    anticipacion = st.slider("Anticipación de señal (segundos)", 0, 30, 20, 5,
                             help="Tiempo antes de la entrada para mostrar la señal")

    st.markdown("---")
    if st.session_state.conectado:
        if not st.session_state.monitoreando:
            if st.button("▶️ INICIAR MONITOREO", use_container_width=True, type="primary"):
                st.session_state.monitoreando = True
                st.session_state.operacion_en_curso = False
                st.session_state.senal_actual = None
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
            st.metric("Operación en curso", "SÍ")
        else:
            st.metric("Operación en curso", "NO")
    with col3:
        st.metric("Señales generadas", len([s for s in st.session_state.log if "🚀" in s]))

    # Mostrar señal actual si existe
    if st.session_state.senal_actual:
        s = st.session_state.senal_actual
        card_class = "call-card" if s['direccion'] == "CALL" else "put-card"
        st.markdown(f"""
        <div class="signal-card {card_class}">
            <div class="signal-title">{'🔵 COMPRA (CALL)' if s['direccion'] == 'CALL' else '🔴 VENTA (PUT)'}</div>
            <div class="signal-detail"><strong>Activo:</strong> {s['asset']}</div>
            <div class="signal-detail"><strong>Entrada:</strong> {s['entrada']}</div>
            <div class="signal-detail"><strong>Vencimiento:</strong> {s['vencimiento']} (5 min)</div>
            <div class="signal-detail"><strong>Nivel Fibonacci:</strong> {s['nombre_fib']} ({s['nivel_fib']:.5f})</div>
            <div class="signal-detail"><strong>Rechazo:</strong> {'✅ Sí' if s['rechazo'] else '❌ No'}</div>
            <div class="signal-detail"><strong>Fuerza ADX:</strong> {s['fuerza']:.1f}</div>
        </div>
        """, unsafe_allow_html=True)

        if st.session_state.proxima_entrada:
            now = datetime.now(ecuador)
            segundos_restantes = (st.session_state.proxima_entrada - now).total_seconds()
            if segundos_restantes > 0:
                st.info(f"⏳ Próxima entrada en {int(segundos_restantes)} segundos...")
            else:
                st.success("✅ Momento de entrada alcanzado")
    else:
        st.info("No hay señal activa en este momento.")

    # Log de eventos
    with st.expander("📋 Log de eventos", expanded=True):
        for linea in st.session_state.log[-30:]:
            st.text(linea)

    # Lógica de monitoreo
    if st.session_state.monitoreando:
        now = datetime.now(ecuador)

        # Si hay una operación en curso, esperar a que termine
        if st.session_state.operacion_en_curso:
            if st.session_state.proxima_entrada and now >= st.session_state.proxima_entrada:
                # La operación ya debería haberse ejecutado, ahora esperamos 5 minutos para que venza
                tiempo_vencimiento = st.session_state.proxima_entrada + timedelta(minutes=5)
                if now >= tiempo_vencimiento:
                    st.session_state.operacion_en_curso = False
                    st.session_state.senal_actual = None
                    st.session_state.proxima_entrada = None
                    st.session_state.log.append("✅ Operación finalizada. Buscando nueva señal...")
                    time.sleep(2)
                    st.rerun()
                else:
                    # Aún no vence
                    segundos_restantes = (tiempo_vencimiento - now).total_seconds()
                    st.info(f"⏳ Operación en curso. Vence en {int(segundos_restantes)} segundos.")
                    time.sleep(5)
                    st.rerun()
            else:
                # No debería pasar, pero por si acaso
                st.session_state.operacion_en_curso = False
                st.rerun()
        else:
            # No hay operación, buscar la mejor señal
            with st.spinner("Buscando la mejor oportunidad..."):
                activos = obtener_activos_abiertos(st.session_state.api, tipo_mercado)
                if activos:
                    mejor = buscar_mejor_senal(st.session_state.api, activos, umbral_adx)
                    if mejor:
                        # Generar señal con anticipación
                        entrada = now + timedelta(seconds=anticipacion)
                        vencimiento = entrada + timedelta(minutes=5)
                        st.session_state.senal_actual = {
                            'asset': mejor['asset'],
                            'direccion': mejor['direccion'],
                            'entrada': entrada.strftime("%H:%M:%S"),
                            'vencimiento': vencimiento.strftime("%H:%M:%S"),
                            'nivel_fib': mejor['nivel_fib'],
                            'nombre_fib': mejor['nombre_fib'],
                            'rechazo': mejor['rechazo'],
                            'fuerza': mejor['fuerza']
                        }
                        st.session_state.proxima_entrada = entrada
                        st.session_state.operacion_en_curso = True
                        st.session_state.log.append(f"🚀 SEÑAL GENERADA: {mejor['asset']} - {mejor['direccion']} a las {entrada.strftime('%H:%M:%S')}")
                        st.rerun()
                    else:
                        st.session_state.log.append("🔍 No se encontraron señales en este ciclo.")
                else:
                    st.session_state.log.append("⚠️ No hay activos disponibles.")
            # Esperar un poco antes del próximo ciclo
            time.sleep(10)
            st.rerun()

else:
    st.info("🔒 Conéctate a IQ Option para comenzar.")

import streamlit as st
import pandas as pd
import time
from datetime import datetime, timedelta
import pytz
from iqoptionapi.stable_api import IQ_Option
from bot import (
    evaluar_activo,
    seleccionar_activos_fuertes,
    obtener_activos_abiertos
)

st.set_page_config(
    page_title="NEUROTRADER - DIVERGENCIAS",
    page_icon="📊",
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
        padding: 15px;
        margin: 10px 0;
        border-left: 6px solid;
        box-shadow: 0 4px 8px rgba(0,0,0,0.3);
    }
    .call-card { border-color: #00ff88; }
    .put-card { border-color: #ff4b4b; }
    .alert-card {
        background-color: #2a2a1e;
        border-left: 4px solid #ffaa00;
        padding: 10px;
        margin: 5px 0;
        border-radius: 5px;
    }
    .asset-title {
        font-size: 1.2rem;
        font-weight: bold;
        margin-bottom: 5px;
    }
    .signal-detail {
        font-size: 0.9rem;
        color: #ccc;
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
if 'activos_seleccionados' not in st.session_state:
    st.session_state.activos_seleccionados = []  # lista de los 2 activos actuales
if 'señales' not in st.session_state:
    st.session_state.señales = []  # historial de señales generadas
if 'ultima_senal_tiempo' not in st.session_state:
    st.session_state.ultima_senal_tiempo = None  # para esperar 5 min después de señal
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
            # Obtener activos
            activos = obtener_activos_abiertos(api, "AMBOS")
            st.session_state.activos_totales = activos
            st.session_state.log.append(f"📊 Total activos disponibles: {len(activos)}")
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
    st.markdown("## 📈 NEUROTRADER - DIVERGENCIAS")
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
    pausa_entre_ciclos = st.slider("Pausa entre ciclos de búsqueda (seg)", 30, 120, 60, 10)
    anticipacion = st.slider("Anticipación de señal (seg)", 5, 30, 15, 5)

    st.markdown("---")
    if st.session_state.conectado:
        if not st.session_state.monitoreando:
            if st.button("▶️ INICIAR", use_container_width=True, type="primary"):
                st.session_state.monitoreando = True
                st.session_state.log.append("🚀 Monitoreo iniciado")
                # Seleccionar los 2 activos más fuertes
                with st.spinner("Seleccionando los 2 activos más fuertes..."):
                    activos_totales = obtener_activos_abiertos(st.session_state.api, tipo_mercado)
                    if activos_totales:
                        seleccionados = seleccionar_activos_fuertes(st.session_state.api, activos_totales, num_activos=2)
                        st.session_state.activos_seleccionados = seleccionados
                        st.session_state.log.append(f"✅ Activos seleccionados: {', '.join(seleccionados)}")
                    else:
                        st.session_state.log.append("⚠️ No hay activos disponibles")
                st.rerun()
        else:
            if st.button("⏹️ DETENER", use_container_width=True, type="secondary"):
                st.session_state.monitoreando = False
                st.rerun()

    if st.session_state.conectado:
        st.metric("💰 Saldo", f"${st.session_state.saldo:.2f}")

# Área principal
if st.session_state.conectado:
    st.title("📊 Señales de Divergencia (5 min)")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Saldo", f"${st.session_state.saldo:.2f}")
    with col2:
        st.metric("Activos seguimiento", len(st.session_state.activos_seleccionados))
    with col3:
        st.metric("Señales emitidas", len(st.session_state.señales))

    # Mostrar activos seleccionados
    if st.session_state.activos_seleccionados:
        st.subheader("🎯 Activos en seguimiento")
        for asset in st.session_state.activos_seleccionados:
            st.markdown(f'<div class="alert-card">🔍 {asset}</div>', unsafe_allow_html=True)

    # Mostrar últimas señales
    if st.session_state.señales:
        st.subheader("📊 Historial de señales")
        for señal in st.session_state.señales[-10:][::-1]:
            card_class = "call-card" if señal['direccion'] == "CALL" else "put-card"
            st.markdown(f"""
            <div class="signal-card {card_class}">
                <div class="asset-title">[{señal['hora']}] {señal['asset']}</div>
                <div><strong>{señal['direccion']}</strong> - {señal['descripcion']}</div>
                <div class="signal-detail">Entrada: {señal['entrada']} | Vencimiento: 5 min</div>
                <div class="signal-detail">Fuerza: {señal['fuerza']:.1f}%</div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("No hay señales aún.")

    # Log de eventos
    with st.expander("📋 Log de eventos", expanded=False):
        for linea in st.session_state.log[-20:]:
            st.text(linea)

    # Lógica de monitoreo
    if st.session_state.monitoreando:
        now = datetime.now(ecuador)

        # Verificar si hay una operación en curso (después de una señal, esperar 5 min)
        if st.session_state.ultima_senal_tiempo:
            tiempo_transcurrido = (now - st.session_state.ultima_senal_tiempo).total_seconds()
            if tiempo_transcurrido < 300:  # 5 minutos
                st.info(f"⏳ Esperando {int(300 - tiempo_transcurrido)} segundos antes de nueva señal...")
                time.sleep(1)
                st.rerun()
            else:
                st.session_state.ultima_senal_tiempo = None
                # No hacemos rerun inmediato, para que pueda evaluar

        # Evaluar los activos seleccionados
        if st.session_state.activos_seleccionados:
            for asset in st.session_state.activos_seleccionados:
                res = evaluar_activo(st.session_state.api, asset)
                if res and 'direccion' in res:
                    # Es una señal
                    entrada = now + timedelta(seconds=anticipacion)
                    entrada_str = entrada.strftime("%H:%M:%S")
                    st.session_state.señales.append({
                        'hora': now.strftime("%H:%M:%S"),
                        'asset': asset,
                        'direccion': res['direccion'],
                        'descripcion': res['descripcion'],
                        'entrada': entrada_str,
                        'fuerza': res['fuerza']
                    })
                    st.session_state.ultima_senal_tiempo = now
                    st.session_state.log.append(f"🚀 SEÑAL: {asset} - {res['direccion']} a las {entrada_str} (Fuerza: {res['fuerza']:.1f}%)")
                    # Forzar rerun para mostrar la señal inmediatamente
                    st.rerun()
                # Esperar un poco entre activos
                time.sleep(1)

            # Si no hubo señal, esperar un poco y volver a evaluar
            time.sleep(pausa_entre_ciclos)
            st.rerun()
        else:
            # No hay activos seleccionados, buscar nuevos
            st.session_state.log.append("🔍 Buscando nuevos activos fuertes...")
            activos_totales = obtener_activos_abiertos(st.session_state.api, tipo_mercado)
            if activos_totales:
                seleccionados = seleccionar_activos_fuertes(st.session_state.api, activos_totales, num_activos=2)
                st.session_state.activos_seleccionados = seleccionados
                st.session_state.log.append(f"✅ Nuevos activos seleccionados: {', '.join(seleccionados)}")
            else:
                st.session_state.log.append("⚠️ No hay activos disponibles")
            time.sleep(pausa_entre_ciclos)
            st.rerun()

else:
    st.info("🔒 Conéctate a IQ Option para comenzar.")

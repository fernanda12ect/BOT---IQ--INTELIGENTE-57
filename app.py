import streamlit as st
import pandas as pd
import time
from datetime import datetime, timedelta
import pytz
from iqoptionapi.stable_api import IQ_Option
from bot import evaluar_activo, obtener_activos_abiertos

st.set_page_config(
    page_title="TRADER NIVELES - 4 ACTIVOS",
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
    .asset-card {
        background-color: #1e2a3a;
        border-radius: 10px;
        padding: 15px;
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
if 'activos_seleccionados' not in st.session_state:
    st.session_state.activos_seleccionados = []  # lista de hasta 4 activos con su info
if 'senal_activa' not in st.session_state:
    st.session_state.senal_activa = None
if 'log' not in st.session_state:
    st.session_state.log = []
if 'ultima_actualizacion' not in st.session_state:
    st.session_state.ultima_actualizacion = None

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
    st.markdown("## 📊 TRADER NIVELES")
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
    vencimiento = st.selectbox("Vencimiento", ["1 minuto", "2 minutos"], index=0)
    tolerancia = st.slider("Tolerancia para toque (%)", 0.05, 0.5, 0.1, 0.05) / 100
    max_activos = 4

    st.markdown("---")
    if st.session_state.conectado:
        if not st.session_state.monitoreando:
            if st.button("▶️ INICIAR", use_container_width=True, type="primary"):
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
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Saldo", f"${st.session_state.saldo:.2f}")
    with col2:
        st.metric("Activos en seguimiento", len(st.session_state.activos_seleccionados))
    with col3:
        st.metric("Señales activas", 1 if st.session_state.senal_activa else 0)

    # Mostrar tarjetas de activos seleccionados (máximo 4)
    if st.session_state.activos_seleccionados:
        st.subheader("📌 ACTIVOS EN SEGUIMIENTO")
        cols = st.columns(min(len(st.session_state.activos_seleccionados), max_activos))
        for i, activo in enumerate(st.session_state.activos_seleccionados[:max_activos]):
            with cols[i]:
                # Determinar el tipo de nivel más cercano
                nivel_mas_cerca = None
                if activo['niveles']:
                    nivel_mas_cerca = activo['niveles'][0]
                elif activo['lineas']:
                    nivel_mas_cerca = activo['lineas'][0]
                if nivel_mas_cerca:
                    distancia_pct = nivel_mas_cerca['distancia'] * 100
                    card_class = "call-card" if nivel_mas_cerca.get('tipo') == 'soporte' or nivel_mas_cerca.get('tipo') == 'alcista' else "put-card"
                    tipo_nivel = nivel_mas_cerca.get('tipo', 'tendencia')
                    st.markdown(f"""
                    <div class="asset-card {card_class}">
                        <h4>{activo['asset']}</h4>
                        <p><strong>Tipo:</strong> {tipo_nivel}</p>
                        <p><strong>Nivel:</strong> {nivel_mas_cerca['precio']:.5f}</p>
                        <p><strong>Distancia:</strong> {distancia_pct:.3f}%</p>
                        <p><strong>Precio actual:</strong> {activo['precio']:.5f}</p>
                    </div>
                    """, unsafe_allow_html=True)

    # Mostrar señal activa
    if st.session_state.senal_activa:
        s = st.session_state.senal_activa
        card_class = "call-card" if s['direccion'] == "CALL" else "put-card"
        st.markdown(f"""
        <div class="asset-card {card_class}">
            <h3>{'🔵 COMPRA' if s['direccion'] == 'CALL' else '🔴 VENTA'}</h3>
            <p><strong>Activo:</strong> {s['asset']}</p>
            <p><strong>Entrada:</strong> {s['entrada']}</p>
            <p><strong>Vencimiento:</strong> {s['vencimiento']}</p>
            <p><strong>Nivel:</strong> {s['nivel']:.5f} ({s['tipo_nivel']})</p>
        </div>
        """, unsafe_allow_html=True)

    with st.expander("📋 Log de eventos", expanded=True):
        for linea in st.session_state.log[-20:]:
            st.text(linea)

    # Lógica de monitoreo
    if st.session_state.monitoreando:
        now = datetime.now(ecuador)

        # Cada segundo actualizamos la información
        if st.session_state.ultima_actualizacion is None or (now - st.session_state.ultima_actualizacion).total_seconds() >= 1:
            # Obtener lista de activos disponibles
            activos = obtener_activos_abiertos(st.session_state.api, tipo_mercado)
            if not activos:
                time.sleep(5)
                st.rerun()

            # Evaluar cada activo y recolectar los que tienen niveles o líneas cercanas
            candidatos = []
            for asset in activos:
                res = evaluar_activo(st.session_state.api, asset)
                if res:
                    # Combinar niveles y líneas, y ordenar por distancia
                    todos_niveles = []
                    for n in res['niveles']:
                        n['tipo_nivel'] = 'soporte' if n['tipo'] == 'soporte' else 'resistencia'
                        todos_niveles.append(n)
                    for l in res['lineas']:
                        l['tipo_nivel'] = 'tendencia ' + l['tipo']
                        todos_niveles.append(l)
                    if todos_niveles:
                        todos_niveles.sort(key=lambda x: x['distancia'])
                        res['mejor_nivel'] = todos_niveles[0]
                        candidatos.append(res)
                time.sleep(0.1)  # pausa entre activos

            # Seleccionar hasta 4 activos con menor distancia
            candidatos.sort(key=lambda x: x['mejor_nivel']['distancia'])
            st.session_state.activos_seleccionados = candidatos[:max_activos]

            # Verificar si algún activo está lo suficientemente cerca para generar señal
            for activo in st.session_state.activos_seleccionados:
                if activo['mejor_nivel']['distancia'] <= tolerancia:
                    # Generar señal
                    minutos = 1 if vencimiento == "1 minuto" else 2
                    entrada = now + timedelta(seconds=10)  # pequeña anticipación
                    entrada_str = entrada.strftime("%H:%M:%S")
                    vencimiento_str = (entrada + timedelta(minutes=minutos)).strftime("%H:%M:%S")
                    st.session_state.senal_activa = {
                        'asset': activo['asset'],
                        'direccion': 'CALL' if activo['mejor_nivel']['tipo_nivel'] in ['soporte', 'tendencia alcista'] else 'PUT',
                        'entrada': entrada_str,
                        'vencimiento': vencimiento_str,
                        'nivel': activo['mejor_nivel']['precio'],
                        'tipo_nivel': activo['mejor_nivel']['tipo_nivel']
                    }
                    st.session_state.log.append(f"🚀 SEÑAL: {activo['asset']} - {st.session_state.senal_activa['direccion']} a las {entrada_str}")
                    break  # solo una señal por ciclo

            st.session_state.ultima_actualizacion = now
            time.sleep(1)
            st.rerun()
        else:
            time.sleep(0.5)
            st.rerun()

else:
    st.info("🔒 Conéctate a IQ Option para comenzar.")

import streamlit as st
import pandas as pd
import time
from datetime import datetime, timedelta
import pytz
from iqoptionapi.stable_api import IQ_Option
from bot import (
    evaluar_activo,
    seleccionar_mejor_activo,
    obtener_activos_abiertos,
    ESTRATEGIAS
)

st.set_page_config(
    page_title="NEUROTRADER PRO",
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
if 'activo_seleccionado' not in st.session_state:
    st.session_state.activo_seleccionado = None
if 'alerta' not in st.session_state:
    st.session_state.alerta = None
if 'señal' not in st.session_state:
    st.session_state.señal = None
if 'log' not in st.session_state:
    st.session_state.log = []
if 'indice_ronda' not in st.session_state:
    st.session_state.indice_ronda = 0
if 'activos_totales' not in st.session_state:
    st.session_state.activos_totales = []
if 'estrategias_activas' not in st.session_state:
    st.session_state.estrategias_activas = [nombre for nombre, _ in ESTRATEGIAS]

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
            st.session_state.activos_totales = obtener_activos_abiertos(api, "AMBOS")
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
    st.session_state.activo_seleccionado = None
    st.session_state.alerta = None
    st.session_state.señal = None

# Sidebar
with st.sidebar:
    st.markdown("## 🧠 NEUROTRADER PRO")
    st.markdown("---")
    email = st.text_input("Correo electrónico")
    password = st.text_input("Contraseña", type="password")

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
    mercado = st.selectbox("Mercado", ["OTC", "REAL", "AMBOS"], index=2)
    tamaño_ronda = st.slider("Activos por ronda", 10, 50, 20, 5)
    pausa_entre_rondas = st.slider("Pausa entre rondas (seg)", 5, 60, 15, 5)

    st.markdown("---")
    st.markdown("### 🎯 Estrategias activas")
    nuevas_estrategias = []
    for nombre, _ in ESTRATEGIAS:
        activa = st.checkbox(nombre, value=(nombre in st.session_state.estrategias_activas))
        if activa:
            nuevas_estrategias.append(nombre)
    st.session_state.estrategias_activas = nuevas_estrategias

    st.markdown("---")
    if st.session_state.conectado:
        if not st.session_state.monitoreando:
            if st.button("▶️ INICIAR", use_container_width=True, type="primary"):
                st.session_state.monitoreando = True
                st.session_state.indice_ronda = 0
                st.session_state.activo_seleccionado = None
                st.session_state.alerta = None
                st.session_state.señal = None
                st.session_state.log.append("🚀 Monitoreo iniciado")
                st.rerun()
        else:
            if st.button("⏹️ DETENER", use_container_width=True, type="secondary"):
                st.session_state.monitoreando = False
                st.rerun()

    if st.session_state.conectado:
        st.metric("Saldo", f"${st.session_state.saldo:.2f}")

# Área principal
if st.session_state.conectado:
    # Métricas
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Saldo", f"${st.session_state.saldo:.2f}")
    with col2:
        if st.session_state.activo_seleccionado:
            st.metric("Activo en seguimiento", st.session_state.activo_seleccionado['asset'])
        else:
            st.metric("Activo en seguimiento", "Ninguno")
    with col3:
        st.metric("Señales generadas", len([s for s in st.session_state.log if "SEÑAL" in s]))

    # Alerta previa
    if st.session_state.alerta:
        st.markdown(f'<div class="alert-card">{st.session_state.alerta}</div>', unsafe_allow_html=True)

    # Señal definitiva
    if st.session_state.señal:
        card_class = "call-card" if st.session_state.señal['direccion'] == "CALL" else "put-card"
        st.markdown(f"""
        <div class="signal-card {card_class}">
            <div class="signal-title">{'🔵 COMPRA' if st.session_state.señal['direccion'] == 'CALL' else '🔴 VENTA'}</div>
            <div class="signal-detail"><strong>Activo:</strong> {st.session_state.señal['asset']}</div>
            <div class="signal-detail"><strong>Entrada:</strong> {st.session_state.señal['entrada']}</div>
            <div class="signal-detail"><strong>Vencimiento:</strong> {st.session_state.señal['vencimiento']}</div>
            <div class="signal-detail"><strong>Estrategias:</strong> {', '.join(st.session_state.señal['estrategias'])}</div>
        </div>
        """, unsafe_allow_html=True)

    # Log de eventos
    with st.expander("📋 Log de eventos"):
        for linea in st.session_state.log[-30:]:
            st.text(linea)

    # Lógica de monitoreo
    if st.session_state.monitoreando:
        now = datetime.now(ecuador)

        # Si ya tenemos un activo seleccionado
        if st.session_state.activo_seleccionado:
            # Verificar si ya pasó el tiempo de la señal (para reiniciar después de 5 min)
            if st.session_state.señal:
                tiempo_transcurrido = (now - st.session_state.señal['timestamp']).total_seconds()
                if tiempo_transcurrido > 300:  # 5 minutos
                    st.session_state.activo_seleccionado = None
                    st.session_state.alerta = None
                    st.session_state.señal = None
                    st.session_state.log.append("🔄 Reiniciando búsqueda...")
                    time.sleep(2)
                    st.rerun()
                else:
                    time.sleep(5)
                    st.rerun()
            else:
                # Monitorear el activo seleccionado
                resultado = evaluar_activo(
                    st.session_state.api,
                    st.session_state.activo_seleccionado['asset'],
                    st.session_state.estrategias_activas
                )
                if resultado and resultado['lista_para_entrar'] and resultado['direccion']:
                    entrada = now.strftime("%H:%M:%S")
                    vencimiento = (now + timedelta(minutes=5)).strftime("%H:%M:%S")
                    st.session_state.señal = {
                        'asset': resultado['asset'],
                        'direccion': resultado['direccion'],
                        'entrada': entrada,
                        'vencimiento': vencimiento,
                        'estrategias': resultado['estrategias'],
                        'timestamp': now
                    }
                    st.session_state.log.append(f"🚀 SEÑAL GENERADA: {resultado['asset']} - {resultado['direccion']} a las {entrada}")
                    st.rerun()
                else:
                    time.sleep(2)
                    st.rerun()
        else:
            # No tenemos activo, buscamos uno nuevo
            activos_totales = st.session_state.activos_totales
            if not activos_totales:
                st.warning("No hay activos disponibles")
                time.sleep(pausa_entre_rondas)
                st.rerun()

            # Filtrar por mercado
            if mercado == "OTC":
                activos_filtrados = [a for a in activos_totales if '-OTC' in a]
            elif mercado == "REAL":
                activos_filtrados = [a for a in activos_totales if '-OTC' not in a]
            else:
                activos_filtrados = activos_totales

            # Dividir en rondas
            inicio = st.session_state.indice_ronda * tamaño_ronda
            fin = inicio + tamaño_ronda
            ronda_actual = activos_filtrados[inicio:fin]

            if not ronda_actual:
                st.session_state.indice_ronda = 0
                st.rerun()

            st.session_state.log.append(f"Analizando ronda {st.session_state.indice_ronda + 1} ({len(ronda_actual)} activos)...")
            mejor = seleccionar_mejor_activo(
                st.session_state.api,
                ronda_actual,
                st.session_state.estrategias_activas,
                min_puntuacion=200
            )

            if mejor:
                st.session_state.activo_seleccionado = mejor
                st.session_state.alerta = f"🔔 {mejor['asset']} - Preparándose: cumple {len(mejor['estrategias'])} estrategias. Señal inminente."
                st.session_state.log.append(f"✅ Activo seleccionado: {mejor['asset']} (puntuación {mejor['puntuacion']})")
            else:
                st.session_state.log.append("⚠️ No se encontraron activos con suficientes estrategias.")

            st.session_state.indice_ronda += 1
            time.sleep(pausa_entre_rondas)
            st.rerun()

else:
    st.info("🔒 Conéctate a IQ Option para comenzar.")

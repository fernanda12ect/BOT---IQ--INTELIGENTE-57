import streamlit as st
import pandas as pd
import time
from datetime import datetime, timedelta
import pytz
from iqoptionapi.stable_api import IQ_Option
from bot import predecir_proxima_vela, obtener_velas_1min

st.set_page_config(
    page_title="Predictor de Velas",
    page_icon="🔮",
    layout="wide"
)

st.title("🔮 Predictor de la Próxima Vela (1 minuto)")

# Inicializar session_state
if 'api' not in st.session_state:
    st.session_state.api = None
if 'conectado' not in st.session_state:
    st.session_state.conectado = False
if 'prediciendo' not in st.session_state:
    st.session_state.prediciendo = False

def conectar(email, password):
    try:
        api = IQ_Option(email, password)
        check, reason = api.connect()
        if check:
            st.session_state.api = api
            st.session_state.conectado = True
            st.success("Conectado")
        else:
            st.error(f"Error: {reason}")
    except Exception as e:
        st.error(f"Excepción: {e}")

def desconectar():
    st.session_state.api = None
    st.session_state.conectado = False
    st.session_state.prediciendo = False

# Sidebar
with st.sidebar:
    st.header("⚙️ Configuración")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Conectar"):
            conectar(email, password)
    with col2:
        if st.button("Desconectar"):
            desconectar()
    
    st.divider()
    if st.session_state.conectado:
        activo = st.text_input("Activo (ej: EURUSD-OTC)", value="EURUSD-OTC")
        ventana = st.slider("Ventana de presión (minutos)", 3, 10, 5, 1)
        if st.button("Iniciar predicción"):
            st.session_state.prediciendo = True
        if st.button("Detener"):
            st.session_state.prediciendo = False

# Área principal
if st.session_state.conectado:
    st.success(f"Conectado - Analizando {activo if 'activo' in locals() else '...'}")
    
    # Mostrar última predicción
    placeholder = st.empty()
    
    if st.session_state.prediciendo:
        while st.session_state.prediciendo:
            now = datetime.now()
            # Esperar hasta el segundo 50 para predecir el próximo minuto
            if now.second >= 50:
                direccion, fuerza = predecir_proxima_vela(st.session_state.api, activo, ventana)
                if direccion:
                    with placeholder.container():
                        st.markdown(f"""
                        ## Predicción para el próximo minuto
                        - **Dirección**: {direccion}
                        - **Fuerza**: {fuerza:.1f}%
                        - **Hora**: {now.strftime('%H:%M:%S')}
                        """)
                        if fuerza > 70:
                            st.markdown("🔥 **Señal muy fuerte**")
                        elif fuerza > 50:
                            st.markdown("⚡ **Señal moderada**")
                        else:
                            st.markdown("🌊 **Señal débil**")
                else:
                    placeholder.info("No hay suficientes datos para predecir.")
                
                # Esperar hasta el próximo minuto (evitar múltiples predicciones)
                time.sleep(5)
            else:
                # Mostrar cuenta regresiva
                segundos_restantes = 50 - now.second
                placeholder.info(f"Próxima predicción en {segundos_restantes} segundos...")
                time.sleep(1)
    else:
        st.info("Presiona 'Iniciar predicción' para comenzar.")
else:
    st.warning("Conéctate primero.")

import streamlit as st
import pandas as pd
import time
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import pytz
from iqoptionapi.stable_api import IQ_Option
from bot import (
    seleccionar_activo_confiable,
    analizar_vela
)

st.set_page_config(
    page_title="Bot de Trading 1 minuto - Niveles y Fuerza",
    page_icon="📈",
    layout="wide"
)

# Estilos CSS
st.markdown("""
<style>
    .stApp { background-color: #0b0f17; color: #e0e0e0; }
    section[data-testid="stSidebar"] { background-color: #1a1f2b; border-right: 1px solid #2a2f3a; }
    div[data-testid="stMetric"] { background-color: #1e2430; border-radius: 8px; padding: 15px; border-left: 4px solid #00a3ff; }
    .stButton > button { background-color: #2a2f3a; color: white; border: 1px solid #3a4050; border-radius: 5px; padding: 10px 20px; font-weight: 500; }
    .stButton > button:hover { background-color: #3a4050; border-color: #00a3ff; }
    .senal-box {
        background-color: #1e2a3a;
        border-radius: 10px;
        padding: 20px;
        margin: 10px 0;
        border-left: 6px solid;
    }
    .call { border-color: #00ff88; }
    .put { border-color: #ff4b4b; }
    .neutral { border-color: #ffaa00; }
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
if 'activo_actual' not in st.session_state:
    st.session_state.activo_actual = None
if 'monitoreando' not in st.session_state:
    st.session_state.monitoreando = False
if 'ultimo_analisis' not in st.session_state:
    st.session_state.ultimo_analisis = None
if 'senal_actual' not in st.session_state:
    st.session_state.senal_actual = None
if 'log' not in st.session_state:
    st.session_state.log = []

# Lista de activos a monitorear (puede ampliarse)
ACTIVOS_PREDEFINIDOS = [
    "BTCUSD", "ETHUSD", "SOLUSD", "BNBUSD", "XRPUSD",
    "EURUSD", "GBPUSD", "USDJPY"
]

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
    st.markdown("## ⚙️ Configuración")
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

    st.divider()
    st.markdown("### 🎯 Selección de activos")
    activos_seleccionados = st.multiselect(
        "Activos a analizar",
        ACTIVOS_PREDEFINIDOS,
        default=["BTCUSD", "ETHUSD", "SOLUSD"]
    )

    if st.button("🔄 Buscar activo más confiable", use_container_width=True):
        if st.session_state.conectado and activos_seleccionados:
            with st.spinner("Analizando activos..."):
                mejor = seleccionar_activo_confiable(st.session_state.api, activos_seleccionados)
                if mejor:
                    st.session_state.activo_actual = mejor
                    st.session_state.log.append(f"✅ Activo seleccionado: {mejor}")
                    st.rerun()
                else:
                    st.warning("No se encontró ningún activo confiable")

    if st.session_state.activo_actual:
        st.info(f"📊 Activo actual: {st.session_state.activo_actual}")
        if not st.session_state.monitoreando:
            if st.button("▶️ INICIAR MONITOREO", type="primary"):
                st.session_state.monitoreando = True
                st.rerun()
        else:
            if st.button("⏹️ DETENER", type="secondary"):
                st.session_state.monitoreando = False
                st.rerun()

    if st.session_state.conectado:
        st.metric("💰 Saldo", f"${st.session_state.saldo:.2f}")

# Área principal
if st.session_state.conectado:
    if st.session_state.activo_actual:
        st.title(f"📈 Análisis de {st.session_state.activo_actual} - Vela 1 min")

        # Columna de señal actual
        if st.session_state.senal_actual:
            s = st.session_state.senal_actual
            color_clase = "call" if s['direccion'] == 'CALL' else "put" if s['direccion'] == 'PUT' else "neutral"
            st.markdown(f"""
            <div class="senal-box {color_clase}">
                <h3>{'🔵 SEÑAL COMPRA' if s['direccion'] == 'CALL' else '🔴 SEÑAL VENTA' if s['direccion'] == 'PUT' else '⚪ SIN SEÑAL'}</h3>
                <p><strong>Fuerza:</strong> {s['fuerza']:.1f}/10</p>
                <p><strong>Nivel roto:</strong> {s['nivel_ruptura'] if s['nivel_ruptura'] else 'Ninguno'}</p>
                <p><strong>Volumen ratio:</strong> {s['vol_ratio']:.2f}</p>
            </div>
            """, unsafe_allow_html=True)

        # Gráfico
        grafico_placeholder = st.empty()

        # Log
        with st.expander("📋 Log de eventos", expanded=False):
            for linea in st.session_state.log[-20:]:
                st.text(linea)

        # Bucle de monitoreo
        if st.session_state.monitoreando:
            # Sincronizar con el segundo 59
            now = datetime.now(ecuador)
            segundo = now.second
            if segundo < 59:
                segundos_restantes = 59 - segundo
                st.info(f"⏳ Próximo análisis en {segundos_restantes} segundos...")
                time.sleep(1)
                st.rerun()
            else:
                # Realizar análisis
                with st.spinner("Analizando vela..."):
                    resultado = analizar_vela(st.session_state.api, st.session_state.activo_actual)
                    if resultado:
                        st.session_state.ultimo_analisis = resultado
                        # Generar señal si corresponde
                        if resultado['senal']:
                            st.session_state.senal_actual = {
                                'direccion': resultado['senal'],
                                'fuerza': resultado['fuerza'],
                                'nivel_ruptura': resultado['nivel_ruptura'],
                                'vol_ratio': resultado['vela_actual']['vol_ratio']
                            }
                            st.session_state.log.append(f"🚀 SEÑAL {resultado['senal']} en {resultado['asset']} con fuerza {resultado['fuerza']:.1f}")
                        else:
                            st.session_state.senal_actual = None
                            st.session_state.log.append("🔍 Sin señal en esta vela")

                        # Actualizar gráfico
                        # Obtener últimas 50 velas para el gráfico
                        candles = st.session_state.api.get_candles(st.session_state.activo_actual, 60, 50, time.time())
                        if candles:
                            df = pd.DataFrame(candles)
                            df['time'] = pd.to_datetime(df['from'], unit='s')
                            fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                                                vertical_spacing=0.05,
                                                row_heights=[0.7, 0.3])
                            # Velas
                            fig.add_trace(go.Candlestick(x=df['time'],
                                                          open=df['open'],
                                                          high=df['max'],
                                                          low=df['min'],
                                                          close=df['close'],
                                                          name='Precio'),
                                          row=1, col=1)
                            # Niveles ocultos
                            for nivel in resultado['niveles_ocultos']:
                                fig.add_hline(y=nivel, line_dash="dash", line_color="cyan", row=1, col=1)
                            # Soportes
                            for s in resultado['soportes']:
                                fig.add_hline(y=s, line_dash="dot", line_color="green", row=1, col=1)
                            # Resistencias
                            for r in resultado['resistencias']:
                                fig.add_hline(y=r, line_dash="dot", line_color="red", row=1, col=1)
                            # Volumen
                            colors = ['green' if row['close'] > row['open'] else 'red' for _, row in df.iterrows()]
                            fig.add_trace(go.Bar(x=df['time'], y=df['volume'], name='Volumen', marker_color=colors),
                                          row=2, col=1)
                            fig.update_layout(title=f"{st.session_state.activo_actual} - Análisis en tiempo real",
                                              xaxis_rangeslider_visible=False,
                                              template='plotly_dark',
                                              height=700)
                            grafico_placeholder.plotly_chart(fig, use_container_width=True)
                    else:
                        st.error("Error en el análisis")
                # Esperar al siguiente minuto (para no repetir)
                time.sleep(2)
                st.rerun()
    else:
        st.info("Selecciona un activo confiable en la barra lateral.")
else:
    st.info("🔒 Conéctate a IQ Option para comenzar.")

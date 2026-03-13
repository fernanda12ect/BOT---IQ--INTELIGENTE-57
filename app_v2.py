import streamlit as st
import pandas as pd
import time
from datetime import datetime, timedelta
import pytz
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from iqoptionapi.stable_api import IQ_Option
from bot_v2 import (
    calcular_indicadores,
    detectar_niveles_sr,
    detectar_niveles_ocultos,
    analizar_fuerza_y_senal,
    seleccionar_activo_confiable,
    obtener_activos_abiertos
)

st.set_page_config(
    page_title="NEUROTRADER V2 - 1 MINUTO",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilos CSS (idénticos a los que ya usamos)
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
if 'activo_objetivo' not in st.session_state:
    st.session_state.activo_objetivo = None
if 'senal_actual' not in st.session_state:
    st.session_state.senal_actual = None
if 'datos_grafico' not in st.session_state:
    st.session_state.datos_grafico = None
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
    st.session_state.activo_objetivo = None

def crear_grafico(df, activo, niveles_sr, niveles_ocultos, senal):
    """Crea un gráfico de velas con Plotly, incluyendo niveles y anotaciones."""
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        vertical_spacing=0.05,
                        row_heights=[0.7, 0.3])

    # Velas
    fig.add_trace(go.Candlestick(x=df.index,
                                  open=df['open'],
                                  high=df['high'],
                                  low=df['low'],
                                  close=df['close'],
                                  name='Precio',
                                  increasing_line_color='#00ff88',
                                  decreasing_line_color='#ff4b4b'),
                  row=1, col=1)

    # EMAs (opcional, para referencia)
    fig.add_trace(go.Scatter(x=df.index, y=df['ema9'], line=dict(color='#ffaa00', width=1), name='EMA9'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['ema21'], line=dict(color='#00a3ff', width=1), name='EMA21'), row=1, col=1)

    # Niveles de soporte/resistencia
    for nivel in niveles_sr:
        color = '#00ff88' if nivel['tipo'] == 'soporte' else '#ff4b4b'
        fig.add_hline(y=nivel['precio'], line_dash="dash", line_color=color,
                      annotation_text=f"{nivel['tipo']} ({nivel['toques']})", row=1, col=1)

    # Niveles ocultos
    for nivel in niveles_ocultos:
        fig.add_hline(y=nivel['precio'], line_dash="dot", line_color='#aa88ff',
                      annotation_text="oculto", row=1, col=1)

    # Volumen
    colors = ['#00ff88' if row['close'] > row['open'] else '#ff4b4b' for _, row in df.iterrows()]
    fig.add_trace(go.Bar(x=df.index, y=df['volume'], name='Volumen', marker_color=colors), row=2, col=1)

    # Anotación de señal
    if senal:
        fig.add_annotation(x=df.index[-1], y=df['high'].iloc[-1] * 1.02,
                           text=f"⚡ SEÑAL: {senal['direccion']} (Fuerza {senal['fuerza']})",
                           showarrow=True, arrowhead=1, bgcolor="black", font=dict(color="white"))

    fig.update_layout(title=f"{activo} - Análisis en tiempo real",
                      xaxis_rangeslider_visible=False,
                      template='plotly_dark',
                      height=700)
    fig.update_xaxes(title_text="Tiempo", row=2, col=1)
    fig.update_yaxes(title_text="Precio", row=1, col=1)
    fig.update_yaxes(title_text="Volumen", row=2, col=1)

    return fig

# Sidebar
with st.sidebar:
    st.markdown("## ⚡ NEUROTRADER V2")
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
    if st.session_state.conectado:
        if not st.session_state.monitoreando:
            if st.button("▶️ INICIAR MONITOREO", use_container_width=True, type="primary"):
                st.session_state.monitoreando = True
                st.session_state.log.append("🚀 Monitoreo iniciado")
                # Seleccionar activo objetivo al arrancar
                with st.spinner("Analizando activos para elegir el más confiable..."):
                    activo = seleccionar_activo_confiable(st.session_state.api, tipo_mercado)
                    if activo:
                        st.session_state.activo_objetivo = activo
                        st.session_state.log.append(f"✅ Activo objetivo: {activo}")
                    else:
                        st.session_state.activo_objetivo = None
                        st.session_state.log.append("⚠️ No se encontró ningún activo confiable.")
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
        st.metric("Activo objetivo", st.session_state.activo_objetivo or "Ninguno")
    with col3:
        st.metric("Señales generadas", len([s for s in st.session_state.log if "⚡" in s]))

    # Mostrar señal actual si existe
    if st.session_state.senal_actual:
        s = st.session_state.senal_actual
        card_class = "call-card" if s['direccion'] == "CALL" else "put-card"
        st.markdown(f"""
        <div class="signal-card {card_class}">
            <div class="signal-title">{'🔵 COMPRA (CALL)' if s['direccion'] == 'CALL' else '🔴 VENTA (PUT)'}</div>
            <div class="signal-detail"><strong>Activo:</strong> {s['asset']}</div>
            <div class="signal-detail"><strong>Fuerza:</strong> {s['fuerza']}/10</div>
            <div class="signal-detail"><strong>Nivel activador:</strong> {s['nivel_activador'] or 'N/A'}</div>
            <div class="signal-detail"><strong>Descripción:</strong> {s['descripcion']}</div>
            <div class="signal-detail"><strong>Entrada sugerida:</strong> Próxima vela (1 min)</div>
        </div>
        """, unsafe_allow_html=True)

    # Gráfico
    if st.session_state.datos_grafico is not None:
        fig = crear_grafico(st.session_state.datos_grafico,
                            st.session_state.activo_objetivo,
                            st.session_state.niveles_sr,
                            st.session_state.niveles_ocultos,
                            st.session_state.senal_actual)
        st.plotly_chart(fig, use_container_width=True)

    # Log
    with st.expander("📋 Log de eventos", expanded=True):
        for linea in st.session_state.log[-20:]:
            st.text(linea)

    # Lógica de monitoreo en ciclo de 1 minuto
    if st.session_state.monitoreando and st.session_state.activo_objetivo:
        now = datetime.now(ecuador)
        segundo = now.second

        # Ejecutar análisis en el segundo 59 (o 58 para anticipación)
        if segundo >= 58:
            # Obtener datos del activo objetivo
            asset = st.session_state.activo_objetivo
            try:
                # Velas de 1 minuto (últimas 60 para tener contexto)
                candles = st.session_state.api.get_candles(asset, 60, 60, time.time())
                if candles and len(candles) > 30:
                    df = pd.DataFrame(candles)
                    for col in ['open', 'max', 'min', 'close', 'volume']:
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                    df.dropna(inplace=True)
                    if len(df) > 30:
                        df = calcular_indicadores(df)
                        ultima_vela = df.iloc[-1]
                        # Detectar niveles
                        niveles_sr = detectar_niveles_sr(df, num_toques=2)
                        niveles_ocultos = detectar_niveles_ocultos(df, ventana=30)
                        # Analizar fuerza y generar señal
                        direccion, fuerza, nivel_activador, desc = analizar_fuerza_y_senal(
                            ultima_vela, niveles_sr, niveles_ocultos
                        )
                        # Guardar datos para el gráfico
                        st.session_state.datos_grafico = df.tail(30)  # últimas 30 velas
                        st.session_state.niveles_sr = niveles_sr
                        st.session_state.niveles_ocultos = niveles_ocultos
                        if direccion:
                            st.session_state.senal_actual = {
                                'asset': asset,
                                'direccion': direccion,
                                'fuerza': fuerza,
                                'nivel_activador': nivel_activador,
                                'descripcion': desc
                            }
                            st.session_state.log.append(f"⚡ SEÑAL: {asset} - {direccion} (Fuerza {fuerza})")
                        else:
                            st.session_state.senal_actual = None
                else:
                    st.session_state.log.append(f"⚠️ No se pudieron obtener datos suficientes de {asset}.")
            except Exception as e:
                st.session_state.log.append(f"❌ Error analizando {asset}: {e}")

            # Esperar hasta el siguiente minuto para no repetir
            time.sleep(2)
            st.rerun()
        else:
            # Mostrar cuenta regresiva
            seg_rest = 59 - segundo
            st.info(f"⏳ Próximo análisis en {seg_rest} segundos...")
            time.sleep(1)
            st.rerun()
    elif st.session_state.monitoreando and not st.session_state.activo_objetivo:
        # No hay activo objetivo, intentar seleccionar uno de nuevo
        st.session_state.log.append("🔄 Re-evaluando activos...")
        activo = seleccionar_activo_confiable(st.session_state.api, tipo_mercado)
        if activo:
            st.session_state.activo_objetivo = activo
            st.session_state.log.append(f"✅ Nuevo activo objetivo: {activo}")
        else:
            st.session_state.log.append("⚠️ No se encontró ningún activo confiable.")
        time.sleep(10)
        st.rerun()

else:
    st.info("🔒 Conéctate a IQ Option para comenzar.")

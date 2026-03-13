import streamlit as st
import pandas as pd
import time
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import pytz
from iqoptionapi.stable_api import IQ_Option
from bot import (
    obtener_activos_abiertos,
    seleccionar_mejor_activo,
    detectar_niveles_ocultos,
    detectar_zonas_balance,
    detectar_soportes_resistencias,
    analizar_fuerza_vela,
    calcular_indicadores
)

st.set_page_config(
    page_title="TRADING AUTÓNOMO 1MIN",
    page_icon="📈",
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
if 'activo_actual' not in st.session_state:
    st.session_state.activo_actual = None  # dict con info del activo seleccionado
if 'senal_actual' not in st.session_state:
    st.session_state.senal_actual = None  # última señal generada
if 'df_velas' not in st.session_state:
    st.session_state.df_velas = None  # DataFrame con velas para el gráfico
if 'log' not in st.session_state:
    st.session_state.log = []
if 'proximo_segundo_59' not in st.session_state:
    st.session_state.proximo_segundo_59 = None

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
    st.session_state.activo_actual = None
    st.session_state.senal_actual = None

def crear_grafico(df, niveles_ocultos, niveles_sr, zonas_balance, senal):
    """
    Crea un gráfico de velas con líneas de niveles y marcadores de señal.
    """
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        vertical_spacing=0.05,
                        row_heights=[0.7, 0.3],
                        subplot_titles=(f"Velas de 1 min - {st.session_state.activo_actual['asset'] if st.session_state.activo_actual else 'Sin activo'}", "Volumen"))

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

    # Líneas de niveles ocultos
    for nivel in niveles_ocultos:
        fig.add_hline(y=nivel, line_dash="dash", line_color="orange", row=1, col=1)

    # Líneas de soportes/resistencias
    for nivel in niveles_sr:
        color = "green" if nivel['tipo'] == 'soporte' else "red"
        fig.add_hline(y=nivel['precio'], line_dash="solid", line_color=color, row=1, col=1)

    # Marcadores de zonas de balance
    for idx in zonas_balance:
        if idx < len(df):
            fig.add_vline(x=df.index[idx], line_dash="dot", line_color="yellow", row=1, col=1)

    # Señal actual (si existe)
    if senal:
        color = "#00ff88" if senal['direccion'] == 'CALL' else "#ff4b4b"
        fig.add_annotation(x=df.index[-1], y=df['close'].iloc[-1],
                           text=f"SEÑAL {senal['direccion']} (fuerza {senal['fuerza']})",
                           showarrow=True, arrowhead=1, ax=0, ay=-40,
                           font=dict(color=color, size=12),
                           bgcolor="black", opacity=0.8)

    # Volumen
    colors = ['#00ff88' if close > open else '#ff4b4b' for close, open in zip(df['close'], df['open'])]
    fig.add_trace(go.Bar(x=df.index, y=df['volume'], name='Volumen', marker_color=colors), row=2, col=1)

    fig.update_layout(title=f"Análisis en tiempo real - {st.session_state.activo_actual['asset'] if st.session_state.activo_actual else 'Buscando activo...'}",
                      xaxis_rangeslider_visible=False,
                      template='plotly_dark',
                      height=700)
    return fig

# Sidebar
with st.sidebar:
    st.markdown("## 📈 TRADING AUTÓNOMO 1MIN")
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

    tipo_mercado = st.selectbox("Tipo de mercado", ["OTC", "REAL", "AMBOS"], index=2)
    min_confiabilidad = st.slider("Puntaje mínimo de confiabilidad", 0, 100, 30, 5)
    anticipacion = st.slider("Anticipación de señal (segundos antes del cierre)", 1, 10, 2, 1)

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
        if st.session_state.activo_actual:
            st.metric("Activo objetivo", st.session_state.activo_actual['asset'])
        else:
            st.metric("Activo objetivo", "Buscando...")
    with col3:
        st.metric("Señales generadas", len([s for s in st.session_state.log if "SEÑAL" in s]))

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
            <div class="signal-detail"><strong>Fuerza:</strong> {s['fuerza']}/10</div>
            <div class="signal-detail"><strong>Nivel activado:</strong> {s.get('nivel', 'Ninguno')}</div>
        </div>
        """, unsafe_allow_html=True)

    # Log de eventos
    with st.expander("📋 Log de eventos", expanded=True):
        for linea in st.session_state.log[-20:]:
            st.text(linea)

    # Lógica principal
    if st.session_state.monitoreando:
        now = datetime.now(ecuador)
        segundo = now.second

        # Calcular el próximo segundo 59
        if st.session_state.proximo_segundo_59 is None:
            # Si ya pasó el 59, programar para el próximo minuto
            if segundo >= 59:
                st.session_state.proximo_segundo_59 = now.replace(second=59, microsecond=0) + timedelta(minutes=1)
            else:
                st.session_state.proximo_segundo_59 = now.replace(second=59, microsecond=0)

        # Si es hora de evaluar (segundo 59 - anticipacion)
        segundo_objetivo = 59 - anticipacion
        if segundo >= segundo_objetivo and now >= st.session_state.proximo_segundo_59 - timedelta(seconds=anticipacion):
            # Estamos en la ventana de evaluación
            st.info(f"⏳ Evaluando en el segundo {segundo}...")

            # Si no hay activo seleccionado, buscar el mejor
            if st.session_state.activo_actual is None:
                with st.spinner("Buscando el activo más confiable..."):
                    activos = obtener_activos_abiertos(st.session_state.api, tipo_mercado)
                    mejor = seleccionar_mejor_activo(st.session_state.api, activos)
                    if mejor and mejor['puntaje'] >= min_confiabilidad:
                        st.session_state.activo_actual = mejor
                        st.session_state.log.append(f"✅ Activo seleccionado: {mejor['asset']} (puntaje {mejor['puntaje']:.1f})")
                    else:
                        st.session_state.log.append("⚠️ No se encontró activo con suficiente confiabilidad.")
                        # Programar próxima evaluación en 1 minuto
                        st.session_state.proximo_segundo_59 += timedelta(minutes=1)
                        time.sleep(1)
                        st.rerun()

            # Si hay activo, analizar la última vela
            if st.session_state.activo_actual:
                asset = st.session_state.activo_actual['asset']
                # Obtener últimas 50 velas de 1 minuto
                candles = st.session_state.api.get_candles(asset, 60, 50, time.time())
                if candles and len(candles) >= 30:
                    df = pd.DataFrame(candles)
                    for col in ['open', 'max', 'min', 'close', 'volume']:
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                    df.dropna(inplace=True)
                    if len(df) >= 30:
                        df = calcular_indicadores(df)
                        st.session_state.df_velas = df

                        # Detectar niveles
                        niveles_ocultos = detectar_niveles_ocultos(df)
                        niveles_sr = detectar_soportes_resistencias(df)
                        zonas_balance = detectar_zonas_balance(df)

                        # Analizar la última vela
                        analisis = analizar_fuerza_vela(df, -1)
                        if analisis and analisis['fuerza'] >= 7:  # umbral de fuerza
                            # Generar señal
                            entrada = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
                            st.session_state.senal_actual = {
                                'asset': asset,
                                'direccion': analisis['direccion'],
                                'entrada': entrada.strftime("%H:%M:%S"),
                                'fuerza': analisis['fuerza'],
                                'nivel': analisis['nivel_activado'] or "Nivel no especificado"
                            }
                            st.session_state.log.append(f"🚀 SEÑAL GENERADA: {asset} - {analisis['direccion']} a las {entrada.strftime('%H:%M:%S')}")

                # Programar próxima evaluación (en el siguiente minuto)
                st.session_state.proximo_segundo_59 += timedelta(minutes=1)
                time.sleep(1)
                st.rerun()
        else:
            # Esperar hasta el momento adecuado
            if st.session_state.proximo_segundo_59:
                segundos_restantes = (st.session_state.proximo_segundo_59 - now).total_seconds() - anticipacion
                if segundos_restantes > 0:
                    st.info(f"⏳ Próxima evaluación en {int(segundos_restantes)} segundos...")
                else:
                    st.info("⏳ Preparando evaluación...")
            time.sleep(1)
            st.rerun()

    # Mostrar gráfico si hay datos
    if st.session_state.df_velas is not None and st.session_state.activo_actual:
        # Detectar niveles para el gráfico (usamos los últimos datos)
        df = st.session_state.df_velas
        niveles_ocultos = detectar_niveles_ocultos(df)
        niveles_sr = detectar_soportes_resistencias(df)
        zonas_balance = detectar_zonas_balance(df)
        fig = crear_grafico(df, niveles_ocultos, niveles_sr, zonas_balance, st.session_state.senal_actual)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Esperando datos para mostrar el gráfico...")

else:
    st.info("🔒 Conéctate a IQ Option para comenzar.")

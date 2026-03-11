import streamlit as st
import pandas as pd
import numpy as np
import time
from datetime import datetime, timedelta
import pytz
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from iqoptionapi.stable_api import IQ_Option
from bot import evaluar_activo, ESTRATEGIAS, calcular_indicadores

# Configuración de página
st.set_page_config(
    page_title="NEUROTRADER SIGNALS",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilos CSS personalizados
st.markdown("""
<style>
    .stApp { background-color: #0b0f17; color: #e0e0e0; }
    section[data-testid="stSidebar"] { background-color: #1a1f2b; border-right: 1px solid #2a2f3a; }
    div[data-testid="stMetric"] { background-color: #1e2430; border-radius: 8px; padding: 15px; border-left: 4px solid #00a3ff; }
    .stButton > button { background-color: #2a2f3a; color: white; border: 1px solid #3a4050; border-radius: 5px; padding: 10px 20px; font-weight: 500; }
    .stButton > button:hover { background-color: #3a4050; border-color: #00a3ff; }
    .call-signal { background-color: #1a3a1a; border-left: 6px solid #00ff88; padding: 15px; margin: 5px 0; border-radius: 5px; }
    .put-signal { background-color: #3a1a1a; border-left: 6px solid #ff4b4b; padding: 15px; margin: 5px 0; border-radius: 5px; }
    .signal-header { font-size: 1.2rem; font-weight: bold; margin-bottom: 5px; }
    .signal-time { color: #888; font-size: 0.9rem; }
    hr { border-color: #2a2f3a; }
    .selected-assets { background-color: #1e2a3a; padding: 15px; border-radius: 8px; margin-bottom: 20px; border-left: 4px solid #00a3ff; }
</style>
""", unsafe_allow_html=True)

# Inicializar variables de sesión
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
    st.session_state.activos_seleccionados = []  # lista de activos que están siendo monitoreados
if 'señales' not in st.session_state:
    st.session_state.señales = []  # lista de dicts con señal, cada uno: {'fecha':..., 'activo':..., 'direccion':..., 'estrategia':..., 'entrada':..., 'vencimiento':..., 'estado': 'activa' o 'cerrada'}
if 'log' not in st.session_state:
    st.session_state.log = []
if 'estrategias_activas' not in st.session_state:
    st.session_state.estrategias_activas = [nombre for nombre, _ in ESTRATEGIAS[:5]]
if 'datos_grafico' not in st.session_state:
    st.session_state.datos_grafico = None

# Zona horaria
ecuador = pytz.timezone("America/Guayaquil")

# =========================
# FUNCIONES AUXILIARES
# =========================
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
            st.error(f"Error de conexión: {reason}")
            return False
    except Exception as e:
        st.error(f"Excepción: {e}")
        return False

def desconectar():
    st.session_state.api = None
    st.session_state.conectado = False
    st.session_state.monitoreando = False
    st.session_state.log.append("🔌 Desconectado")

def obtener_activos():
    if not st.session_state.api:
        return []
    try:
        open_time = st.session_state.api.get_all_open_time()
        activos = []
        if 'binary' in open_time:
            for asset, data in open_time['binary'].items():
                if data.get('open', False):
                    activos.append(asset)
        return activos
    except:
        return []

def seleccionar_activos_confiables(api, num_activos=4):
    """Selecciona los num_activos activos más prometedores basado en análisis rápido."""
    todos = obtener_activos()
    if not todos:
        return []
    puntuaciones = []
    for asset in todos[:30]:  # limitamos a 30 para no saturar
        try:
            candles = api.get_candles(asset, 300, 50, time.time())
            if not candles or len(candles) < 30:
                continue
            df = pd.DataFrame(candles)
            for col in ['open', 'max', 'min', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            df.dropna(inplace=True)
            if len(df) < 30:
                continue
            df = calcular_indicadores(df)
            ultimo = df.iloc[-1]
            # Puntuación simple: ADX alto indica tendencia, volumen alto indica liquidez
            puntuacion = (ultimo['adx'] if not np.isnan(ultimo['adx']) else 0) + (ultimo['vol_ratio'] * 10)
            puntuaciones.append((puntuacion, asset))
            time.sleep(0.1)
        except:
            continue
    puntuaciones.sort(reverse=True)
    return [asset for _, asset in puntuaciones[:num_activos]]

def crear_grafico_velas(df, activo):
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        vertical_spacing=0.05,
                        row_heights=[0.7, 0.3])
    fig.add_trace(go.Candlestick(x=df.index,
                                  open=df['open'],
                                  high=df['high'],
                                  low=df['low'],
                                  close=df['close'],
                                  name='Precio',
                                  increasing_line_color='#00ff88',
                                  decreasing_line_color='#ff4b4b'),
                  row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['ema9'], line=dict(color='#ffaa00', width=1), name='EMA9'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['ema21'], line=dict(color='#00a3ff', width=1), name='EMA21'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['bb_upper'], line=dict(color='#888', width=1, dash='dash'), name='BB Sup'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['bb_lower'], line=dict(color='#888', width=1, dash='dash'), name='BB Inf'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['rsi'], line=dict(color='#aa88ff', width=1), name='RSI'), row=2, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="#ff4b4b", row=2, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="#00ff88", row=2, col=1)
    fig.update_layout(title=f"{activo} - Análisis",
                      xaxis_rangeslider_visible=False,
                      template='plotly_dark',
                      height=500,
                      margin=dict(l=50, r=50, t=50, b=50))
    return fig

# =========================
# BARRA LATERAL
# =========================
with st.sidebar:
    st.markdown("## 📈 NEUROTRADER SIGNALS")
    st.markdown("---")

    st.markdown("### 🔌 Conexión IQ Option")
    email = st.text_input("Correo electrónico", placeholder="tu@email.com")
    password = st.text_input("Contraseña", type="password", placeholder="********")

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

    st.markdown("### 💳 Tipo de cuenta")
    tipo_cuenta = st.radio("", ["PRACTICE", "REAL"], index=0, horizontal=True)
    if tipo_cuenta != st.session_state.tipo_cuenta and st.session_state.conectado:
        st.session_state.tipo_cuenta = tipo_cuenta
        st.session_state.api.change_balance(tipo_cuenta)
        saldo = st.session_state.api.get_balance()
        st.session_state.saldo = saldo if saldo is not None else 0.0
        st.session_state.log.append(f"🔄 Cambio a cuenta {tipo_cuenta} - Saldo: {st.session_state.saldo}")

    st.markdown("---")

    st.markdown("### 🎯 Estrategias activas")
    nuevas_estrategias = []
    for nombre, _ in ESTRATEGIAS:
        activa = st.checkbox(nombre, value=(nombre in st.session_state.estrategias_activas))
        if activa:
            nuevas_estrategias.append(nombre)
    st.session_state.estrategias_activas = nuevas_estrategias

    st.markdown("---")

    st.markdown("### ⚙️ Control")
    if st.session_state.conectado:
        if not st.session_state.monitoreando:
            if st.button("▶️ INICIAR MONITOREO", use_container_width=True, type="primary"):
                st.session_state.monitoreando = True
                st.session_state.log.append("🚀 Monitoreo iniciado")
                # Seleccionar activos confiables al inicio
                with st.spinner("Seleccionando activos confiables..."):
                    seleccionados = seleccionar_activos_confiables(st.session_state.api, num_activos=4)
                    st.session_state.activos_seleccionados = seleccionados
                    st.session_state.log.append(f"✅ Activos seleccionados: {', '.join(seleccionados)}")
                st.rerun()
        else:
            if st.button("⏹️ DETENER MONITOREO", use_container_width=True, type="secondary"):
                st.session_state.monitoreando = False
                st.session_state.log.append("🛑 Monitoreo detenido")
                st.rerun()

    if st.session_state.conectado:
        st.markdown("---")
        st.metric("Saldo", f"${st.session_state.saldo:.2f}")

# =========================
# ÁREA PRINCIPAL
# =========================
if st.session_state.conectado:
    # Cabecera con métricas
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Saldo", f"${st.session_state.saldo:.2f}")
    with col2:
        st.metric("Activos en seguimiento", len(st.session_state.activos_seleccionados))
    with col3:
        st.metric("Señales generadas", len(st.session_state.señales))

    # Mostrar activos seleccionados
    if st.session_state.activos_seleccionados:
        st.markdown(f"""
        <div class="selected-assets">
            <strong>📌 ACTIVOS SELECCIONADOS:</strong> {', '.join(st.session_state.activos_seleccionados)} – ESPERANDO PUNTO DE ENTRADA
        </div>
        """, unsafe_allow_html=True)

    # Gráfico del activo actual (opcional)
    if st.session_state.activos_seleccionados and st.session_state.datos_grafico is not None:
        fig = crear_grafico_velas(st.session_state.datos_grafico, st.session_state.activos_seleccionados[0])
        st.plotly_chart(fig, use_container_width=True)

    # Lista de señales (la más reciente arriba)
    st.subheader("📊 SEÑALES DE TRADING")
    if st.session_state.señales:
        for senal in st.session_state.señales:
            if senal['direccion'] == 'CALL':
                st.markdown(f"""
                <div class="call-signal">
                    <div class="signal-header">[{senal['fecha']}] SEÑAL ACTIVA | {senal['activo']} | 🔵 COMPRA | ENTRADA AHORA | VENCIMIENTO 5 MIN</div>
                    <div class="signal-time">Estrategia: {senal['estrategia']}</div>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div class="put-signal">
                    <div class="signal-header">[{senal['fecha']}] SEÑAL ACTIVA | {senal['activo']} | 🔴 VENTA | ENTRADA AHORA | VENCIMIENTO 5 MIN</div>
                    <div class="signal-time">Estrategia: {senal['estrategia']}</div>
                </div>
                """, unsafe_allow_html=True)
    else:
        st.info("No hay señales aún. Esperando condiciones de mercado...")

    # Historial de señales (opcional, podríamos ponerlo en un expander)
    with st.expander("📋 Historial de señales"):
        if st.session_state.señales:
            df_hist = pd.DataFrame(st.session_state.señales)
            st.dataframe(df_hist[['fecha', 'activo', 'direccion', 'estrategia']], use_container_width=True, hide_index=True)
        else:
            st.info("No hay historial.")

    # Log de eventos
    with st.expander("📋 Log de eventos", expanded=False):
        for linea in st.session_state.log[-20:]:
            st.text(linea)

    # =========================
    # LÓGICA DE MONITOREO
    # =========================
    if st.session_state.monitoreando and st.session_state.activos_seleccionados:
        now = datetime.now(ecuador)
        # Analizar cada activo seleccionado secuencialmente
        for asset in st.session_state.activos_seleccionados:
            if not st.session_state.monitoreando:
                break
            st.session_state.activo_actual = asset
            # Obtener datos para gráfico (opcional)
            try:
                candles = st.session_state.api.get_candles(asset, 300, 50, time.time())
                if candles:
                    df = pd.DataFrame(candles)
                    for col in ['open', 'max', 'min', 'close', 'volume']:
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                    df.dropna(inplace=True)
                    if len(df) > 30:
                        df = calcular_indicadores(df)
                        st.session_state.datos_grafico = df
            except:
                pass

            # Evaluar estrategias
            resultado = evaluar_activo(st.session_state.api, asset, st.session_state.estrategias_activas)
            if resultado:
                direccion, nombre_estr = resultado
                # Crear nueva señal
                nueva_senal = {
                    'fecha': now.strftime("%Y-%m-%d %H:%M:%S"),
                    'activo': asset,
                    'direccion': direccion,
                    'estrategia': nombre_estr,
                    'entrada': now.strftime("%H:%M:%S"),
                    'vencimiento': (now + timedelta(minutes=5)).strftime("%H:%M:%S"),
                    'estado': 'activa'
                }
                # Insertar al principio de la lista
                st.session_state.señales.insert(0, nueva_senal)
                st.session_state.log.append(f"📢 NUEVA SEÑAL: {asset} - {direccion} ({nombre_estr}) a las {now.strftime('%H:%M:%S')}")
                # Esperar un poco antes de seguir analizando (para no saturar)
                time.sleep(2)
            # Pequeña pausa entre activos
            time.sleep(1)
        # Al terminar de analizar todos, esperar y repetir
        time.sleep(5)
        st.rerun()
    elif st.session_state.monitoreando and not st.session_state.activos_seleccionados:
        st.warning("No hay activos seleccionados. Reintentando...")
        time.sleep(5)
        st.rerun()

else:
    st.info("🔒 Conéctate a IQ Option para comenzar.")

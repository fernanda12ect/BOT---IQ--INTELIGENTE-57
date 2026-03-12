import streamlit as st
import pandas as pd
import time
from datetime import datetime, timedelta
import pytz
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from iqoptionapi.stable_api import IQ_Option
from bot import evaluar_activo, calcular_indicadores

st.set_page_config(
    page_title="NEUROTRADER EFECTIVO",
    page_icon="🎯",
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
    .call-signal { background-color: #1a3a1a; border-left: 6px solid #00ff88; padding: 15px; margin: 5px 0; border-radius: 5px; }
    .put-signal { background-color: #3a1a1a; border-left: 6px solid #ff4b4b; padding: 15px; margin: 5px 0; border-radius: 5px; }
    .signal-header { font-size: 1.2rem; font-weight: bold; margin-bottom: 5px; }
    .signal-time { color: #888; font-size: 0.9rem; }
    .selected-assets { background-color: #1e2a3a; padding: 15px; border-radius: 8px; margin-bottom: 20px; border-left: 4px solid #00a3ff; }
</style>
""", unsafe_allow_html=True)

# Inicializar sesión
if 'api' not in st.session_state:
    st.session_state.api = None
if 'conectado' not in st.session_state:
    st.session_state.conectado = False
if 'tipo_cuenta' not in st.session_state:
    st.session_state.tipo_cuenta = "PRACTICE"
if 'monitoreando' not in st.session_state:
    st.session_state.monitoreando = False
if 'activo_actual' not in st.session_state:
    st.session_state.activo_actual = None
if 'activos_seleccionados' not in st.session_state:
    st.session_state.activos_seleccionados = []  # lista de activos que están siendo monitoreados
if 'señales' not in st.session_state:
    st.session_state.señales = []  # lista de dicts con señal
if 'log' not in st.session_state:
    st.session_state.log = []
if 'datos_grafico' not in st.session_state:
    st.session_state.datos_grafico = None
if 'operacion_en_curso' not in st.session_state:
    st.session_state.operacion_en_curso = None  # dict con activo, direccion, hora_entrada, vencimiento

ecuador = pytz.timezone("America/Guayaquil")

# =========================
# FUNCIONES
# =========================
def conectar(email, password):
    try:
        api = IQ_Option(email, password)
        check, reason = api.connect()
        if check:
            st.session_state.api = api
            st.session_state.conectado = True
            api.change_balance(st.session_state.tipo_cuenta)
            st.session_state.log.append("✅ Conectado")
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

def seleccionar_activos_confiables(api, num_activos=3):
    """Selecciona los activos con mayor ADX y volumen."""
    todos = obtener_activos()
    if not todos:
        return []
    candidatos = []
    for asset in todos[:30]:
        try:
            candles = api.get_candles(asset, 300, 30, time.time())
            if not candles or len(candles) < 20:
                continue
            df = pd.DataFrame(candles)
            for col in ['open', 'max', 'min', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            df.dropna(inplace=True)
            if len(df) < 20:
                continue
            df = calcular_indicadores(df)
            ultimo = df.iloc[-1]
            if ultimo['adx'] > 20 and not np.isnan(ultimo['adx']):
                candidatos.append((ultimo['adx'], asset))
            time.sleep(0.1)
        except:
            continue
    candidatos.sort(reverse=True)
    return [asset for _, asset in candidatos[:num_activos]]

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
                      height=500)
    return fig

# =========================
# BARRA LATERAL
# =========================
with st.sidebar:
    st.markdown("## 🎯 NEUROTRADER EFECTIVO")
    st.markdown("---")

    st.markdown("### 🔌 Conexión")
    email = st.text_input("Correo", placeholder="tu@email.com")
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

    st.markdown("### 💳 Tipo de cuenta")
    tipo_cuenta = st.radio("", ["PRACTICE", "REAL"], index=0, horizontal=True)
    if tipo_cuenta != st.session_state.tipo_cuenta and st.session_state.conectado:
        st.session_state.tipo_cuenta = tipo_cuenta
        st.session_state.api.change_balance(tipo_cuenta)
        st.session_state.log.append(f"🔄 Cambio a cuenta {tipo_cuenta}")

    st.markdown("---")

    st.markdown("### 🎯 Control")
    if st.session_state.conectado:
        if not st.session_state.monitoreando:
            if st.button("▶️ INICIAR MONITOREO", use_container_width=True, type="primary"):
                st.session_state.monitoreando = True
                st.session_state.log.append("🚀 Monitoreo iniciado")
                with st.spinner("Seleccionando activos confiables..."):
                    seleccionados = seleccionar_activos_confiables(st.session_state.api, num_activos=3)
                    st.session_state.activos_seleccionados = seleccionados
                    st.session_state.log.append(f"✅ Activos seleccionados: {', '.join(seleccionados)}")
                st.rerun()
        else:
            if st.button("⏹️ DETENER MONITOREO", use_container_width=True, type="secondary"):
                st.session_state.monitoreando = False
                st.session_state.operacion_en_curso = None
                st.session_state.log.append("🛑 Monitoreo detenido")
                st.rerun()

# =========================
# ÁREA PRINCIPAL
# =========================
if st.session_state.conectado:
    # Mostrar activos seleccionados
    if st.session_state.activos_seleccionados:
        st.markdown(f"""
        <div class="selected-assets">
            <strong>📌 ACTIVOS SELECCIONADOS:</strong> {', '.join(st.session_state.activos_seleccionados)}
        </div>
        """, unsafe_allow_html=True)

    # Si hay una operación en curso, mostrar su estado y esperar vencimiento
    if st.session_state.operacion_en_curso:
        op = st.session_state.operacion_en_curso
        tiempo_restante = (op['vencimiento'] - datetime.now(ecuador)).total_seconds()
        if tiempo_restante > 0:
            mins, segs = divmod(int(tiempo_restante), 60)
            st.info(f"⏳ Operación en curso en {op['activo']} - {op['direccion']} - Tiempo restante: {mins:02d}:{segs:02d}")
        else:
            # Operación vencida, liberar
            st.session_state.operacion_en_curso = None
            st.rerun()

    # Gráfico del activo actual
    if st.session_state.activo_actual and st.session_state.datos_grafico is not None:
        fig = crear_grafico_velas(st.session_state.datos_grafico, st.session_state.activo_actual)
        st.plotly_chart(fig, use_container_width=True)

    # Lista de señales (la más reciente arriba)
    st.subheader("📊 SEÑALES DE TRADING")
    if st.session_state.señales:
        for senal in st.session_state.señales:
            if senal['direccion'] == 'CALL':
                st.markdown(f"""
                <div class="call-signal">
                    <div class="signal-header">[{senal['fecha']}] {senal['activo']} | 🔵 COMPRA | ENTRADA: {senal['entrada']} | VENCIMIENTO: {senal['vencimiento']}</div>
                    <div class="signal-time">Estrategia: {senal['estrategia']}</div>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div class="put-signal">
                    <div class="signal-header">[{senal['fecha']}] {senal['activo']} | 🔴 VENTA | ENTRADA: {senal['entrada']} | VENCIMIENTO: {senal['vencimiento']}</div>
                    <div class="signal-time">Estrategia: {senal['estrategia']}</div>
                </div>
                """, unsafe_allow_html=True)
    else:
        st.info("No hay señales aún. Esperando condiciones de mercado...")

    # Log
    with st.expander("📋 Log"):
        for linea in st.session_state.log[-20:]:
            st.text(linea)

    # =========================
    # LÓGICA DE MONITOREO
    # =========================
    if st.session_state.monitoreando and st.session_state.activos_seleccionados:
        # Si hay una operación en curso, no hacer nada (esperar)
        if st.session_state.operacion_en_curso:
            time.sleep(1)
            st.rerun()
        else:
            # Analizar activos secuencialmente hasta encontrar una señal
            for asset in st.session_state.activos_seleccionados:
                if not st.session_state.monitoreando:
                    break
                st.session_state.activo_actual = asset
                # Obtener datos para gráfico
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

                resultado = evaluar_activo(st.session_state.api, asset)
                if resultado:
                    direccion, estrategia = resultado
                    ahora = datetime.now(ecuador)
                    entrada = ahora + timedelta(minutes=1)  # damos 1 minuto para prepararse
                    entrada = entrada.replace(second=0, microsecond=0)
                    vencimiento = entrada + timedelta(minutes=5)
                    nueva_senal = {
                        'fecha': ahora.strftime("%Y-%m-%d %H:%M:%S"),
                        'activo': asset,
                        'direccion': direccion,
                        'estrategia': estrategia,
                        'entrada': entrada.strftime("%H:%M:%S"),
                        'vencimiento': vencimiento.strftime("%H:%M:%S")
                    }
                    st.session_state.señales.insert(0, nueva_senal)
                    st.session_state.operacion_en_curso = {
                        'activo': asset,
                        'direccion': direccion,
                        'hora_entrada': entrada,
                        'vencimiento': vencimiento
                    }
                    st.session_state.log.append(f"📢 SEÑAL: {asset} - {direccion} a las {entrada.strftime('%H:%M:%S')}")
                    # Salir del bucle, tenemos señal
                    break
                time.sleep(1)  # pausa entre activos
            # Si no hubo señal, esperar y reintentar
            if not st.session_state.operacion_en_curso:
                time.sleep(5)
            st.rerun()
    elif st.session_state.monitoreando and not st.session_state.activos_seleccionados:
        st.warning("No hay activos seleccionados. Reintentando...")
        time.sleep(5)
        st.rerun()
else:
    st.info("🔒 Conéctate a IQ Option para comenzar.")

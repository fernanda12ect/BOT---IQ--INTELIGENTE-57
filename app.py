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
    .signal-card {
        background-color: #1e2430;
        border-radius: 10px;
        padding: 20px;
        margin: 10px 0;
        border-left: 6px solid;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }
    .signal-card.call { border-left-color: #00ff88; }
    .signal-card.put { border-left-color: #ff4b4b; }
    .signal-title {
        font-size: 1.8rem;
        font-weight: bold;
        margin-bottom: 5px;
    }
    .signal-detail {
        display: flex;
        justify-content: space-between;
        margin: 10px 0;
        font-size: 1.1rem;
    }
    .signal-time {
        color: #888;
        font-size: 0.9rem;
    }
    .signal-badge {
        display: inline-block;
        padding: 5px 10px;
        border-radius: 5px;
        font-weight: bold;
    }
    .badge-call { background-color: #1a3a1a; color: #00ff88; }
    .badge-put { background-color: #3a1a1a; color: #ff4b4b; }
    hr { border-color: #2a2f3a; }
    .selected-assets {
        background-color: #1e2a3a;
        padding: 15px;
        border-radius: 8px;
        margin-bottom: 20px;
        border-left: 4px solid #00a3ff;
    }
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
if 'activo_actual' not in st.session_state:
    st.session_state.activo_actual = None  # el activo que se está analizando/monitoreando
if 'señal_activa' not in st.session_state:
    st.session_state.señal_activa = None  # dict con la señal actual
if 'historial_señales' not in st.session_state:
    st.session_state.historial_señales = []  # lista de señales pasadas
if 'log' not in st.session_state:
    st.session_state.log = []
if 'estrategias_activas' not in st.session_state:
    st.session_state.estrategias_activas = [nombre for nombre, _ in ESTRATEGIAS[:5]]
if 'tipo_mercado' not in st.session_state:
    st.session_state.tipo_mercado = "OTC"  # por defecto solo OTC
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

def obtener_activos_por_tipo(tipo):
    """Obtiene activos según el tipo seleccionado: 'OTC', 'REAL' o 'AMBOS'"""
    if not st.session_state.api:
        return []
    try:
        open_time = st.session_state.api.get_all_open_time()
        activos = []
        if 'binary' in open_time:
            for asset, data in open_time['binary'].items():
                if data.get('open', False):
                    if tipo == "OTC" and "-OTC" in asset:
                        activos.append(asset)
                    elif tipo == "REAL" and "-OTC" not in asset:
                        activos.append(asset)
                    elif tipo == "AMBOS":
                        activos.append(asset)
        return activos
    except:
        return []

def evaluar_mejor_activo(activos):
    """Evalúa todos los activos y devuelve el que tenga la señal más fuerte (mayor puntuación)"""
    mejor_activo = None
    mejor_puntuacion = 0
    mejor_direccion = None
    mejor_estrategia = None
    for asset in activos:
        try:
            # Evaluar el activo con las estrategias activas
            resultado = evaluar_activo(st.session_state.api, asset, st.session_state.estrategias_activas)
            if resultado:
                direccion, nombre_estr = resultado
                # Asignamos una puntuación (podría basarse en la fuerza de la señal, pero por ahora usamos 1)
                puntuacion = 1
                if puntuacion > mejor_puntuacion:
                    mejor_puntuacion = puntuacion
                    mejor_activo = asset
                    mejor_direccion = direccion
                    mejor_estrategia = nombre_estr
        except:
            continue
        time.sleep(0.2)
    if mejor_activo:
        return mejor_activo, mejor_direccion, mejor_estrategia
    return None, None, None

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

    st.markdown("### 🌍 Mercados a analizar")
    tipo_mercado = st.radio("", ["OTC", "REAL", "AMBOS"], index=0, horizontal=True)
    st.session_state.tipo_mercado = tipo_mercado

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
        st.metric("Mercado", st.session_state.tipo_mercado)
    with col3:
        st.metric("Señales generadas", len(st.session_state.historial_señales))

    # Mostrar activo actual si hay
    if st.session_state.activo_actual:
        st.markdown(f"<div class='selected-assets'><strong>🔍 ANALIZANDO:</strong> {st.session_state.activo_actual}</div>", unsafe_allow_html=True)

    # Gráfico del activo actual (opcional)
    if st.session_state.activo_actual and st.session_state.datos_grafico is not None:
        fig = crear_grafico_velas(st.session_state.datos_grafico, st.session_state.activo_actual)
        st.plotly_chart(fig, use_container_width=True)

    # Señal activa (solo una a la vez)
    if st.session_state.señal_activa:
        senal = st.session_state.señal_activa
        color_class = "call" if senal['direccion'] == 'CALL' else "put"
        badge_class = "badge-call" if senal['direccion'] == 'CALL' else "badge-put"
        st.markdown(f"""
        <div class="signal-card {color_class}">
            <div class="signal-title">{senal['activo']}</div>
            <div class="signal-detail">
                <span><span class="signal-badge {badge_class}">{senal['direccion']}</span></span>
                <span>💰 Monto sugerido: $10</span>
            </div>
            <div class="signal-detail">
                <span>⏰ Entrada: {senal['entrada']}</span>
                <span>⌛ Vencimiento: {senal['vencimiento']} (5 min)</span>
            </div>
            <div class="signal-detail">
                <span>📊 Estrategia: {senal['estrategia']}</span>
            </div>
            <div class="signal-time">Generada: {senal['fecha']}</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.info("⏳ Esperando señal...")

    # Historial de señales
    with st.expander("📋 Historial de señales", expanded=True):
        if st.session_state.historial_señales:
            # Mostrar las señales en orden descendente (la más reciente primero)
            for senal in reversed(st.session_state.historial_señales[-10:]):
                color = "#00ff88" if senal['direccion'] == 'CALL' else "#ff4b4b"
                st.markdown(f"""
                <div style="border-left: 4px solid {color}; padding: 10px; margin: 5px 0; background-color: #1e2430; border-radius: 5px;">
                    <strong>{senal['fecha']}</strong> | {senal['activo']} | {senal['direccion']} | Entrada: {senal['entrada']} | Vencimiento: {senal['vencimiento']}
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("No hay historial aún.")

    # Log de eventos
    with st.expander("📋 Log de eventos", expanded=False):
        for linea in st.session_state.log[-20:]:
            st.text(linea)

    # =========================
    # LÓGICA DE MONITOREO (UNA SEÑAL A LA VEZ)
    # =========================
    if st.session_state.monitoreando:
        # Si hay una señal activa, verificar si ya venció
        if st.session_state.señal_activa:
            now = datetime.now(ecuador)
            # Convertir la hora de entrada a datetime para comparar
            entrada_str = st.session_state.señal_activa['entrada']
            # Asumimos que la fecha es hoy
            entrada_dt = datetime.strptime(entrada_str, "%H:%M:%S").time()
            entrada_full = datetime.combine(now.date(), entrada_dt)
            entrada_full = ecuador.localize(entrada_full)
            vencimiento = entrada_full + timedelta(minutes=5)
            if now >= vencimiento:
                # La señal ha expirado, mover al historial
                st.session_state.historial_señales.append(st.session_state.señal_activa)
                st.session_state.señal_activa = None
                st.session_state.log.append("⏳ Señal anterior expirada, buscando nueva...")
                # Pequeña pausa antes de buscar nueva señal
                time.sleep(2)
                st.rerun()
            else:
                # Aún no vence, mostrar tiempo restante
                tiempo_restante = vencimiento - now
                mins, segs = divmod(tiempo_restante.seconds, 60)
                st.info(f"⏳ Señal activa - Tiempo restante: {mins:02d}:{segs:02d}")
                time.sleep(1)
                st.rerun()
        else:
            # No hay señal activa, buscar el mejor activo
            activos = obtener_activos_por_tipo(st.session_state.tipo_mercado)
            if not activos:
                st.warning("No hay activos disponibles en este mercado.")
                time.sleep(5)
                st.rerun()

            st.session_state.activo_actual = "Buscando mejor activo..."
            mejor_activo, direccion, estrategia = evaluar_mejor_activo(activos)
            if mejor_activo:
                # Generar nueva señal
                now = datetime.now(ecuador)
                entrada = now.strftime("%H:%M:%S")
                vencimiento = (now + timedelta(minutes=5)).strftime("%H:%M:%S")
                st.session_state.señal_activa = {
                    'fecha': now.strftime("%Y-%m-%d %H:%M:%S"),
                    'activo': mejor_activo,
                    'direccion': direccion,
                    'estrategia': estrategia,
                    'entrada': entrada,
                    'vencimiento': vencimiento
                }
                st.session_state.activo_actual = mejor_activo
                st.session_state.log.append(f"📢 NUEVA SEÑAL: {mejor_activo} - {direccion} a las {entrada}")
                # Obtener datos para gráfico
                try:
                    candles = st.session_state.api.get_candles(mejor_activo, 300, 50, time.time())
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
                time.sleep(2)
                st.rerun()
            else:
                st.session_state.activo_actual = None
                st.session_state.log.append("🔍 No se encontraron señales en este ciclo. Reintentando...")
                time.sleep(5)
                st.rerun()
else:
    st.info("🔒 Conéctate a IQ Option para comenzar.")

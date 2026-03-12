import streamlit as st
import pandas as pd
import time
from datetime import datetime, timedelta
import pytz
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from iqoptionapi.stable_api import IQ_Option
from bot import (
    evaluar_activo,
    seleccionar_mejores_activos,
    calcular_indicadores,
    DEFAULT_OTC_ASSETS,
    DEFAULT_REAL_ASSETS
)

# Configuración de página
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
    .signal-title { font-size: 1.5rem; font-weight: bold; margin-bottom: 10px; }
    .signal-detail { font-size: 1rem; color: #ccc; margin: 5px 0; }
    hr { border-color: #2a2f3a; }
    .assets-container {
        display: flex;
        gap: 20px;
        flex-wrap: wrap;
        margin: 20px 0;
    }
    .asset-card {
        background-color: #1e2a3a;
        border-radius: 8px;
        padding: 15px;
        flex: 1;
        min-width: 200px;
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
if 'activos_seguimiento' not in st.session_state:
    st.session_state.activos_seguimiento = []  # lista de dicts con info de cada activo
if 'señales' not in st.session_state:
    st.session_state.señales = []
if 'log' not in st.session_state:
    st.session_state.log = []
if 'datos_grafico' not in st.session_state:
    st.session_state.datos_grafico = {}
if 'tiempo_inicio_espera' not in st.session_state:
    st.session_state.tiempo_inicio_espera = datetime.now()

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
    st.session_state.activos_seguimiento = []
    st.session_state.log.append("🔌 Desconectado")

def obtener_activos_por_tipo(tipo_mercado):
    """Obtiene lista de activos según el tipo seleccionado"""
    if not st.session_state.api:
        if tipo_mercado == "OTC":
            return DEFAULT_OTC_ASSETS
        elif tipo_mercado == "REAL":
            return DEFAULT_REAL_ASSETS
        else:
            return DEFAULT_OTC_ASSETS + DEFAULT_REAL_ASSETS
    try:
        open_time = st.session_state.api.get_all_open_time()
        real = []
        otc = []
        if 'binary' in open_time:
            for asset, data in open_time['binary'].items():
                if data.get('open', False):
                    if '-OTC' in asset:
                        otc.append(asset)
                    else:
                        real.append(asset)
        if tipo_mercado == "OTC":
            return otc if otc else DEFAULT_OTC_ASSETS
        elif tipo_mercado == "REAL":
            return real if real else DEFAULT_REAL_ASSETS
        else:
            return (otc + real) if (otc or real) else DEFAULT_OTC_ASSETS + DEFAULT_REAL_ASSETS
    except:
        if tipo_mercado == "OTC":
            return DEFAULT_OTC_ASSETS
        elif tipo_mercado == "REAL":
            return DEFAULT_REAL_ASSETS
        else:
            return DEFAULT_OTC_ASSETS + DEFAULT_REAL_ASSETS

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
    fig.add_trace(go.Scatter(x=df.index, y=df['rsi'], line=dict(color='#aa88ff', width=1), name='RSI'), row=2, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="#ff4b4b", row=2, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="#00ff88", row=2, col=1)
    fig.update_layout(title=f"{activo} - Análisis en tiempo real",
                      xaxis_rangeslider_visible=False,
                      template='plotly_dark',
                      height=500)
    return fig

# =========================
# BARRA LATERAL
# =========================
with st.sidebar:
    st.markdown("## 🧠 NEUROTRADER PRO")
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
    tipo_cuenta = st.radio("Tipo de cuenta", ["PRACTICE", "REAL"], index=0, horizontal=True, label_visibility="collapsed")
    if tipo_cuenta != st.session_state.tipo_cuenta and st.session_state.conectado:
        st.session_state.tipo_cuenta = tipo_cuenta
        st.session_state.api.change_balance(tipo_cuenta)
        saldo = st.session_state.api.get_balance()
        st.session_state.saldo = saldo if saldo is not None else 0.0
        st.session_state.log.append(f"🔄 Cambio a cuenta {tipo_cuenta} - Saldo: {st.session_state.saldo}")

    st.markdown("---")

    st.markdown("### ⚙️ Configuración")
    tipo_mercado = st.selectbox("Mercado a analizar", ["OTC", "REAL", "AMBOS"], index=0)
    num_activos = st.slider("Número de activos a seguir", 1, 5, 3, 1,
                            help="Cantidad de activos que se monitorearán simultáneamente")
    tiempo_max_espera = st.slider("Tiempo máximo de espera (minutos)", 5, 30, 15, 5,
                                   help="Si un activo no da señal en este tiempo, se reemplazará")

    st.markdown("---")

    st.markdown("### ⚙️ Control")
    if st.session_state.conectado:
        if not st.session_state.monitoreando:
            if st.button("▶️ INICIAR MONITOREO", use_container_width=True, type="primary"):
                st.session_state.monitoreando = True
                st.session_state.log.append("🚀 Monitoreo iniciado")
                # Seleccionar los mejores activos
                with st.spinner("Seleccionando activos confiables..."):
                    activos_lista = obtener_activos_por_tipo(tipo_mercado)
                    if activos_lista:
                        mejores = seleccionar_mejores_activos(st.session_state.api, activos_lista, num_activos)
                        if mejores:
                            st.session_state.activos_seguimiento = []
                            for asset, direc, fuerza in mejores:
                                st.session_state.activos_seguimiento.append({
                                    'activo': asset,
                                    'direccion': direc,
                                    'fuerza': fuerza,
                                    'estado': 'ESPERANDO',
                                    'hora_entrada': None,
                                    'hora_vencimiento': None,
                                    'tiempo_inicio': datetime.now(ecuador)
                                })
                            st.session_state.log.append(f"✅ Seleccionados {len(mejores)} activos: {', '.join([a[0] for a in mejores])}")
                        else:
                            # Fallback: primeros activos de la lista
                            fallback = activos_lista[:num_activos]
                            st.session_state.activos_seguimiento = []
                            for asset in fallback:
                                st.session_state.activos_seguimiento.append({
                                    'activo': asset,
                                    'direccion': None,
                                    'fuerza': 0,
                                    'estado': 'ESPERANDO',
                                    'hora_entrada': None,
                                    'hora_vencimiento': None,
                                    'tiempo_inicio': datetime.now(ecuador)
                                })
                            st.session_state.log.append(f"⚠️ Usando activos por defecto: {', '.join(fallback)}")
                    else:
                        st.session_state.log.append("⚠️ No hay activos disponibles.")
                st.rerun()
        else:
            if st.button("⏹️ DETENER MONITOREO", use_container_width=True, type="secondary"):
                st.session_state.monitoreando = False
                st.session_state.activos_seguimiento = []
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
        st.metric("Activos en seguimiento", len(st.session_state.activos_seguimiento))
    with col3:
        en_espera = sum(1 for a in st.session_state.activos_seguimiento if a['estado'] == 'ESPERANDO')
        listos = sum(1 for a in st.session_state.activos_seguimiento if a['estado'] == 'LISTO')
        en_curso = sum(1 for a in st.session_state.activos_seguimiento if a['estado'] == 'OPERACION_EN_CURSO')
        st.metric("Estados", f"Espera:{en_espera} Listo:{listos} Curso:{en_curso}")

    # Mostrar tarjetas de activos en seguimiento
    if st.session_state.activos_seguimiento:
        st.subheader("📊 ACTIVOS EN SEGUIMIENTO")
        cols = st.columns(min(len(st.session_state.activos_seguimiento), 3))
        for idx, activo in enumerate(st.session_state.activos_seguimiento):
            with cols[idx % 3]:
                if activo['estado'] == 'LISTO' and activo['hora_entrada']:
                    card_class = "call-card" if activo['direccion'] == 'CALL' else "put-card"
                    st.markdown(f"""
                    <div class="signal-card {card_class}">
                        <div class="signal-title">{activo['activo']}</div>
                        <div><strong>{'🔵 COMPRA' if activo['direccion'] == 'CALL' else '🔴 VENTA'}</strong></div>
                        <div>Entrada: {activo['hora_entrada']}</div>
                        <div>Vencimiento: {activo['hora_vencimiento']}</div>
                        <div>Estrategia: Tendencia + EMA</div>
                        <div class="signal-time">✅ LISTO PARA OPERAR</div>
                    </div>
                    """, unsafe_allow_html=True)
                elif activo['estado'] == 'OPERACION_EN_CURSO' and activo['hora_entrada']:
                    now = datetime.now(ecuador)
                    venc = datetime.strptime(activo['hora_vencimiento'], "%H:%M:%S").time()
                    venc_dt = datetime.combine(now.date(), venc)
                    if venc_dt < now:
                        venc_dt += timedelta(days=1)
                    resto = (venc_dt - now).total_seconds()
                    mins, segs = divmod(int(resto), 60)
                    st.markdown(f"""
                    <div class="signal-card waiting-card">
                        <div class="signal-title">{activo['activo']}</div>
                        <div><strong>{'⏳ ' + activo['direccion']}</strong></div>
                        <div>Entrada: {activo['hora_entrada']}</div>
                        <div>Vence: {activo['hora_vencimiento']}</div>
                        <div>Tiempo: {mins:02d}:{segs:02d}</div>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                    <div class="asset-card">
                        <div><strong>{activo['activo']}</strong></div>
                        <div>Dirección: {activo['direccion'] or 'Sin tendencia'}</div>
                        <div>Fuerza: {activo['fuerza']:.1f}</div>
                        <div>Estado: {activo['estado']}</div>
                    </div>
                    """, unsafe_allow_html=True)

        # Gráficos (opcional: mostrar el primer activo)
        if st.session_state.activos_seguimiento and st.session_state.datos_grafico:
            primer_activo = st.session_state.activos_seguimiento[0]['activo']
            if primer_activo in st.session_state.datos_grafico:
                fig = crear_grafico_velas(st.session_state.datos_grafico[primer_activo], primer_activo)
                st.plotly_chart(fig, use_container_width=True)

    # Historial de señales
    with st.expander("📋 Historial de señales", expanded=True):
        if st.session_state.señales:
            df_hist = pd.DataFrame(st.session_state.señales)
            st.dataframe(df_hist[['fecha', 'activo', 'direccion', 'entrada', 'vencimiento']],
                         use_container_width=True, hide_index=True)
        else:
            st.info("No hay señales en el historial.")

    # Log de eventos
    with st.expander("📋 Log de eventos", expanded=False):
        for linea in st.session_state.log[-20:]:
            st.text(linea)

    # =========================
    # LÓGICA DE MONITOREO (por cada activo)
    # =========================
    if st.session_state.monitoreando and st.session_state.activos_seguimiento:
        now = datetime.now(ecuador)
        nuevos_seguimiento = []
        for activo in st.session_state.activos_seguimiento:
            asset = activo['activo']

            # Si está en OPERACION_EN_CURSO, verificar vencimiento
            if activo['estado'] == 'OPERACION_EN_CURSO' and activo['hora_vencimiento']:
                venc = datetime.strptime(activo['hora_vencimiento'], "%H:%M:%S").time()
                venc_dt = datetime.combine(now.date(), venc)
                if venc_dt < now:
                    venc_dt += timedelta(days=1)
                if now >= venc_dt:
                    # Operación vencida, volver a ESPERANDO
                    activo['estado'] = 'ESPERANDO'
                    activo['hora_entrada'] = None
                    activo['hora_vencimiento'] = None
                    activo['tiempo_inicio'] = now
                    st.session_state.log.append(f"✅ Operación en {asset} finalizada. Volviendo a esperar.")
                else:
                    # Aún no vence, mantener estado
                    nuevos_seguimiento.append(activo)
                continue

            # Verificar tiempo máximo de espera
            if activo['estado'] == 'ESPERANDO' and activo['tiempo_inicio']:
                tiempo_trans = (now - activo['tiempo_inicio']).total_seconds() / 60
                if tiempo_trans > tiempo_max_espera:
                    st.session_state.log.append(f"⏰ {asset} alcanzó tiempo máximo de espera. Buscando reemplazo...")
                    # Se reemplazará al final del ciclo
                    continue

            # Evaluar el activo
            direccion, fuerza, lista_para_entrar, estrategia, precio = evaluar_activo(
                st.session_state.api, asset, check_agotamiento=True
            )
            if direccion is None:
                # Perdió tendencia, buscar reemplazo
                st.session_state.log.append(f"⚠️ {asset} perdió tendencia. Será reemplazado.")
                continue

            # Actualizar datos
            activo['direccion'] = direccion
            activo['fuerza'] = fuerza

            if lista_para_entrar and activo['estado'] == 'ESPERANDO':
                # Generar señal
                hora_entrada = now.strftime("%H:%M:%S")
                hora_venc = (now + timedelta(minutes=5)).strftime("%H:%M:%S")
                activo['estado'] = 'LISTO'
                activo['hora_entrada'] = hora_entrada
                activo['hora_vencimiento'] = hora_venc
                st.session_state.señales.insert(0, {
                    'fecha': now.strftime("%Y-%m-%d %H:%M:%S"),
                    'activo': asset,
                    'direccion': direccion,
                    'entrada': hora_entrada,
                    'vencimiento': hora_venc,
                    'estrategia': estrategia
                })
                st.session_state.log.append(f"📢 SEÑAL GENERADA: {asset} - {direccion} a las {hora_entrada}")
            else:
                # Si no hay señal, seguir esperando
                pass

            # Actualizar gráfico (opcional)
            try:
                candles = st.session_state.api.get_candles(asset, 300, 50, time.time())
                if candles:
                    df = pd.DataFrame(candles)
                    for col in ['open', 'max', 'min', 'close', 'volume']:
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                    df.dropna(inplace=True)
                    if len(df) > 30:
                        df = calcular_indicadores(df)
                        st.session_state.datos_grafico[asset] = df
            except:
                pass

            nuevos_seguimiento.append(activo)

        # Reemplazar activos perdidos
        if len(nuevos_seguimiento) < len(st.session_state.activos_seguimiento):
            cuantos_faltan = len(st.session_state.activos_seguimiento) - len(nuevos_seguimiento)
            st.session_state.log.append(f"🔍 Buscando {cuantos_faltan} reemplazo(s)...")
            activos_lista = obtener_activos_por_tipo(tipo_mercado)
            # Excluir los que ya están en seguimiento
            existentes = [a['activo'] for a in nuevos_seguimiento]
            disponibles = [a for a in activos_lista if a not in existentes]
            if disponibles:
                mejores = seleccionar_mejores_activos(st.session_state.api, disponibles, cuantos_faltan)
                for asset, direc, fuerza in mejores:
                    nuevos_seguimiento.append({
                        'activo': asset,
                        'direccion': direc,
                        'fuerza': fuerza,
                        'estado': 'ESPERANDO',
                        'hora_entrada': None,
                        'hora_vencimiento': None,
                        'tiempo_inicio': now
                    })
                    st.session_state.log.append(f"➕ Nuevo activo añadido: {asset}")
            else:
                st.session_state.log.append("⚠️ No hay disponibles para reemplazo.")

        st.session_state.activos_seguimiento = nuevos_seguimiento
        time.sleep(5)  # Pausa entre ciclos
        st.rerun()
    elif st.session_state.monitoreando and not st.session_state.activos_seguimiento:
        # No hay activos, intentar seleccionar
        activos_lista = obtener_activos_por_tipo(tipo_mercado)
        if activos_lista:
            mejores = seleccionar_mejores_activos(st.session_state.api, activos_lista, num_activos)
            if mejores:
                st.session_state.activos_seguimiento = []
                for asset, direc, fuerza in mejores:
                    st.session_state.activos_seguimiento.append({
                        'activo': asset,
                        'direccion': direc,
                        'fuerza': fuerza,
                        'estado': 'ESPERANDO',
                        'hora_entrada': None,
                        'hora_vencimiento': None,
                        'tiempo_inicio': datetime.now(ecuador)
                    })
                st.session_state.log.append(f"✅ Seleccionados {len(mejores)} activos")
            else:
                st.session_state.log.append("⚠️ No se encontraron activos confiables.")
        time.sleep(5)
        st.rerun()

else:
    st.info("🔒 Conéctate a IQ Option para comenzar.")

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
    retroceso_a_fibonacci,
    confirmar_vela_1min,
    calcular_fibonacci,
    calcular_indicadores  # importamos para usar en app
)

st.set_page_config(
    page_title="NEUROTRADER PRO - TENDENCIA + FIBONACCI",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilos CSS (igual que antes)
st.markdown("""
<style>
    .stApp { background: linear-gradient(135deg, #0a0c15 0%, #121724 100%); font-family: 'Segoe UI', sans-serif; }
    section[data-testid="stSidebar"] { background: rgba(18,23,36,0.95); backdrop-filter: blur(10px); border-right: 1px solid rgba(0,163,255,0.2); }
    div[data-testid="stMetric"] { background: linear-gradient(145deg, #1e2435, #151b2a); border-radius: 16px; padding: 20px; box-shadow: 0 10px 20px rgba(0,0,0,0.3); border: 1px solid rgba(0,163,255,0.2); transition: transform 0.2s; }
    .stButton > button { background: linear-gradient(90deg, #00a3ff, #0066cc); border: none; border-radius: 30px; color: white; font-weight: bold; padding: 10px 20px; transition: all 0.3s; box-shadow: 0 4px 10px rgba(0,163,255,0.3); }
    .stButton > button:hover { transform: scale(1.02); background: linear-gradient(90deg, #00b4ff, #0077ee); box-shadow: 0 6px 15px rgba(0,163,255,0.5); }
    .asset-card { background: linear-gradient(145deg, #1a2032, #0f1422); border-radius: 20px; padding: 20px; margin: 15px 0; box-shadow: 0 20px 35px -10px rgba(0,0,0,0.5); border: 1px solid rgba(0,163,255,0.3); transition: all 0.3s ease; }
    .asset-card:hover { transform: translateY(-5px); box-shadow: 0 25px 40px -12px rgba(0,0,0,0.6); border-color: #00a3ff; }
    .asset-name { font-size: 1.4rem; font-weight: bold; margin-bottom: 10px; color: #fff; text-shadow: 0 2px 5px rgba(0,0,0,0.3); }
    .asset-status { font-size: 0.9rem; padding: 4px 12px; border-radius: 20px; display: inline-block; background: rgba(0,0,0,0.5); margin-bottom: 15px; }
    .signal-call { border-left: 5px solid #00ff88; background: linear-gradient(90deg, rgba(0,255,136,0.1) 0%, rgba(0,0,0,0) 100%); }
    .signal-put { border-left: 5px solid #ff4b4b; background: linear-gradient(90deg, rgba(255,75,75,0.1) 0%, rgba(0,0,0,0) 100%); }
    .force-bar { background: #2a2f3a; border-radius: 10px; height: 8px; margin: 10px 0; overflow: hidden; }
    .force-fill { background: linear-gradient(90deg, #00a3ff, #00ff88); width: 0%; height: 100%; border-radius: 10px; transition: width 0.5s; }
    .entry-time { font-family: monospace; font-size: 1.1rem; color: #ffaa00; margin-top: 5px; }
    hr { border-color: #2a2f3a; }
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
if 'esperando_retroceso' not in st.session_state:
    st.session_state.esperando_retroceso = False
if 'senal_generada' not in st.session_state:
    st.session_state.senal_generada = None
if 'log' not in st.session_state:
    st.session_state.log = []
if 'activos_totales' not in st.session_state:
    st.session_state.activos_totales = []

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
    st.markdown("## 📈 NEUROTRADER PRO")
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
    umbral_fuerza = st.slider("Fuerza mínima de tendencia (%)", 0, 100, 30, 5,
                              help="Solo se consideran activos con fuerza mayor a este valor")
    pausa_ronda = st.slider("Pausa entre rondas (seg)", 5, 30, 10, 5)
    anticipacion = st.slider("Anticipación señal (seg antes del cierre de vela 1min)", 5, 30, 20, 5)

    st.markdown("---")
    if st.session_state.conectado:
        if not st.session_state.monitoreando:
            if st.button("▶️ INICIAR", use_container_width=True, type="primary"):
                st.session_state.monitoreando = True
                st.session_state.log.append("🚀 Monitoreo iniciado")
                st.session_state.activos_totales = obtener_activos_abiertos(st.session_state.api, tipo_mercado)
                st.session_state.log.append(f"📊 Total activos disponibles: {len(st.session_state.activos_totales)}")
                st.rerun()
        else:
            if st.button("⏹️ DETENER", use_container_width=True, type="secondary"):
                st.session_state.monitoreando = False
                st.rerun()

    if st.session_state.conectado:
        st.metric("💰 Saldo", f"${st.session_state.saldo:.2f}")

# Área principal
if st.session_state.conectado:
    st.title("📊 Trading de Tendencia + Fibonacci (5min)")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Saldo", f"${st.session_state.saldo:.2f}")
    with col2:
        st.metric("Activo en seguimiento", st.session_state.activo_seleccionado['asset'] if st.session_state.activo_seleccionado else "Ninguno")
    with col3:
        st.metric("Señales generadas", len([l for l in st.session_state.log if "🚀" in l]))

    # Mostrar información del activo seleccionado
    if st.session_state.activo_seleccionado:
        s = st.session_state.activo_seleccionado
        st.markdown(f"""
        <div class="asset-card">
            <div class="asset-name">{s['asset']}</div>
            <div><strong>Dirección:</strong> {s['direccion']} | <strong>Fuerza:</strong> {s['fuerza']:.1f}%</div>
            <div>Precio actual: {s['precio']:.5f}</div>
            <div>Niveles Fibonacci: 38.2% = {s['fib']['382']:.5f}, 50% = {s['fib']['500']:.5f}, 61.8% = {s['fib']['618']:.5f}</div>
            <div>Estado: {'Esperando retroceso...' if not st.session_state.senal_generada else 'Señal lista para operar'}</div>
        </div>
        """, unsafe_allow_html=True)

    # Mostrar señal si existe
    if st.session_state.senal_generada:
        s = st.session_state.senal_generada
        card_class = "signal-call" if s['direccion'] == "CALL" else "signal-put"
        st.markdown(f"""
        <div class="asset-card {card_class}">
            <div class="asset-name">{s['asset']}</div>
            <div class="asset-status">✅ SEÑAL LISTA</div>
            <div><strong>{s['direccion']}</strong> - Nivel Fibonacci {s['nivel_fib']} alcanzado</div>
            <div>Fuerza: {s['fuerza']:.1f}%</div>
            <div class="force-bar"><div class="force-fill" style="width: {s['fuerza']}%;"></div></div>
            <div class="entry-time">⏱️ Entrada: {s['entrada']}</div>
            <div class="entry-time">⏰ Vencimiento: {s['vencimiento']}</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.info("No hay señal activa. Esperando condiciones...")

    # Log
    with st.expander("📋 Log de eventos", expanded=True):
        for linea in st.session_state.log[-20:]:
            st.text(linea)

    # Lógica principal
    if st.session_state.monitoreando:
        now = datetime.now(ecuador)

        if st.session_state.senal_generada:
            entrada_dt = datetime.strptime(st.session_state.senal_generada['entrada'], "%H:%M:%S").time()
            entrada_completa = datetime.combine(now.date(), entrada_dt)
            entrada_completa = ecuador.localize(entrada_completa)
            if entrada_completa > now:
                entrada_completa -= timedelta(days=1)
            expiracion = entrada_completa + timedelta(minutes=5)
            if now >= expiracion:
                st.session_state.senal_generada = None
                st.session_state.activo_seleccionado = None
                st.session_state.log.append("🗑️ Señal expirada. Buscando nueva oportunidad...")
                st.rerun()
            else:
                seg_rest = (expiracion - now).total_seconds()
                mins = int(seg_rest // 60)
                segs = int(seg_rest % 60)
                st.info(f"⏳ Señal activa. Vence en {mins} min {segs} seg...")
                time.sleep(1)
                st.rerun()
        else:
            # Si no hay activo seleccionado, hacer ronda de búsqueda (60 activos, pausa reducida)
            if not st.session_state.activo_seleccionado:
                st.session_state.log.append("🔍 Buscando el mejor activo con tendencia fuerte...")
                if not st.session_state.activos_totales:
                    st.session_state.activos_totales = obtener_activos_abiertos(st.session_state.api, tipo_mercado)
                # Tomar los primeros 60 activos (o todos)
                candidatos = st.session_state.activos_totales[:60]
                mejor = seleccionar_mejor_activo(st.session_state.api, candidatos)
                if mejor and mejor['fuerza'] >= umbral_fuerza:
                    st.session_state.activo_seleccionado = mejor
                    st.session_state.esperando_retroceso = True
                    st.session_state.log.append(f"✅ Activo seleccionado: {mejor['asset']} - {mejor['direccion']} (fuerza {mejor['fuerza']:.1f}%)")
                    st.session_state.log.append(f"   Niveles Fibonacci: 38.2%={mejor['fib']['382']:.5f}, 50%={mejor['fib']['500']:.5f}, 61.8%={mejor['fib']['618']:.5f}")
                else:
                    st.session_state.log.append("⚠️ No se encontró ningún activo con tendencia suficiente. Reintentando...")
                time.sleep(pausa_ronda)
                st.rerun()
            else:
                # Ya tenemos activo, esperar retroceso a Fibonacci
                asset = st.session_state.activo_seleccionado['asset']
                direccion = st.session_state.activo_seleccionado['direccion']
                fib = st.session_state.activo_seleccionado['fib']

                # Obtener velas de 5 minutos
                try:
                    candles = st.session_state.api.get_candles(asset, 300, 5, time.time())
                    if not candles:
                        time.sleep(1)
                        st.rerun()
                    df = pd.DataFrame(candles)
                    for col in ['open', 'max', 'min', 'close', 'volume']:
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                    df.dropna(inplace=True)
                    if len(df) < 5:
                        time.sleep(1)
                        st.rerun()
                    # Calcular indicadores
                    from bot import calcular_indicadores
                    df_indicadores = calcular_indicadores(df)
                    retroceso = retroceso_a_fibonacci(df_indicadores, direccion, fib, tolerancia=0.5)
                except Exception as e:
                    st.session_state.log.append(f"⚠️ Error obteniendo velas de {asset}: {e}")
                    time.sleep(1)
                    st.rerun()

                if retroceso:
                    st.session_state.log.append(f"📉 Precio alcanzó nivel Fibonacci {retroceso['clave']} en {asset}. Esperando confirmación de vela 1min...")
                    # Confirmación con vela de 1 minuto
                    for _ in range(10):
                        if confirmar_vela_1min(st.session_state.api, asset, direccion):
                            # Generar señal con anticipación
                            now = datetime.now(ecuador)
                            # Redondear al siguiente minuto (segundo 00)
                            entrada = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
                            entrada_str = entrada.strftime("%H:%M:%S")
                            vencimiento_str = (entrada + timedelta(minutes=5)).strftime("%H:%M:%S")
                            st.session_state.senal_generada = {
                                'asset': asset,
                                'direccion': direccion,
                                'fuerza': st.session_state.activo_seleccionado['fuerza'],
                                'nivel_fib': retroceso['clave'],
                                'entrada': entrada_str,
                                'vencimiento': vencimiento_str
                            }
                            st.session_state.log.append(f"🚀 SEÑAL GENERADA: {asset} - {direccion} a las {entrada_str} (nivel {retroceso['clave']})")
                            st.rerun()
                        time.sleep(2)
                    st.session_state.log.append(f"⚠️ No hubo confirmación en {asset} tras alcanzar Fibonacci. Buscando otro activo...")
                    st.session_state.activo_seleccionado = None
                    st.rerun()
                else:
                    time.sleep(2)
                    st.rerun()

else:
    st.info("🔒 Conéctate a IQ Option para comenzar.")

import streamlit as st
import pandas as pd
import time
from datetime import datetime, timedelta
import pytz
from iqoptionapi.stable_api import IQ_Option
from bot import (
    evaluar_activo,
    seleccionar_activos_fuertes,
    obtener_activos_abiertos
)

st.set_page_config(
    page_title="NEUROTRADER PRO",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilos CSS profesionales (igual que antes)
st.markdown("""
<style>
    .stApp {
        background: linear-gradient(135deg, #0a0c15 0%, #121724 100%);
        font-family: 'Segoe UI', 'Poppins', sans-serif;
    }
    section[data-testid="stSidebar"] {
        background: rgba(18, 23, 36, 0.95);
        backdrop-filter: blur(10px);
        border-right: 1px solid rgba(0, 163, 255, 0.2);
    }
    div[data-testid="stMetric"] {
        background: linear-gradient(145deg, #1e2435, #151b2a);
        border-radius: 16px;
        padding: 20px;
        box-shadow: 0 10px 20px rgba(0,0,0,0.3);
        border: 1px solid rgba(0, 163, 255, 0.2);
        transition: transform 0.2s;
    }
    .stButton > button {
        background: linear-gradient(90deg, #00a3ff, #0066cc);
        border: none;
        border-radius: 30px;
        color: white;
        font-weight: bold;
        padding: 10px 20px;
        transition: all 0.3s;
        box-shadow: 0 4px 10px rgba(0,163,255,0.3);
    }
    .stButton > button:hover {
        transform: scale(1.02);
        background: linear-gradient(90deg, #00b4ff, #0077ee);
        box-shadow: 0 6px 15px rgba(0,163,255,0.5);
    }
    .asset-card {
        background: linear-gradient(145deg, #1a2032, #0f1422);
        border-radius: 20px;
        padding: 20px;
        margin: 15px 0;
        box-shadow: 0 20px 35px -10px rgba(0,0,0,0.5);
        border: 1px solid rgba(0, 163, 255, 0.3);
        transition: all 0.3s ease;
        position: relative;
        overflow: hidden;
    }
    .asset-card:hover {
        transform: translateY(-5px);
        box-shadow: 0 25px 40px -12px rgba(0,0,0,0.6);
        border-color: #00a3ff;
    }
    .asset-name {
        font-size: 1.4rem;
        font-weight: bold;
        margin-bottom: 10px;
        color: #fff;
        text-shadow: 0 2px 5px rgba(0,0,0,0.3);
    }
    .asset-status {
        font-size: 0.9rem;
        padding: 4px 12px;
        border-radius: 20px;
        display: inline-block;
        background: rgba(0,0,0,0.5);
        margin-bottom: 15px;
    }
    .signal-call {
        border-left: 5px solid #00ff88;
        background: linear-gradient(90deg, rgba(0,255,136,0.1) 0%, rgba(0,0,0,0) 100%);
    }
    .signal-put {
        border-left: 5px solid #ff4b4b;
        background: linear-gradient(90deg, rgba(255,75,75,0.1) 0%, rgba(0,0,0,0) 100%);
    }
    .signal-neutral {
        border-left: 5px solid #ffaa00;
    }
    .force-bar {
        background: #2a2f3a;
        border-radius: 10px;
        height: 8px;
        margin: 10px 0;
        overflow: hidden;
    }
    .force-fill {
        background: linear-gradient(90deg, #00a3ff, #00ff88);
        width: 0%;
        height: 100%;
        border-radius: 10px;
        transition: width 0.5s;
    }
    .entry-time {
        font-family: monospace;
        font-size: 1.1rem;
        color: #ffaa00;
        margin-top: 5px;
    }
    hr {
        border-color: #2a2f3a;
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
if 'activos_seleccionados' not in st.session_state:
    st.session_state.activos_seleccionados = []
if 'señales_activas' not in st.session_state:
    st.session_state.señales_activas = {}  # dict {asset: señal_dict}
if 'ultima_senal_tiempo' not in st.session_state:
    st.session_state.ultima_senal_tiempo = None
if 'log' not in st.session_state:
    st.session_state.log = []
if 'activos_totales' not in st.session_state:
    st.session_state.activos_totales = []
if 'indice_ronda' not in st.session_state:
    st.session_state.indice_ronda = 0  # <--- AGREGADO para evitar AttributeError

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
    num_activos = st.slider("Número de activos a seguir", 1, 5, 3, 1)
    pausa_entre_ciclos = st.slider("Pausa entre ciclos (seg)", 30, 120, 60, 10)
    anticipacion = st.slider("Anticipación de señal (seg)", 5, 30, 15, 5)

    st.markdown("---")
    if st.session_state.conectado:
        # Mostrar conteo de activos disponibles
        if st.session_state.activos_totales:
            otc_count = sum(1 for a in st.session_state.activos_totales if '-OTC' in a)
            real_count = len(st.session_state.activos_totales) - otc_count
            st.info(f"📊 Activos disponibles: OTC={otc_count} | REAL={real_count}")
        else:
            st.info("📊 Conectando...")

        if not st.session_state.monitoreando:
            if st.button("▶️ INICIAR", use_container_width=True, type="primary"):
                st.session_state.monitoreando = True
                st.session_state.log.append("🚀 Monitoreo iniciado")
                # Seleccionar los activos más fuertes
                with st.spinner("Analizando activos..."):
                    activos_totales = obtener_activos_abiertos(st.session_state.api, tipo_mercado)
                    st.session_state.activos_totales = activos_totales
                    seleccionados = seleccionar_activos_fuertes(st.session_state.api, activos_totales, num_activos)
                    st.session_state.activos_seleccionados = seleccionados
                    st.session_state.log.append(f"✅ Activos seleccionados: {', '.join(seleccionados)}")
                st.rerun()
        else:
            if st.button("⏹️ DETENER", use_container_width=True, type="secondary"):
                st.session_state.monitoreando = False
                st.rerun()

    if st.session_state.conectado:
        st.metric("💰 Saldo", f"${st.session_state.saldo:.2f}")

# Área principal
if st.session_state.conectado:
    st.title("📊 Sistema de Trading con Divergencias")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Saldo", f"${st.session_state.saldo:.2f}")
    with col2:
        st.metric("Activos seguimiento", len(st.session_state.activos_seleccionados))
    with col3:
        st.metric("Señales activas", len([s for s in st.session_state.señales_activas.values() if s.get('activa', False)]))

    # Mostrar tarjetas de activos
    if st.session_state.activos_seleccionados:
        st.subheader("📌 Activos en seguimiento")
        cols = st.columns(len(st.session_state.activos_seleccionados))
        for idx, asset in enumerate(st.session_state.activos_seleccionados):
            with cols[idx]:
                senal = st.session_state.señales_activas.get(asset, {})
                if senal and senal.get('activa'):
                    # Tarjeta con señal activa
                    direccion = senal['direccion']
                    fuerza = senal['fuerza']
                    entrada = senal['entrada']
                    vencimiento = senal['vencimiento']
                    descripcion = senal['descripcion']
                    card_class = "signal-call" if direccion == "CALL" else "signal-put"
                    st.markdown(f"""
                    <div class="asset-card {card_class}">
                        <div class="asset-name">{asset}</div>
                        <div class="asset-status">✅ SEÑAL ACTIVA</div>
                        <div><strong>{direccion}</strong> - {descripcion}</div>
                        <div>Fuerza: {fuerza:.1f}%</div>
                        <div class="force-bar"><div class="force-fill" style="width: {fuerza}%;"></div></div>
                        <div class="entry-time">⏱️ Entrada: {entrada}</div>
                        <div class="entry-time">⏰ Vencimiento: {vencimiento}</div>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    # Tarjeta neutra
                    st.markdown(f"""
                    <div class="asset-card signal-neutral">
                        <div class="asset-name">{asset}</div>
                        <div class="asset-status">⚪ NEUTRO</div>
                        <div>Esperando señal...</div>
                        <div class="force-bar"><div class="force-fill" style="width: 0%;"></div></div>
                    </div>
                    """, unsafe_allow_html=True)

    # Historial de señales activas (tabla)
    with st.expander("📋 Señales activas", expanded=True):
        activas = [s for s in st.session_state.señales_activas.values() if s.get('activa')]
        if activas:
            data = []
            for s in activas:
                data.append({
                    'Activo': s['asset'],
                    'Dirección': s['direccion'],
                    'Descripción': s['descripcion'],
                    'Fuerza': f"{s['fuerza']:.1f}%",
                    'Entrada': s['entrada'],
                    'Vencimiento': s['vencimiento']
                })
            df = pd.DataFrame(data)
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("No hay señales activas.")

    # Log de eventos
    with st.expander("📋 Log de eventos", expanded=False):
        for linea in st.session_state.log[-20:]:
            st.text(linea)

    # Lógica de monitoreo
    if st.session_state.monitoreando:
        now = datetime.now(ecuador)

        # 1. Eliminar señales expiradas (5 minutos después de la entrada)
        activas = st.session_state.señales_activas.copy()
        for asset, senal in activas.items():
            if senal.get('activa'):
                entrada_dt = datetime.strptime(senal['entrada'], "%H:%M:%S").time()
                entrada_completa = datetime.combine(now.date(), entrada_dt)
                if entrada_completa < now:
                    entrada_completa += timedelta(days=1)
                if now >= entrada_completa + timedelta(minutes=5):
                    senal['activa'] = False
                    st.session_state.señales_activas[asset] = senal
                    st.session_state.log.append(f"🗑️ Señal expirada para {asset}")

        # 2. Si hay alguna señal activa, no evaluamos nuevos (esperamos)
        if any(s.get('activa') for s in st.session_state.señales_activas.values()):
            time.sleep(5)
            st.rerun()

        # 3. Evaluar activos
        if st.session_state.activos_seleccionados:
            for asset in st.session_state.activos_seleccionados:
                # Si ya tiene una señal activa (no debería porque ya las eliminamos), saltar
                if st.session_state.señales_activas.get(asset, {}).get('activa'):
                    continue

                res = evaluar_activo(st.session_state.api, asset)
                if res and 'direccion' in res:
                    # Nueva señal
                    entrada = now + timedelta(seconds=anticipacion)
                    entrada_str = entrada.strftime("%H:%M:%S")
                    vencimiento_str = (entrada + timedelta(minutes=5)).strftime("%H:%M:%S")
                    st.session_state.señales_activas[asset] = {
                        'activa': True,
                        'asset': asset,
                        'direccion': res['direccion'],
                        'descripcion': res['descripcion'],
                        'fuerza': res['fuerza'],
                        'entrada': entrada_str,
                        'vencimiento': vencimiento_str
                    }
                    st.session_state.log.append(f"🚀 SEÑAL: {asset} - {res['direccion']} a las {entrada_str} (Fuerza: {res['fuerza']:.1f}%)")
                    st.rerun()
                # Pequeña pausa entre activos
                time.sleep(1)

            # Si no hubo señales, esperar y luego actualizar fuerza de activos
            time.sleep(pausa_entre_ciclos)
            # Opcional: cada cierto tiempo, reevaluar la lista de activos fuertes
            st.session_state.indice_ronda += 1
            if st.session_state.indice_ronda % 10 == 0:
                # Cada 10 ciclos, refrescar activos
                activos_totales = obtener_activos_abiertos(st.session_state.api, tipo_mercado)
                if activos_totales:
                    nuevos = seleccionar_activos_fuertes(st.session_state.api, activos_totales, num_activos)
                    if nuevos != st.session_state.activos_seleccionados:
                        st.session_state.activos_seleccionados = nuevos
                        st.session_state.log.append(f"🔄 Activos actualizados: {', '.join(nuevos)}")
            st.rerun()
        else:
            # No hay activos seleccionados, buscar nuevos
            st.session_state.log.append("🔍 Buscando nuevos activos fuertes...")
            activos_totales = obtener_activos_abiertos(st.session_state.api, tipo_mercado)
            st.session_state.activos_totales = activos_totales
            seleccionados = seleccionar_activos_fuertes(st.session_state.api, activos_totales, num_activos)
            st.session_state.activos_seleccionados = seleccionados
            st.session_state.log.append(f"✅ Activos seleccionados: {', '.join(seleccionados)}")
            time.sleep(pausa_entre_ciclos)
            st.rerun()

else:
    st.info("🔒 Conéctate a IQ Option para comenzar.")

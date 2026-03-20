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
    page_title="NEUROTRADER - NIVELES",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilos CSS (tarjetas profesionales)
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
if 'activos_monitoreo' not in st.session_state:
    st.session_state.activos_monitoreo = []  # lista de dicts con info de cada activo
if 'señales_activas' not in st.session_state:
    st.session_state.señales_activas = {}  # dict {asset: dict con señal}
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
    st.markdown("## 📈 NEUROTRADER - NIVELES")
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
    umbral_fuerza = st.slider("Fuerza mínima para considerar activo", 0, 100, 40, 5)
    anticipacion = st.slider("Anticipación de señal (segundos antes del cierre)", 5, 60, 30, 5)
    max_activos = st.slider("Número máximo de activos a monitorear", 1, 5, 5, 1)

    st.markdown("---")
    if st.session_state.conectado:
        if not st.session_state.monitoreando:
            if st.button("▶️ INICIAR", use_container_width=True, type="primary"):
                st.session_state.monitoreando = True
                st.session_state.log.append("🚀 Monitoreo iniciado")
                st.session_state.activos_totales = obtener_activos_abiertos(st.session_state.api, tipo_mercado)
                # Seleccionar los mejores activos
                with st.spinner("Seleccionando los mejores activos..."):
                    mejores = seleccionar_activos_fuertes(st.session_state.api, st.session_state.activos_totales, max_activos)
                    st.session_state.activos_monitoreo = mejores
                    st.session_state.log.append(f"✅ Activos seleccionados: {', '.join([a['asset'] for a in mejores])}")
                st.rerun()
        else:
            if st.button("⏹️ DETENER", use_container_width=True, type="secondary"):
                st.session_state.monitoreando = False
                st.rerun()

    if st.session_state.conectado:
        st.metric("💰 Saldo", f"${st.session_state.saldo:.2f}")

# Área principal
if st.session_state.conectado:
    st.title("📊 Estrategia de Niveles Clave (1 minuto)")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Saldo", f"${st.session_state.saldo:.2f}")
    with col2:
        st.metric("Activos en seguimiento", len(st.session_state.activos_monitoreo))
    with col3:
        st.metric("Señales activas", len(st.session_state.señales_activas))

    # Mostrar tarjetas de los activos
    if st.session_state.activos_monitoreo:
        cols = st.columns(len(st.session_state.activos_monitoreo))
        for idx, activo_data in enumerate(st.session_state.activos_monitoreo):
            with cols[idx]:
                asset = activo_data['asset']
                tendencia = activo_data['tendencia']
                fuerza = activo_data['fuerza']
                # Verificar si ya hay una señal activa para este activo
                senal = st.session_state.señales_activas.get(asset)
                if senal and senal.get('activa'):
                    # Tarjeta con señal activa
                    card_class = "signal-call" if senal['direccion'] == "CALL" else "signal-put"
                    st.markdown(f"""
                    <div class="asset-card {card_class}">
                        <div class="asset-name">{asset}</div>
                        <div class="asset-status">✅ SEÑAL ACTIVA</div>
                        <div><strong>{senal['direccion']}</strong> - {senal['descripcion']}</div>
                        <div>Entrada: {senal['entrada']}</div>
                        <div>Vencimiento: {senal['vencimiento']}</div>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    # Tarjeta neutra
                    estado = "NEUTRO - Esperando nivel"
                    st.markdown(f"""
                    <div class="asset-card signal-neutral">
                        <div class="asset-name">{asset}</div>
                        <div class="asset-status">⚪ {estado}</div>
                        <div>Tendencia: {tendencia if tendencia else 'No definida'}</div>
                        <div>Fuerza: {fuerza:.1f}%</div>
                        <div class="force-bar"><div class="force-fill" style="width: {fuerza}%;"></div></div>
                    </div>
                    """, unsafe_allow_html=True)

    # Log de eventos
    with st.expander("📋 Log de eventos", expanded=True):
        for linea in st.session_state.log[-20:]:
            st.text(linea)

    # Lógica de monitoreo
    if st.session_state.monitoreando:
        now = datetime.now(ecuador)
        # Calcular próximo cierre de vela de 1 minuto (para sincronización)
        # Pero para simplificar, analizamos cada segundo y generamos señal cuando se alcanza nivel
        # En realidad, deberíamos tener un loop que revise constantemente los precios.
        # Como Streamlit no es tiempo real, simulamos con rerun cada segundo.

        # Primero, verificar si alguna señal activa ha expirado (1 min después de entrada)
        activas = st.session_state.señales_activas.copy()
        for asset, senal in activas.items():
            if senal.get('activa'):
                entrada_dt = datetime.strptime(senal['entrada'], "%H:%M:%S").time()
                entrada_completa = datetime.combine(now.date(), entrada_dt)
                entrada_completa = ecuador.localize(entrada_completa)
                if entrada_completa > now:
                    entrada_completa -= timedelta(days=1)
                expiracion = entrada_completa + timedelta(minutes=1)
                if now >= expiracion:
                    senal['activa'] = False
                    st.session_state.señales_activas[asset] = senal
                    st.session_state.log.append(f"🗑️ Señal expirada para {asset}")
                    # Opcional: si la señal era ganadora, podríamos decidir si seguir con el mismo activo
                    # Por simplicidad, solo la eliminamos.

        # Evaluar activos en busca de nuevos niveles
        for activo_data in st.session_state.activos_monitoreo:
            asset = activo_data['asset']
            # Si ya tiene señal activa, saltar
            if st.session_state.señales_activas.get(asset, {}).get('activa'):
                continue

            # Obtener datos actualizados del activo
            res = evaluar_activo(st.session_state.api, asset)
            if res is None:
                continue
            tendencia = res['tendencia']
            fuerza = res['fuerza']
            # Actualizar fuerza en activo_data
            activo_data['fuerza'] = fuerza
            activo_data['tendencia'] = tendencia

            # Si no hay tendencia clara, no operamos
            if tendencia is None:
                continue

            # Buscar niveles (soportes/resistencias) o líneas de tendencia
            # Ver si el precio actual está cerca de algún nivel
            precio = res['precio']
            atr = res.get('atr', 0.001)
            umbral = 0.5 * atr / precio  # 0.5 ATR como distancia máxima
            nivel_encontrado = None
            direccion_esperada = None
            descripcion = ""

            # 1. Verificar soporte/resistencia horizontal
            for nivel in res['niveles']:
                distancia = abs(precio - nivel['precio']) / precio
                if distancia < umbral:
                    if nivel['tipo'] == 'soporte' and tendencia == 'CALL':
                        nivel_encontrado = nivel['precio']
                        direccion_esperada = 'CALL'
                        descripcion = f"Soporte {nivel['precio']:.5f} ({nivel['toques']} toques)"
                        break
                    elif nivel['tipo'] == 'resistencia' and tendencia == 'PUT':
                        nivel_encontrado = nivel['precio']
                        direccion_esperada = 'PUT'
                        descripcion = f"Resistencia {nivel['precio']:.5f} ({nivel['toques']} toques)"
                        break

            # 2. Si no hay nivel horizontal, buscar línea de tendencia
            if not nivel_encontrado:
                for linea in res['lineas']:
                    distancia = abs(precio - linea['precio']) / precio
                    if distancia < umbral:
                        if linea['tipo'] == 'alcista' and tendencia == 'CALL':
                            nivel_encontrado = linea['precio']
                            direccion_esperada = 'CALL'
                            descripcion = f"Línea tendencia alcista"
                            break
                        elif linea['tipo'] == 'bajista' and tendencia == 'PUT':
                            nivel_encontrado = linea['precio']
                            direccion_esperada = 'PUT'
                            descripcion = f"Línea tendencia bajista"
                            break

            if nivel_encontrado and direccion_esperada:
                # Generar señal para entrada en la próxima vela (1 minuto después)
                # Calculamos la próxima vela de 1 minuto
                now_utc = now.astimezone(pytz.UTC)
                minute = now_utc.minute
                start_minute = minute  # la vela actual termina en 60 - segundos
                # Simplemente, la entrada será dentro de 1 minuto (próxima vela)
                entrada_dt = now + timedelta(minutes=1)
                entrada_dt = entrada_dt.replace(second=0, microsecond=0)
                entrada_str = entrada_dt.strftime("%H:%M:%S")
                vencimiento_str = (entrada_dt + timedelta(minutes=1)).strftime("%H:%M:%S")
                st.session_state.señales_activas[asset] = {
                    'activa': True,
                    'direccion': direccion_esperada,
                    'descripcion': descripcion,
                    'entrada': entrada_str,
                    'vencimiento': vencimiento_str,
                    'fuerza': fuerza
                }
                st.session_state.log.append(f"🚀 SEÑAL: {asset} - {direccion_esperada} a las {entrada_str} (Nivel: {descripcion})")
                # Forzar rerun para mostrar la tarjeta
                st.rerun()

        # Actualizar el session_state con los nuevos valores de fuerza/tendencia
        # (se actualizó in-place)

        # Esperar 1 segundo y volver a evaluar
        time.sleep(1)
        st.rerun()

else:
    st.info("🔒 Conéctate a IQ Option para comenzar.")

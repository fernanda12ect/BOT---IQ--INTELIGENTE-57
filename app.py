import streamlit as st
import html
from datetime import datetime, timedelta
import pytz
from bot import escanear_activos_por_grupos, obtener_todos_activos, REAL_ASSETS, OTC_ASSETS
from iqoptionapi.stable_api import IQ_Option

st.set_page_config(layout="wide")
st.title("🤖 IQ OPTION PRO SIGNAL BOT")

# Inicializar session_state
if 'api' not in st.session_state:
    st.session_state.api = None
if 'ultima_senal' not in st.session_state:
    st.session_state.ultima_senal = None
if 'todos_activos' not in st.session_state:
    st.session_state.todos_activos = None
if 'cooldown_until' not in st.session_state:
    st.session_state.cooldown_until = None

# Sidebar de configuración
with st.sidebar:
    st.header("⚙️ Configuración")
    email = st.text_input("📧 Email")
    password = st.text_input("🔑 Password", type="password")
    
    conjunto_activos = st.selectbox("📊 Conjunto de activos", 
                                    ["Predefinidos (REAL/OTC)", "Todos los disponibles"])
    
    if conjunto_activos == "Predefinidos (REAL/OTC)":
        tipo_activos = st.radio("Tipo", ["REAL", "OTC", "AMBOS"])
    else:
        tipo_activos = "AMBOS"  # Para todos, no aplica filtro
    
    # NOTA: Se eliminó el campo "Máx. activos"
    
    col1, col2 = st.columns(2)
    with col1:
        conectar = st.button("🔌 Conectar")
    with col2:
        desconectar = st.button("⛔ Desconectar")

# Lógica de conexión
if conectar:
    if not email or not password:
        st.error("❌ Por favor ingresa email y password")
    else:
        try:
            API = IQ_Option(email, password)
            check, reason = API.connect()  # Ajustar según documentación real
            if check:
                st.session_state.api = API
                st.session_state.todos_activos = None
                st.session_state.ultima_senal = None
                st.session_state.cooldown_until = None
                st.success("✅ Conectado a IQ Option")
            else:
                st.error(f"❌ Error de conexión: {reason}")
        except Exception as e:
            st.error(f"Error inesperado: {e}")

if desconectar:
    st.session_state.api = None
    st.session_state.todos_activos = None
    st.session_state.ultima_senal = None
    st.session_state.cooldown_until = None
    st.success("Desconectado")

# Área principal
if st.session_state.api is not None:
    st.info("🔌 Conectado. Listo para escanear.")

    # Botón de escaneo con cooldown (siempre booleano)
    cooldown_active = st.session_state.cooldown_until is not None and datetime.now() < st.session_state.cooldown_until
    escanear_btn = st.button("🔍 Escanear ahora", disabled=cooldown_active)
    
    if escanear_btn:
        if cooldown_active:
            st.warning(f"⏳ Cooldown activo. Espera hasta las {st.session_state.cooldown_until.strftime('%H:%M:%S')} para escanear de nuevo.")
        else:
            # Construir lista de activos
            if conjunto_activos == "Predefinidos (REAL/OTC)":
                activos = []
                if tipo_activos in ["REAL", "AMBOS"]:
                    activos.extend(REAL_ASSETS)
                if tipo_activos in ["OTC", "AMBOS"]:
                    activos.extend(OTC_ASSETS)
            else:  # Todos los disponibles
                if st.session_state.todos_activos is None:
                    with st.spinner("Obteniendo lista de activos..."):
                        st.session_state.todos_activos = obtener_todos_activos(st.session_state.api)
                activos = st.session_state.todos_activos

            # Escanear por grupos (sin límite de activos)
            with st.spinner(f"Escaneando {len(activos)} activos en grupos de 20..."):
                try:
                    senal = escanear_activos_por_grupos(
                        st.session_state.api,
                        activos=activos,
                        batch_size=20,
                        timeout_seconds=60  # Puedes ajustar
                    )
                    if senal:
                        st.session_state.ultima_senal = senal
                        # Calcular cooldown (entrada + 1 minuto)
                        entry_utc = datetime.strptime(senal['entry_utc'], "%Y-%m-%d %H:%M:%S")
                        entry_utc = entry_utc.replace(tzinfo=pytz.UTC)
                        cooldown = entry_utc + timedelta(minutes=1)
                        st.session_state.cooldown_until = cooldown.astimezone(ecuador)
                        st.success("✅ Señal encontrada!")
                    else:
                        st.warning("No se encontraron señales con probabilidad ≥80% después de revisar todos los activos.")
                except Exception as e:
                    st.error(f"Error durante el escaneo: {e}")

    # Mostrar última señal si existe
    if st.session_state.ultima_senal:
        signal = st.session_state.ultima_senal
        # Determinar tipo de activo
        asset = signal['asset']
        if "-OTC" in asset:
            tipo_mostrar = "OTC"
            asset_clean = asset.replace("-OTC", "")
        else:
            tipo_mostrar = "REAL"
            asset_clean = asset

        color = "#006400" if signal["direction"] == "CALL" else "#8B0000"

        asset_display = html.escape(f"{asset_clean} {tipo_mostrar}")
        direction = html.escape(signal['direction'])
        entry = html.escape(signal['entry'])
        expiry = html.escape(signal['expiry'])
        prob = html.escape(str(signal['prob']))
        strategy = html.escape(signal['strategy'])

        html_code = f"""
        <div style="display:flex; justify-content:space-between; background:#111; padding:40px; border-radius:20px; border:4px solid {color}; box-shadow: 0 0 15px rgba(0,0,0,0.5);">
            <div>
                <h1 style="margin-bottom:5px;">{asset_display}</h1>
                <h3 style="color:#ccc;">OPERAR</h3>
                <h2 style="color:#fff;">{entry}</h2>
                <h3 style="color:#ccc;">EXPIRA</h3>
                <h2 style="color:#fff;">{expiry}</h2>
            </div>
            <div style="text-align:right;">
                <h1 style="color:{color}; font-size:4rem; margin:0;">{direction}</h1>
                <h3 style="color:#ccc;">PROBABILIDAD</h3>
                <h1 style="color:#fff;">{prob}%</h1>
                <h4 style="color:#888;">{strategy}</h4>
            </div>
        </div>
        """
        st.markdown(html_code, unsafe_allow_html=True)

        with st.expander("📅 Ver detalles UTC"):
            st.write(f"**Entrada UTC:** {signal['entry_utc']}")
            st.write(f"**Expiración UTC:** {signal['expiry_utc']}")
            if st.session_state.cooldown_until:
                st.write(f"**Próximo escaneo permitido:** {st.session_state.cooldown_until.strftime('%H:%M:%S')} (hora Ecuador)")
    else:
        if st.session_state.api is not None:
            st.info("No hay señales aún. Presiona 'Escanear ahora'.")
else:
    st.warning("🔒 Por favor, conéctate primero desde el panel izquierdo.")

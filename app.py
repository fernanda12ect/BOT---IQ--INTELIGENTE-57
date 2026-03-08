import streamlit as st
import html
import time
from datetime import datetime, timedelta
import pytz
from bot import escanear_activos_por_grupos, obtener_todos_activos, REAL_ASSETS, OTC_ASSETS
from iqoptionapi.stable_api import IQ_Option

st.set_page_config(layout="wide")
st.title("🤖 IQ OPTION PRO SIGNAL BOT (Escaneo Continuo)")

# Inicializar session_state
if 'api' not in st.session_state:
    st.session_state.api = None
if 'ultima_senal' not in st.session_state:
    st.session_state.ultima_senal = None
if 'todos_activos' not in st.session_state:
    st.session_state.todos_activos = None
if 'cooldown_until' not in st.session_state:
    st.session_state.cooldown_until = None
if 'escaneo_activo' not in st.session_state:
    st.session_state.escaneo_activo = False
if 'ultimo_escaneo' not in st.session_state:
    st.session_state.ultimo_escaneo = None

# Zona horaria Ecuador
ecuador = pytz.timezone("America/Guayaquil")

# Sidebar
with st.sidebar:
    st.header("⚙️ Configuración")
    email = st.text_input("📧 Email")
    password = st.text_input("🔑 Password", type="password")
    
    conjunto_activos = st.selectbox("📊 Conjunto de activos", 
                                    ["Predefinidos (REAL/OTC)", "Todos los disponibles"])
    
    if conjunto_activos == "Predefinidos (REAL/OTC)":
        tipo_activos = st.radio("Tipo", ["REAL", "OTC", "AMBOS"])
    else:
        tipo_activos = "AMBOS"
    
    # Intervalo entre rondas de escaneo (segundos)
    intervalo_rondas = st.number_input("⏱️ Intervalo entre rondas (seg)", min_value=10, max_value=300, value=30, step=5)
    
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
            check, reason = API.connect()
            if check:
                st.session_state.api = API
                st.session_state.todos_activos = None
                st.session_state.ultima_senal = None
                st.session_state.cooldown_until = None
                st.session_state.escaneo_activo = False
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
    st.session_state.escaneo_activo = False
    st.success("Desconectado")

# Área principal
if st.session_state.api is not None:
    st.info("🔌 Conectado. Listo para escanear.")

    # Botón de inicio/parada de escaneo continuo
    if not st.session_state.escaneo_activo:
        if st.button("▶️ Iniciar escaneo continuo"):
            st.session_state.escaneo_activo = True
            st.rerun()
    else:
        if st.button("⏹️ Detener escaneo"):
            st.session_state.escaneo_activo = False
            st.rerun()

    # Mostrar estado del escaneo
    if st.session_state.escaneo_activo:
        st.markdown("**Estado:** 🟢 Escaneo continuo activo")
        if st.session_state.cooldown_until and datetime.now() < st.session_state.cooldown_until:
            st.warning(f"⏳ Cooldown activo hasta las {st.session_state.cooldown_until.strftime('%H:%M:%S')} (hora Ecuador). Esperando...")
    else:
        st.markdown("**Estado:** ⚪ Escaneo detenido")

    # Lógica de escaneo continuo
    if st.session_state.escaneo_activo:
        # Verificar cooldown
        if st.session_state.cooldown_until and datetime.now() < st.session_state.cooldown_until:
            # Esperar hasta que termine el cooldown
            tiempo_restante = (st.session_state.cooldown_until - datetime.now()).total_seconds()
            st.info(f"Esperando {tiempo_restante:.0f} segundos por cooldown...")
            time.sleep(min(tiempo_restante, 1))  # Esperar en pequeños intervalos para no congelar
            st.rerun()
        else:
            # Realizar una ronda de escaneo
            with st.spinner("Preparando escaneo..."):
                # Obtener lista de activos
                if conjunto_activos == "Predefinidos (REAL/OTC)":
                    activos = []
                    if tipo_activos in ["REAL", "AMBOS"]:
                        activos.extend(REAL_ASSETS)
                    if tipo_activos in ["OTC", "AMBOS"]:
                        activos.extend(OTC_ASSETS)
                else:
                    if st.session_state.todos_activos is None:
                        with st.spinner("Obteniendo lista de activos..."):
                            st.session_state.todos_activos = obtener_todos_activos(st.session_state.api)
                    activos = st.session_state.todos_activos

                total_activos = len(activos)
                st.info(f"📊 Total de activos a escanear: {total_activos}")

                # Escanear por grupos de 20
                grupo_size = 20
                señal_encontrada = None

                # Usar un placeholder para mostrar progreso
                progreso = st.empty()

                for i in range(0, total_activos, grupo_size):
                    grupo = activos[i:i+grupo_size]
                    progreso.info(f"Escaneando grupo {i//grupo_size + 1} de {(total_activos-1)//grupo_size + 1} (activos {i+1} a {min(i+grupo_size, total_activos)})...")
                    
                    # Escanear el grupo
                    señal = escanear_activos_por_grupos(
                        st.session_state.api,
                        activos=grupo,
                        grupo_size=grupo_size,
                        timeout_seconds=30  # Timeout por grupo, no por total
                    )
                    
                    if señal:
                        señal_encontrada = señal
                        break
                    
                    # Pequeña pausa entre grupos (opcional)
                    time.sleep(0.5)

                progreso.empty()

                if señal_encontrada:
                    st.session_state.ultima_senal = señal_encontrada
                    # Calcular cooldown: entrada (hora UTC) + 1 minuto
                    entry_utc = datetime.strptime(señal['entry_utc'], "%Y-%m-%d %H:%M:%S")
                    entry_utc = entry_utc.replace(tzinfo=pytz.UTC)
                    cooldown = entry_utc + timedelta(minutes=1)
                    st.session_state.cooldown_until = cooldown.astimezone(ecuador)
                    st.success("✅ ¡Señal encontrada!")
                else:
                    st.info("No se encontraron señales en esta ronda.")

            # Esperar el intervalo antes de la siguiente ronda (si sigue activo)
            if st.session_state.escaneo_activo:
                st.info(f"Esperando {intervalo_rondas} segundos para la próxima ronda...")
                time.sleep(intervalo_rondas)
                st.rerun()

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
            st.info("No hay señales aún. Inicia el escaneo continuo para buscar.")

else:
    st.warning("🔒 Por favor, conéctate primero desde el panel izquierdo.")

import streamlit as st
import pandas as pd
import html
import time
from datetime import datetime, timedelta
import pytz
from bot import (
    obtener_activos_abiertos,
    calcular_indicadores,
    evaluar_estrategias,
    evaluar_punto_entrada,
    REAL_ASSETS,
    OTC_ASSETS
)
from iqoptionapi.stable_api import IQ_Option

st.set_page_config(layout="wide")
st.title("🤖 IQ OPTION PRO - ESTRATEGIAS CON PUNTO DE ENTRADA DINÁMICO")

# Inicializar session_state
if 'api' not in st.session_state:
    st.session_state.api = None
if 'activos_reales' not in st.session_state:
    st.session_state.activos_reales = []
if 'activos_otc' not in st.session_state:
    st.session_state.activos_otc = []
if 'señales_activas' not in st.session_state:
    st.session_state.señales_activas = []  # Lista de dicts con señal + estado
if 'escaneando' not in st.session_state:
    st.session_state.escaneando = False
if 'indice_activo' not in st.session_state:
    st.session_state.indice_activo = 0
if 'activos_a_escanear' not in st.session_state:
    st.session_state.activos_a_escanear = []
if 'historial' not in st.session_state:
    st.session_state.historial = []

# Zona horaria Ecuador
ecuador = pytz.timezone("America/Guayaquil")

# Sidebar
with st.sidebar:
    st.header("⚙️ Configuración")
    email = st.text_input("📧 Email")
    password = st.text_input("🔑 Password", type="password")

    # Umbral de fuerza mínima para considerar una señal
    umbral_fuerza = st.slider("🎯 Fuerza mínima para mostrar (%)", 0, 100, 40, 5)

    # Número máximo de tarjetas a mostrar
    max_tarjetas = 4

    # Tiempo de espera entre rondas completas (segundos)
    pausa_entre_rondas = st.number_input("⏱️ Pausa entre rondas (seg)", min_value=5, max_value=120, value=20)

    col1, col2 = st.columns(2)
    with col1:
        conectar = st.button("🔌 Conectar")
    with col2:
        desconectar = st.button("⛔ Desconectar")

    if st.session_state.api is not None and not st.session_state.escaneando:
        if st.button("▶️ Reiniciar escaneo"):
            real, otc = obtener_activos_abiertos(st.session_state.api)
            st.session_state.activos_reales = real
            st.session_state.activos_otc = otc
            st.session_state.activos_a_escanear = real + otc
            st.session_state.indice_activo = 0
            st.session_state.historial = []
            st.session_state.señales_activas = []
            st.session_state.escaneando = True
            st.rerun()

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
                real, otc = obtener_activos_abiertos(API)
                st.session_state.activos_reales = real
                st.session_state.activos_otc = otc
                st.session_state.activos_a_escanear = real + otc
                st.session_state.indice_activo = 0
                st.session_state.historial = []
                st.session_state.señales_activas = []
                st.session_state.escaneando = True
                st.success("✅ Conectado - Escaneo iniciado")
                st.rerun()
            else:
                st.error(f"❌ Error de conexión: {reason}")
        except Exception as e:
            st.error(f"Error inesperado: {e}")

if desconectar:
    st.session_state.api = None
    st.session_state.activos_reales = []
    st.session_state.activos_otc = []
    st.session_state.activos_a_escanear = []
    st.session_state.indice_activo = 0
    st.session_state.historial = []
    st.session_state.señales_activas = []
    st.session_state.escaneando = False
    st.success("Desconectado")
    st.rerun()

# Área principal
if st.session_state.api is not None:
    st.info("🔌 Conectado.")

    real_count = len(st.session_state.activos_reales)
    otc_count = len(st.session_state.activos_otc)
    if real_count > 0:
        st.success(f"🌍 REAL: {real_count} | 📱 OTC: {otc_count}")
    else:
        st.warning(f"⚠️ Mercado REAL cerrado - Solo OTC ({otc_count} disponibles)")

    # --- SECCIÓN DE SEÑALES ACTIVAS (hasta 4 tarjetas) ---
    st.subheader(f"📊 Señales activas (máx {max_tarjetas})")

    # Eliminar señales que ya perdieron validez (por tiempo o fuerza)
    now = datetime.now(ecuador)
    señales_vigentes = []
    for senal in st.session_state.señales_activas:
        # Si ya fue confirmada y la hora de entrada ya pasó, se considera expirada
        if senal.get('confirmada', False) and senal['entry_time'] <= now:
            st.session_state.historial.append(f"🗑️ Señal ejecutada: {senal['asset']}")
            continue
        # Si no está confirmada pero pasó mucho tiempo (ej. 10 min) desde que se creó, se puede eliminar
        # (opcional, para no acumular)
        if not senal.get('confirmada', False) and (now - senal['creacion']).total_seconds() > 600:  # 10 min
            st.session_state.historial.append(f"⏳ Señal caducada por espera: {senal['asset']}")
            continue
        señales_vigentes.append(senal)
    st.session_state.señales_activas = señales_vigentes

    # Mostrar tarjetas
    if st.session_state.señales_activas:
        # Ordenar: primero las confirmadas (listas para operar), luego por fuerza
        def prioridad(s):
            return (1 if s.get('confirmada', False) else 0, s['fuerza'])
        señales_ordenadas = sorted(st.session_state.señales_activas, key=prioridad, reverse=True)[:max_tarjetas]

        cols = st.columns(len(señales_ordenadas))
        for idx, senal in enumerate(señales_ordenadas):
            with cols[idx]:
                asset = senal['asset']
                if "-OTC" in asset:
                    tipo_mostrar = "📱 OTC"
                    asset_clean = asset.replace("-OTC", "")
                else:
                    tipo_mostrar = "🌍 REAL"
                    asset_clean = asset

                color = "#006400" if senal['direccion'] == "CALL" else "#8B0000"

                # Determinar estado visual
                if senal.get('confirmada', False):
                    estado_texto = "✅ CONFIRMADO - ENTRA AHORA"
                    countdown = ""  # No necesario
                else:
                    estado_texto = "⏳ ESPERANDO RETROCESO"
                    # Tiempo de espera (opcional)
                    countdown = ""

                asset_display = html.escape(f"{asset_clean} {tipo_mostrar}")
                direccion = html.escape(senal['direccion'])
                estrategia = html.escape(senal['estrategia'])
                entry = html.escape(senal['entry']) if senal.get('confirmada', False) else "---"
                expiry = html.escape(senal['expiry']) if senal.get('confirmada', False) else "---"
                fuerza = html.escape(str(senal['fuerza']))

                html_code = f"""
                <div style="background:#111; padding:20px; border-radius:15px; border:3px solid {color}; margin-bottom:10px;">
                    <h3 style="margin:0;">{asset_display}</h3>
                    <p style="color:{color}; font-size:1.5rem; margin:5px 0;">{direccion}</p>
                    <p><strong>Estrategia:</strong> {estrategia}</p>
                    <p><strong>Fuerza:</strong> {fuerza}%</p>
                    <p><strong>Entrada:</strong> {entry}</p>
                    <p><strong>Expira:</strong> {expiry}</p>
                    <p><strong>Estado:</strong> {estado_texto}</p>
                </div>
                """
                st.markdown(html_code, unsafe_allow_html=True)
    else:
        st.info("No hay señales activas en este momento.")

    # Historial
    if st.session_state.historial:
        with st.expander("📋 Historial de análisis", expanded=False):
            for linea in st.session_state.historial[-20:]:
                st.text(linea)

    # Lógica de escaneo continuo
    if st.session_state.escaneando:
        if not st.session_state.activos_a_escanear or st.session_state.indice_activo >= len(st.session_state.activos_a_escanear):
            # Nueva ronda
            real, otc = obtener_activos_abiertos(st.session_state.api)
            st.session_state.activos_reales = real
            st.session_state.activos_otc = otc
            st.session_state.activos_a_escanear = real + otc
            st.session_state.indice_activo = 0
            st.session_state.historial.append(f"🔄 Nueva ronda: {len(st.session_state.activos_a_escanear)} activos")
            if st.session_state.activos_a_escanear:
                st.info(f"Esperando {pausa_entre_rondas} segundos para nueva ronda...")
                time.sleep(pausa_entre_rondas)
                st.rerun()
            else:
                st.warning("No hay activos disponibles.")
                st.session_state.escaneando = False
                st.rerun()
        else:
            asset = st.session_state.activos_a_escanear[st.session_state.indice_activo]
            tipo = "🌍 REAL" if "-OTC" not in asset else "📱 OTC"
            st.markdown(f"### 🔍 Analizando: {tipo} {asset}")

            try:
                st.session_state.historial.append(f"{tipo} Analizando {asset}...")

                candles = st.session_state.api.get_candles(asset, 60, 100, time.time())
                if not candles or len(candles) < 50:
                    st.session_state.historial.append(f"⏭️ {asset}: datos insuficientes")
                    time.sleep(0.25)
                    st.session_state.indice_activo += 1
                    st.rerun()

                df = pd.DataFrame(candles)
                for col in ['open', 'max', 'min', 'close', 'volume']:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                df.dropna(inplace=True)

                if len(df) < 50:
                    st.session_state.historial.append(f"⏭️ {asset}: datos insuficientes después de limpieza")
                    time.sleep(0.25)
                    st.session_state.indice_activo += 1
                    st.rerun()

                indicators = calcular_indicadores(df)
                señales_encontradas = evaluar_estrategias(indicators)

                # Determinar la mejor señal para este activo
                mejor_senal = None
                if señales_encontradas:
                    mejor_senal = max(señales_encontradas, key=lambda x: x['fuerza'])

                # Obtener hora actual del servidor
                try:
                    server_time = st.session_state.api.get_server_time()
                    now_utc = datetime.fromtimestamp(server_time, tz=pytz.UTC)
                except:
                    now_utc = datetime.now(pytz.UTC)

                now_local = now_utc.astimezone(ecuador)

                # Buscar si el activo ya tiene una señal activa
                señal_existente = next((s for s in st.session_state.señales_activas if s['asset'] == asset), None)

                if mejor_senal and mejor_senal['fuerza'] >= umbral_fuerza:
                    # Hay señal válida
                    if señal_existente:
                        # Actualizar la señal existente
                        señal_existente['fuerza'] = mejor_senal['fuerza']
                        señal_existente['estrategia'] = mejor_senal['estrategia']
                        señal_existente['direccion'] = mejor_senal['direccion']
                        # No cambiar confirmación si ya estaba confirmada
                        if not señal_existente.get('confirmada', False):
                            # Evaluar punto de entrada
                            if evaluar_punto_entrada(indicators, mejor_senal['direccion']):
                                señal_existente['confirmada'] = True
                                # Fijar hora de entrada ahora
                                entrada_dt = now_utc + timedelta(minutes=1)  # 1 minuto para prepararse
                                entrada_dt = entrada_dt.replace(second=0, microsecond=0)
                                expiry_dt = entrada_dt + timedelta(minutes=5)
                                señal_existente['entry'] = entrada_dt.astimezone(ecuador).strftime("%H:%M:%S")
                                señal_existente['expiry'] = expiry_dt.astimezone(ecuador).strftime("%H:%M:%S")
                                señal_existente['entry_time'] = entrada_dt.astimezone(ecuador)
                                st.session_state.historial.append(f"✅ Confirmada entrada para {asset} a las {señal_existente['entry']}")
                            # Si no se confirma, se mantiene en espera
                        # La señal existente se actualiza, no se crea duplicado
                    else:
                        # Nueva señal, aún no confirmada
                        nueva_senal = {
                            "asset": asset,
                            "direccion": mejor_senal['direccion'],
                            "fuerza": mejor_senal['fuerza'],
                            "estrategia": mejor_senal['estrategia'],
                            "entry": "---",
                            "expiry": "---",
                            "entry_time": None,
                            "confirmada": False,
                            "creacion": now_local
                        }
                        st.session_state.señales_activas.append(nueva_senal)
                        st.session_state.historial.append(f"🎯 Nueva señal en {asset}: {mejor_senal['estrategia']} ({mejor_senal['fuerza']}%)")
                else:
                    # No hay señal válida para este activo
                    if señal_existente:
                        # Eliminar la señal si existe
                        st.session_state.señales_activas.remove(señal_existente)
                        st.session_state.historial.append(f"❌ Señal eliminada: {asset} (dejó de cumplir)")

                # Después de modificar, ordenar y limitar a las 4 más fuertes (priorizando confirmadas)
                # Primero separamos confirmadas y no confirmadas
                confirmadas = [s for s in st.session_state.señales_activas if s.get('confirmada', False)]
                no_confirmadas = [s for s in st.session_state.señales_activas if not s.get('confirmada', False)]
                # Ordenar no confirmadas por fuerza
                no_confirmadas.sort(key=lambda x: x['fuerza'], reverse=True)
                # Unir: todas las confirmadas (sin límite) más las no confirmadas hasta completar max_tarjetas
                final = confirmadas + no_confirmadas[:max_tarjetas - len(confirmadas)]
                st.session_state.señales_activas = final

                time.sleep(0.25)
                st.session_state.indice_activo += 1
                st.rerun()

            except Exception as e:
                st.session_state.historial.append(f"⚠️ Error en {asset}: {str(e)[:50]}")
                time.sleep(0.25)
                st.session_state.indice_activo += 1
                st.rerun()

else:
    st.warning("🔒 Por favor, conéctate primero desde el panel izquierdo.")

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
    st.session_state.señales_activas = []
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

    # Umbral de fuerza mínima para mostrar señal
    umbral_fuerza = st.slider("🎯 Fuerza mínima para mostrar (%)", 0, 100, 30, 5)

    # Número máximo de tarjetas a mostrar
    max_tarjetas = 4

    # Tiempo de espera entre rondas completas (segundos)
    pausa_entre_rondas = st.number_input("⏱️ Pausa entre rondas (seg)", min_value=5, max_value=120, value=15)

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

    # --- SECCIÓN DE SEÑALES ACTIVAS ---
    st.subheader(f"📊 Señales activas (máx {max_tarjetas})")

    # Eliminar señales que ya perdieron validez
    now = datetime.now(ecuador)
    señales_vigentes = []
    for senal in st.session_state.señales_activas:
        # Si está confirmada y la hora de entrada ya pasó, se considera ejecutada
        if senal.get('estado') == 'CONFIRMADA' and senal['entry_time'] <= now:
            st.session_state.historial.append(f"🗑️ Señal ejecutada: {senal['asset']}")
            continue
        # Si está en pre-entrada (PREPARANDO) y la hora de entrada ya pasó, pasa a confirmada (esto no debería pasar porque se actualiza)
        if senal.get('estado') == 'PREPARANDO' and senal['entry_time'] <= now:
            # Cambiar a confirmada
            senal['estado'] = 'CONFIRMADA'
            # No se elimina
        # Si está en espera y ha pasado mucho tiempo (10 min) sin activarse, se elimina
        if senal.get('estado') == 'ESPERA' and (now - senal['creacion']).total_seconds() > 600:
            st.session_state.historial.append(f"⏳ Señal caducada por espera: {senal['asset']}")
            continue
        señales_vigentes.append(senal)
    st.session_state.señales_activas = señales_vigentes

    # Mostrar tarjetas
    if st.session_state.señales_activas:
        # Prioridad: confirmadas, luego preparando, luego espera, y por fuerza
        def prioridad(s):
            orden = {'CONFIRMADA': 3, 'PREPARANDO': 2, 'ESPERA': 1}
            return (orden.get(s.get('estado', 'ESPERA'), 0), s['fuerza'])
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
                estado = senal.get('estado', 'ESPERA')
                if estado == 'CONFIRMADA':
                    estado_texto = "✅ CONFIRMADO - ENTRA AHORA"
                    # Mostrar hora de entrada
                    entry_show = senal['entry']
                    expiry_show = senal['expiry']
                    # Calcular tiempo restante para la entrada (si es futuro)
                    if senal['entry_time'] > now:
                        resto = (senal['entry_time'] - now).total_seconds()
                        mins, secs = divmod(int(resto), 60)
                        countdown = f" (en {mins}m {secs}s)"
                    else:
                        countdown = " (YA)"
                elif estado == 'PREPARANDO':
                    estado_texto = f"⏳ ENTRADA EN 1 MINUTO - {senal['entry']}"
                    entry_show = senal['entry']
                    expiry_show = senal['expiry']
                    resto = (senal['entry_time'] - now).total_seconds()
                    if resto > 0:
                        mins, secs = divmod(int(resto), 60)
                        countdown = f" (faltan {mins}m {secs}s)"
                    else:
                        countdown = " (YA)"
                else:  # ESPERA
                    estado_texto = "⏳ ESPERANDO RETROCESO"
                    entry_show = "---"
                    expiry_show = "---"
                    countdown = ""

                asset_display = html.escape(f"{asset_clean} {tipo_mostrar}")
                direccion = html.escape(senal['direccion'])
                estrategia = html.escape(senal['estrategia'])
                fuerza = html.escape(str(senal['fuerza']))

                html_code = f"""
                <div style="background:#111; padding:20px; border-radius:15px; border:3px solid {color}; margin-bottom:10px;">
                    <h3 style="margin:0;">{asset_display}</h3>
                    <p style="color:{color}; font-size:1.5rem; margin:5px 0;">{direccion}</p>
                    <p><strong>Estrategia:</strong> {estrategia}</p>
                    <p><strong>Fuerza:</strong> {fuerza}%</p>
                    <p><strong>Entrada:</strong> {entry_show}</p>
                    <p><strong>Expira:</strong> {expiry_show}</p>
                    <p><strong>Estado:</strong> {estado_texto}{countdown}</p>
                </div>
                """
                st.markdown(html_code, unsafe_allow_html=True)
    else:
        st.info("No hay señales activas en este momento.")

    # Historial
    if st.session_state.historial:
        with st.expander("📋 Historial de análisis", expanded=True):
            for linea in st.session_state.historial[-30:]:
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
                # Añadir línea de análisis
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

                # Mostrar en historial los valores clave para depuración
                debug_msg = f"📊 {asset}: ADX={indicators['adx']:.1f}, RSI={indicators['rsi']:.1f}, Vol rel={indicators['vol_actual']/indicators['vol_promedio']:.2f}, cerca Sop={indicators['cerca_soporte']}, cerca Res={indicators['cerca_resistencia']}"
                st.session_state.historial.append(debug_msg)

                mejor_senal = None
                if señales_encontradas:
                    mejor_senal = max(señales_encontradas, key=lambda x: x['fuerza'])

                # Obtener hora del servidor
                try:
                    server_time = st.session_state.api.get_server_time()
                    now_utc = datetime.fromtimestamp(server_time, tz=pytz.UTC)
                except:
                    now_utc = datetime.now(pytz.UTC)
                now_local = now_utc.astimezone(ecuador)

                señal_existente = next((s for s in st.session_state.señales_activas if s['asset'] == asset), None)

                if mejor_senal and mejor_senal['fuerza'] >= umbral_fuerza:
                    # Hay señal válida
                    if señal_existente:
                        # Actualizar la señal existente
                        señal_existente['fuerza'] = mejor_senal['fuerza']
                        señal_existente['estrategia'] = mejor_senal['estrategia']
                        señal_existente['direccion'] = mejor_senal['direccion']
                        # Si está en espera, verificar si se alcanza punto de entrada
                        if señal_existente.get('estado') == 'ESPERA':
                            if evaluar_punto_entrada(indicators, mejor_senal['direccion']):
                                # Punto de entrada alcanzado: pasar a PREPARANDO con entrada en 1 minuto
                                entrada_dt = now_utc + timedelta(minutes=1)
                                entrada_dt = entrada_dt.replace(second=0, microsecond=0)
                                expiry_dt = entrada_dt + timedelta(minutes=5)
                                señal_existente['estado'] = 'PREPARANDO'
                                señal_existente['entry'] = entrada_dt.astimezone(ecuador).strftime("%H:%M:%S")
                                señal_existente['expiry'] = expiry_dt.astimezone(ecuador).strftime("%H:%M:%S")
                                señal_existente['entry_time'] = entrada_dt.astimezone(ecuador)
                                st.session_state.historial.append(f"⏳ {asset}: punto de entrada alcanzado, operar a las {señal_existente['entry']}")
                        elif señal_existente.get('estado') == 'PREPARANDO':
                            # Si ya está en preparando, verificar si ya es hora de confirmar
                            if señal_existente['entry_time'] <= now_local:
                                señal_existente['estado'] = 'CONFIRMADA'
                                st.session_state.historial.append(f"✅ {asset}: ¡ENTRA AHORA!")
                        # Si está confirmada, no hacemos nada (ya se operó)
                    else:
                        # Nueva señal, estado inicial ESPERA
                        nueva_senal = {
                            "asset": asset,
                            "direccion": mejor_senal['direccion'],
                            "fuerza": mejor_senal['fuerza'],
                            "estrategia": mejor_senal['estrategia'],
                            "entry": "---",
                            "expiry": "---",
                            "entry_time": None,
                            "estado": "ESPERA",
                            "creacion": now_local
                        }
                        st.session_state.señales_activas.append(nueva_senal)
                        st.session_state.historial.append(f"🎯 Nueva señal en {asset}: {mejor_senal['estrategia']} ({mejor_senal['fuerza']}%)")
                else:
                    # No hay señal válida para este activo
                    if señal_existente:
                        # Eliminar la señal si existe (excepto si ya está confirmada o preparando? mejor eliminarla porque perdió fuerza)
                        # Pero si está confirmada, no debería eliminarse aunque ya no cumpla, porque la operación está en curso
                        if señal_existente.get('estado') not in ['CONFIRMADA', 'PREPARANDO']:
                            st.session_state.señales_activas.remove(señal_existente)
                            st.session_state.historial.append(f"❌ Señal eliminada: {asset} (dejó de cumplir)")

                # Reordenar y limitar a máximo de tarjetas
                # Priorizamos las confirmadas y preparando sobre las de espera
                confirmadas = [s for s in st.session_state.señales_activas if s.get('estado') == 'CONFIRMADA']
                preparando = [s for s in st.session_state.señales_activas if s.get('estado') == 'PREPARANDO']
                espera = [s for s in st.session_state.señales_activas if s.get('estado') == 'ESPERA']
                espera.sort(key=lambda x: x['fuerza'], reverse=True)
                # Primero todas las confirmadas, luego todas las preparando, luego las espera hasta completar
                final = confirmadas + preparando + espera[:max_tarjetas - len(confirmadas) - len(preparando)]
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

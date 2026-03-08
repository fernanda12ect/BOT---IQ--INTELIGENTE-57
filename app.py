import streamlit as st
import pandas as pd
import html
import time
from datetime import datetime, timedelta
import pytz
from bot import (
    obtener_activos_abiertos,
    calcular_indicadores,
    evaluar_tendencia,
    calcular_nivel_retroceso
)
from iqoptionapi.stable_api import IQ_Option

st.set_page_config(layout="wide")
st.title("🤖 IQ OPTION PRO - SEGUIMIENTO DE 2 ACTIVOS CON RETROCESO")

# Inicializar session_state
if 'api' not in st.session_state:
    st.session_state.api = None
if 'activos_reales' not in st.session_state:
    st.session_state.activos_reales = []
if 'activos_otc' not in st.session_state:
    st.session_state.activos_otc = []
if 'escaneando' not in st.session_state:
    st.session_state.escaneando = False
if 'fase' not in st.session_state:
    st.session_state.fase = "seleccion"
if 'activos_seleccionados' not in st.session_state:
    st.session_state.activos_seleccionados = []
if 'señales_activas' not in st.session_state:
    st.session_state.señales_activas = []
if 'historial' not in st.session_state:
    st.session_state.historial = []

# Zona horaria Ecuador
ecuador = pytz.timezone("America/Guayaquil")

# Sidebar
with st.sidebar:
    st.header("⚙️ Configuración")
    email = st.text_input("📧 Email")
    password = st.text_input("🔑 Password", type="password")

    umbral_fuerza = st.slider("🎯 Fuerza mínima de tendencia", 0, 100, 40, 5)
    pausa_entre_rondas = st.number_input("⏱️ Pausa entre rondas", 5, 120, 15)

    col1, col2 = st.columns(2)
    with col1:
        conectar = st.button("🔌 Conectar")
    with col2:
        desconectar = st.button("⛔ Desconectar")

# Lógica de conexión
if conectar:
    if not email or not password:
        st.error("❌ Ingresa email y password")
    else:
        try:
            API = IQ_Option(email, password)
            check, reason = API.connect()
            if check:
                st.session_state.api = API
                real, otc = obtener_activos_abiertos(API)
                st.session_state.activos_reales = real
                st.session_state.activos_otc = otc
                st.session_state.escaneando = True
                st.session_state.fase = "seleccion"
                st.session_state.activos_seleccionados = []
                st.session_state.señales_activas = []
                st.session_state.historial = []
                st.success("✅ Conectado - Iniciando búsqueda de activos...")
                st.rerun()
            else:
                st.error(f"❌ Error de conexión: {reason}")
        except Exception as e:
            st.error(f"Error inesperado: {e}")

if desconectar:
    st.session_state.api = None
    st.session_state.escaneando = False
    st.session_state.activos_seleccionados = []
    st.session_state.señales_activas = []
    st.success("Desconectado")
    st.rerun()

# Área principal
if st.session_state.api is not None:
    real_count = len(st.session_state.activos_reales)
    otc_count = len(st.session_state.activos_otc)
    if real_count > 0:
        st.success(f"🌍 REAL: {real_count} | 📱 OTC: {otc_count}")
    else:
        st.warning(f"⚠️ Solo OTC ({otc_count})")

    # Mostrar señales activas
    if st.session_state.señales_activas:
        st.subheader("📊 SEÑALES LISTAS PARA OPERAR")
        for senal in st.session_state.señales_activas:
            asset = senal['asset']
            if "-OTC" in asset:
                tipo = "📱 OTC"
                asset_clean = asset.replace("-OTC", "")
            else:
                tipo = "🌍 REAL"
                asset_clean = asset
            color = "#006400" if senal['direccion'] == "CALL" else "#8B0000"

            html_code = f"""
            <div style="background:#111; padding:20px; border-radius:15px; border:3px solid {color}; margin-bottom:10px;">
                <h3>{asset_clean} {tipo}</h3>
                <p style="color:{color}; font-size:2rem;">{senal['direccion']}</p>
                <p><strong>Entrada:</strong> {senal['entry']}</p>
                <p><strong>Expira:</strong> {senal['expiry']}</p>
                <p><strong>Estrategia:</strong> {senal['estrategia']}</p>
                <p style="color:#0f0;">✅ LISTO PARA OPERAR</p>
            </div>
            """
            st.markdown(html_code, unsafe_allow_html=True)

    # Historial
    if st.session_state.historial:
        with st.expander("📋 Historial", expanded=True):
            for linea in st.session_state.historial[-20:]:
                st.text(linea)

    # Lógica de escaneo
    if st.session_state.escaneando:
        now = datetime.now(ecuador)

        # FASE DE SELECCIÓN
        if st.session_state.fase == "seleccion":
            st.info("🔍 Buscando los 2 mejores activos con tendencia...")
            todos_activos = st.session_state.activos_reales + st.session_state.activos_otc
            if not todos_activos:
                st.warning(f"No hay activos disponibles. Reintentando en {pausa_entre_rondas} segundos...")
                time.sleep(pausa_entre_rondas)
                real, otc = obtener_activos_abiertos(st.session_state.api)
                st.session_state.activos_reales = real
                st.session_state.activos_otc = otc
                st.rerun()

            candidatos = []
            for asset in todos_activos:
                try:
                    candles = st.session_state.api.get_candles(asset, 60, 100, time.time())
                    if not candles or len(candles) < 50:
                        continue
                    df = pd.DataFrame(candles)
                    # Asegurar nombres de columnas correctos
                    for col in ['open', 'high', 'low', 'close', 'volume']:
                        if col not in df.columns:
                            # Si la API devuelve con otros nombres, intentar mapear
                            if col == 'high' and 'max' in df.columns:
                                df.rename(columns={'max': 'high'}, inplace=True)
                            elif col == 'low' and 'min' in df.columns:
                                df.rename(columns={'min': 'low'}, inplace=True)
                            else:
                                df[col] = pd.to_numeric(df.get(col, 0), errors='coerce')
                        else:
                            df[col] = pd.to_numeric(df[col], errors='coerce')
                    df.dropna(inplace=True)
                    if len(df) < 50:
                        continue
                    indicators = calcular_indicadores(df)
                    res = evaluar_tendencia(indicators)
                    if res:
                        direccion, fuerza = res
                        if fuerza >= umbral_fuerza:
                            nivel = calcular_nivel_retroceso(indicators['df'], direccion)
                            candidatos.append({
                                'asset': asset,
                                'direccion': direccion,
                                'fuerza': fuerza,
                                'nivel_retroceso': nivel,
                                'precio_actual': indicators['close'],
                                'indicators': indicators
                            })
                except Exception as e:
                    st.session_state.historial.append(f"⚠️ Error con {asset}: {str(e)}")
                    continue
                time.sleep(0.1)

            if candidatos:
                candidatos.sort(key=lambda x: x['fuerza'], reverse=True)
                st.session_state.activos_seleccionados = candidatos[:2]
                st.session_state.fase = "seguimiento"
                st.session_state.historial.append(f"✅ Seleccionados: {candidatos[0]['asset']} ({candidatos[0]['fuerza']:.1f}%) y {candidatos[1]['asset']} ({candidatos[1]['fuerza']:.1f}%)")
                time.sleep(2)
                st.rerun()
            else:
                st.session_state.historial.append("⚠️ No se encontraron activos con tendencia suficiente. Reintentando...")
                time.sleep(pausa_entre_rondas)
                st.rerun()

        # FASE DE SEGUIMIENTO
        elif st.session_state.fase == "seguimiento":
            st.subheader("🔎 SIGUIENDO ACTIVOS SELECCIONADOS")
            for idx, activo in enumerate(st.session_state.activos_seleccionados):
                asset = activo['asset']
                precio_actual_str = f"{activo.get('precio_actual', 0):.5f}"
                st.write(f"**{idx+1}. {asset}** - Tendencia: {activo['direccion']} - Nivel retroceso: {activo['nivel_retroceso']:.5f} - Precio actual: {precio_actual_str}")

                try:
                    candles = st.session_state.api.get_candles(asset, 60, 5, time.time())
                    if not candles:
                        continue
                    df = pd.DataFrame(candles)
                    if 'close' in df.columns:
                        precio_actual = df['close'].iloc[-1]
                    else:
                        continue
                    activo['precio_actual'] = precio_actual

                    direccion = activo['direccion']
                    nivel = activo['nivel_retroceso']
                    if direccion == "CALL":
                        if precio_actual <= nivel * 1.001:
                            try:
                                server_time = st.session_state.api.get_server_time()
                                now_utc = datetime.fromtimestamp(server_time, tz=pytz.UTC)
                            except:
                                now_utc = datetime.now(pytz.UTC)
                            entry_dt = now_utc + timedelta(minutes=1)
                            entry_dt = entry_dt.replace(second=0, microsecond=0)
                            expiry_dt = entry_dt + timedelta(minutes=5)
                            entry_local = entry_dt.astimezone(ecuador)
                            expiry_local = expiry_dt.astimezone(ecuador)

                            señal = {
                                'asset': asset,
                                'direccion': 'CALL',
                                'entry': entry_local.strftime("%H:%M:%S"),
                                'expiry': expiry_local.strftime("%H:%M:%S"),
                                'estrategia': 'Retroceso alcanzado',
                                'fuerza': activo['fuerza']
                            }
                            st.session_state.señales_activas.append(señal)
                            st.session_state.historial.append(f"🎯 Señal CALL para {asset} a las {entry_local.strftime('%H:%M:%S')}")
                            st.session_state.activos_seleccionados.pop(idx)
                            break
                    else:  # PUT
                        if precio_actual >= nivel * 0.999:
                            try:
                                server_time = st.session_state.api.get_server_time()
                                now_utc = datetime.fromtimestamp(server_time, tz=pytz.UTC)
                            except:
                                now_utc = datetime.now(pytz.UTC)
                            entry_dt = now_utc + timedelta(minutes=1)
                            entry_dt = entry_dt.replace(second=0, microsecond=0)
                            expiry_dt = entry_dt + timedelta(minutes=5)
                            entry_local = entry_dt.astimezone(ecuador)
                            expiry_local = expiry_dt.astimezone(ecuador)

                            señal = {
                                'asset': asset,
                                'direccion': 'PUT',
                                'entry': entry_local.strftime("%H:%M:%S"),
                                'expiry': expiry_local.strftime("%H:%M:%S"),
                                'estrategia': 'Retroceso alcanzado',
                                'fuerza': activo['fuerza']
                            }
                            st.session_state.señales_activas.append(señal)
                            st.session_state.historial.append(f"🎯 Señal PUT para {asset} a las {entry_local.strftime('%H:%M:%S')}")
                            st.session_state.activos_seleccionados.pop(idx)
                            break
                except Exception as e:
                    st.session_state.historial.append(f"⚠️ Error monitoreando {asset}: {str(e)}")

            if len(st.session_state.activos_seleccionados) == 0:
                st.session_state.fase = "seleccion"
                st.rerun()
            else:
                time.sleep(pausa_entre_rondas)
                st.rerun()

else:
    st.warning("🔒 Conéctate primero desde el panel izquierdo.")

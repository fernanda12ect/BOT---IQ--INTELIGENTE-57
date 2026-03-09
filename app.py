import streamlit as st
import pandas as pd
import html
import time
from datetime import datetime, timedelta
import pytz
from bot import (
    obtener_activos_abiertos,
    calcular_indicadores,
    evaluar_activo
)
from iqoptionapi.stable_api import IQ_Option

st.set_page_config(layout="wide")
st.title("🤖 BOT OTC - NIVELES CON 2 TOQUES + EMA (1 MIN)")

# Inicializar session_state
if 'api' not in st.session_state:
    st.session_state.api = None
if 'activos_otc' not in st.session_state:
    st.session_state.activos_otc = []
if 'escaneando' not in st.session_state:
    st.session_state.escaneando = False
if 'fase' not in st.session_state:
    st.session_state.fase = "seleccion"
if 'activos_seguimiento' not in st.session_state:
    st.session_state.activos_seguimiento = []  # Máx 15 activos
if 'alertas_anticipadas' not in st.session_state:
    st.session_state.alertas_anticipadas = []  # Alertas cuando el precio se acerca
if 'señales_activas' not in st.session_state:
    st.session_state.señales_activas = []  # Lista de señales definitivas (cada activo una sola vez)
if 'historial' not in st.session_state:
    st.session_state.historial = []

# Zona horaria Ecuador
ecuador = pytz.timezone("America/Guayaquil")

# Definir función generar_señal (ahora incluye timestamp)
def generar_señal(activo, tipo_nivel, direccion, confirmacion=""):
    try:
        server_time = st.session_state.api.get_server_time()
        now_utc = datetime.fromtimestamp(server_time, tz=pytz.UTC)
    except:
        now_utc = datetime.now(pytz.UTC)
    entry_dt = now_utc + timedelta(minutes=1)  # 1 minuto para prepararse (entrada en la próxima vela)
    entry_dt = entry_dt.replace(second=0, microsecond=0)
    expiry_dt = entry_dt + timedelta(minutes=1)  # vencimiento 1 minuto después
    entry_local = entry_dt.astimezone(ecuador)
    expiry_local = expiry_dt.astimezone(ecuador)

    # Crear nueva señal
    nueva_señal = {
        'asset': activo['asset'],
        'direccion': direccion,
        'entry': entry_local.strftime("%H:%M:%S"),
        'expiry': expiry_local.strftime("%H:%M:%S"),
        'tipo_nivel': tipo_nivel,
        'confirmacion': confirmacion,
        'fuerza': activo.get('fuerza', 50),
        'timestamp': datetime.now(ecuador)  # para ordenar
    }

    # Eliminar señales previas del mismo activo (para evitar duplicados)
    st.session_state.señales_activas = [s for s in st.session_state.señales_activas if s['asset'] != activo['asset']]
    # Añadir la nueva
    st.session_state.señales_activas.append(nueva_señal)
    # Ordenar por timestamp descendente (más reciente primero)
    st.session_state.señales_activas.sort(key=lambda x: x['timestamp'], reverse=True)
    # Mantener solo las últimas 10 (para no saturar)
    st.session_state.señales_activas = st.session_state.señales_activas[:10]

    st.session_state.historial.append(f"🎯 SEÑAL DEFINITIVA: {activo['asset']} - {direccion} a las {entry_local.strftime('%H:%M:%S')} ({tipo_nivel})")

# Sidebar
with st.sidebar:
    st.header("⚙️ Configuración")
    email = st.text_input("📧 Email")
    password = st.text_input("🔑 Password", type="password")

    # Parámetros
    umbral_cerca = st.slider("🔍 Distancia para alerta anticipada (%)", 0.1, 2.0, 0.5, 0.1) / 100
    max_activos = st.slider("📊 Máx activos en seguimiento", 1, 15, 6, 1)  # Cambiado a 15
    pausa_entre_rondas = st.number_input("⏱️ Pausa entre rondas (seg)", 5, 60, 10)

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
                st.session_state.activos_otc = otc
                st.session_state.escaneando = True
                st.session_state.fase = "seleccion"
                st.session_state.activos_seguimiento = []
                st.session_state.alertas_anticipadas = []
                st.session_state.señales_activas = []
                st.session_state.historial = []
                st.success("✅ Conectado - Buscando activos OTC estables...")
                st.rerun()
            else:
                st.error(f"❌ Error de conexión: {reason}")
        except Exception as e:
            st.error(f"Error inesperado: {e}")

if desconectar:
    st.session_state.api = None
    st.session_state.escaneando = False
    st.session_state.activos_seguimiento = []
    st.session_state.alertas_anticipadas = []
    st.session_state.señales_activas = []
    st.success("Desconectado")
    st.rerun()

# Área principal
if st.session_state.api is not None:
    otc_count = len(st.session_state.activos_otc)
    st.success(f"📱 OTC disponibles: {otc_count}")

    # --- SECCIÓN 1: ACTIVOS EN SEGUIMIENTO (hasta 15) ---
    with st.expander(f"📌 ACTIVOS EN SEGUIMIENTO (MÁX {max_activos})", expanded=True):
        if st.session_state.activos_seguimiento:
            data = []
            for a in st.session_state.activos_seguimiento:
                data.append({
                    "Activo": a['asset'],
                    "Tipo Nivel": a['tipo'],
                    "Dirección": a['direccion'],
                    "Nivel": f"{a['nivel']:.5f}",
                    "Precio actual": f"{a.get('precio_actual', 0):.5f}",
                    "Fuerza": f"{a['fuerza']:.0f}%"
                })
            df = pd.DataFrame(data)
            st.dataframe(df, width='stretch')
        else:
            st.info("No hay activos en seguimiento.")

    # --- SECCIÓN 2: ALERTAS ANTICIPADAS (precio cerca del nivel) ---
    with st.expander("🔔 ALERTAS ANTICIPADAS", expanded=True):
        if st.session_state.alertas_anticipadas:
            for alerta in st.session_state.alertas_anticipadas[-10:]:
                st.warning(alerta)
        else:
            st.info("No hay alertas por ahora.")

    # --- SECCIÓN 3: SEÑALES DEFINITIVAS LISTAS PARA OPERAR ---
    with st.expander("🚀 SEÑALES DEFINITIVAS", expanded=True):
        if st.session_state.señales_activas:
            cols = st.columns(2)
            # Mostrar las señales en orden (ya están ordenadas por timestamp descendente)
            for idx, senal in enumerate(st.session_state.señales_activas):
                with cols[idx % 2]:
                    asset = senal['asset']
                    tipo = "📱 OTC"
                    asset_clean = asset.replace("-OTC", "")
                    color = "#006400" if senal['direccion'] == "CALL" else "#8B0000"
                    html_code = f"""
                    <div style="background:#111; padding:15px; border-radius:10px; border:3px solid {color}; margin-bottom:10px;">
                        <h4>{asset_clean} {tipo}</h4>
                        <p style="color:{color}; font-size:1.8rem;">{senal['direccion']}</p>
                        <p><strong>Tipo:</strong> {senal['tipo_nivel']}</p>
                        <p><strong>Entrada:</strong> {senal['entry']}</p>
                        <p><strong>Expira:</strong> {senal['expiry']}</p>
                        <p><strong>Conf:</strong> {senal.get('confirmacion', '')}</p>
                        <p style="color:#0f0;">✅ LISTO PARA OPERAR</p>
                    </div>
                    """
                    st.markdown(html_code, unsafe_allow_html=True)
        else:
            st.info("No hay señales definitivas aún.")

    # --- HISTORIAL ---
    with st.expander("📋 HISTORIAL DE EVENTOS", expanded=False):
        if st.session_state.historial:
            for linea in st.session_state.historial[-30:]:
                st.text(linea)
        else:
            st.info("Sin eventos.")

    # Lógica de escaneo continuo
    if st.session_state.escaneando:
        if st.session_state.fase == "seleccion":
            st.info("🔍 Analizando activos OTC...")
            todos = st.session_state.activos_otc
            if not todos:
                st.warning(f"No hay OTC. Reintentando en {pausa_entre_rondas} seg...")
                time.sleep(pausa_entre_rondas)
                _, otc = obtener_activos_abiertos(st.session_state.api)
                st.session_state.activos_otc = otc
                st.rerun()

            candidatos = []
            for asset in todos:
                try:
                    candles = st.session_state.api.get_candles(asset, 60, 100, time.time())
                    if not candles or len(candles) < 50:
                        continue
                    df = pd.DataFrame(candles)
                    for col in ['open', 'max', 'min', 'close', 'volume']:
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                    df.dropna(inplace=True)
                    if len(df) < 50:
                        continue
                    indicators = calcular_indicadores(df)
                    res = evaluar_activo(indicators, umbral_estabilidad=True)
                    if res:
                        candidatos.append({
                            'asset': asset,
                            'tipo': res['tipo'],
                            'direccion': res['direccion'],
                            'nivel': res['nivel'],
                            'fuerza': res['fuerza'],
                            'descripcion': res['descripcion'],
                            'precio_actual': indicators['close'],
                            'indicators': indicators
                        })
                except Exception as e:
                    st.session_state.historial.append(f"⚠️ Error con {asset}: {str(e)[:50]}")
                    continue
                time.sleep(0.2)

            if candidatos:
                candidatos.sort(key=lambda x: x['fuerza'], reverse=True)
                st.session_state.activos_seguimiento = candidatos[:max_activos]
                st.session_state.fase = "seguimiento"
                st.session_state.historial.append(f"✅ Seleccionados {len(st.session_state.activos_seguimiento)} activos:")
                for a in st.session_state.activos_seguimiento:
                    st.session_state.historial.append(f"   - {a['asset']} ({a['direccion']}, {a['tipo']}, fuerza {a['fuerza']}%)")
                time.sleep(2)
                st.rerun()
            else:
                st.session_state.historial.append("⚠️ No se encontraron activos estables con niveles. Reintentando...")
                time.sleep(pausa_entre_rondas)
                st.rerun()

        elif st.session_state.fase == "seguimiento":
            st.info("🔄 Monitoreando niveles...")
            nuevos_seguimiento = []
            activos_a_remover = []

            for activo in st.session_state.activos_seguimiento:
                asset = activo['asset']
                try:
                    # Obtener velas recientes
                    candles = st.session_state.api.get_candles(asset, 60, 5, time.time())
                    if not candles:
                        continue
                    df_recent = pd.DataFrame(candles)
                    last = df_recent.iloc[-1]
                    precio_actual = last['close']
                    activo['precio_actual'] = precio_actual

                    # Calcular distancia al nivel
                    nivel = activo['nivel']
                    distancia = abs(precio_actual - nivel) / nivel if nivel else 1

                    # Verificar alerta anticipada
                    if distancia < umbral_cerca:
                        alerta_msg = f"🔔 {asset} se acerca a {activo['tipo']} (distancia {distancia*100:.2f}%)"
                        if alerta_msg not in st.session_state.alertas_anticipadas:
                            st.session_state.alertas_anticipadas.append(alerta_msg)
                            st.session_state.historial.append(alerta_msg)

                    # Verificar señal definitiva: cuando el precio toca el nivel (con tolerancia) y hay cruce de EMAs
                    candles_full = st.session_state.api.get_candles(asset, 60, 100, time.time())
                    if not candles_full or len(candles_full) < 50:
                        continue
                    df_full = pd.DataFrame(candles_full)
                    for col in ['open', 'max', 'min', 'close', 'volume']:
                        df_full[col] = pd.to_numeric(df_full[col], errors='coerce')
                    df_full.dropna(inplace=True)
                    if len(df_full) < 50:
                        continue
                    indicators = calcular_indicadores(df_full)

                    # Condición de toque: precio actual dentro de 0.1% del nivel
                    toca = abs(precio_actual - nivel) / nivel < 0.001

                    if toca and indicators['cruce_ema'] and indicators['direccion_cruce'] == activo['direccion']:
                        # Señal definitiva
                        generar_señal(activo, activo['tipo'], activo['direccion'], confirmacion="EMA cruzada")
                        activos_a_remover.append(activo)
                        continue

                    # Si no hay señal, reevaluar si el activo sigue siendo válido
                    res = evaluar_activo(indicators, umbral_estabilidad=True)
                    if res:
                        # Actualizar datos (puede cambiar nivel)
                        activo['nivel'] = res['nivel']
                        activo['fuerza'] = res['fuerza']
                        activo['descripcion'] = res['descripcion']
                        nuevos_seguimiento.append(activo)
                    else:
                        activos_a_remover.append(activo)
                        st.session_state.historial.append(f"❌ {asset} dejó de cumplir criterios")
                except Exception as e:
                    st.session_state.historial.append(f"⚠️ Error monitoreando {asset}: {str(e)[:50]}")
                    activos_a_remover.append(activo)

            # Limpiar
            for a in activos_a_remover:
                if a in st.session_state.activos_seguimiento:
                    st.session_state.activos_seguimiento.remove(a)

            # Si hay espacios, volver a selección
            if len(st.session_state.activos_seguimiento) < max_activos:
                st.session_state.fase = "seleccion"
                st.rerun()
            else:
                time.sleep(pausa_entre_rondas)
                st.rerun()

else:
    st.warning("🔒 Conéctate primero desde el panel izquierdo.")

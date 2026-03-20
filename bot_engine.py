import time
import logging
import threading
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import pytz
from collections import defaultdict

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Zona horaria
ecuador = pytz.timezone("America/Guayaquil")

# =========================
# CLASE QUE CONTIENE EL ESTADO COMPARTIDO CON STREAMLIT
# =========================
class BotState:
    def __init__(self):
        self.running = False
        self.logs = []
        self.trades = []          # lista de trades realizados (con resultado)
        self.current_trade = None # operación en curso
        self.saldo = 0.0
        self.api = None
        self.tipo_cuenta = "PRACTICE"
        self.monto = 1.0
        self.last_signal_time = None

    def add_log(self, msg):
        self.logs.append(f"[{datetime.now(ecuador).strftime('%H:%M:%S')}] {msg}")
        if len(self.logs) > 200:
            self.logs = self.logs[-200:]

    def add_trade(self, trade):
        self.trades.append(trade)
        if len(self.trades) > 100:
            self.trades = self.trades[-100:]

# =========================
# FUNCIONES DE CONEXIÓN Y ACTIVOS
# =========================
def obtener_activos_otc(api):
    """Obtiene lista de activos OTC abiertos desde IQ Option."""
    try:
        open_time = api.get_all_open_time()
        activos = []
        if 'binary' in open_time:
            for asset, data in open_time['binary'].items():
                if data.get('open', False) and '-OTC' in asset:
                    activos.append(asset)
        return activos
    except Exception as e:
        logger.error(f"Error obteniendo activos: {e}")
        return []

def is_asset_open(api, asset):
    try:
        open_time = api.get_all_open_time()
        if 'binary' in open_time:
            for a, data in open_time['binary'].items():
                if a == asset:
                    return data.get('open', False)
        return False
    except:
        return True

def obtener_velas_1min(api, asset, n=50):
    try:
        candles = api.get_candles(asset, 60, n, time.time())
        if not candles or len(candles) < n:
            return None
        df = pd.DataFrame(candles)
        for col in ['open', 'max', 'min', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df.dropna(inplace=True)
        return df
    except Exception as e:
        logger.error(f"Error obteniendo velas de {asset}: {e}")
        return None

def calcular_indicadores(df):
    df = df.copy()
    df.rename(columns={'max': 'high', 'min': 'low'}, inplace=True)

    df['ema2'] = df['close'].ewm(span=2, adjust=False).mean()
    df['ema5'] = df['close'].ewm(span=5, adjust=False).mean()
    df['ema9'] = df['close'].ewm(span=9, adjust=False).mean()
    df['ema21'] = df['close'].ewm(span=21, adjust=False).mean()

    delta = df['close'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(9).mean()
    avg_loss = loss.rolling(9).mean()
    rs = avg_gain / avg_loss
    df['rsi9'] = 100 - (100 / (1 + rs))

    df['vol_avg'] = df['volume'].rolling(20).mean()
    df['vol_ratio'] = df['volume'] / df['vol_avg']
    return df

# =========================
# ESTRATEGIAS
# =========================
def estrategia_volatil(df, precio_actual):
    if len(df) < 6:
        return None
    ultimas5 = df.iloc[-5:]
    soporte = ultimas5['low'].min()
    resistencia = ultimas5['high'].max()
    dist_soporte = abs(precio_actual - soporte) / precio_actual
    dist_resistencia = abs(precio_actual - resistencia) / precio_actual
    umbral = 0.001
    ema2 = df['ema2'].iloc[-1]
    ema5 = df['ema5'].iloc[-1]
    rsi = df['rsi9'].iloc[-1]
    if dist_soporte < umbral and ema2 > ema5 and rsi < 40:
        ultima = df.iloc[-1]
        cuerpo = abs(ultima['close'] - ultima['open'])
        rango = ultima['high'] - ultima['low']
        if cuerpo > rango * 0.6:
            return ('CALL', f"Soporte micro + EMA2>5, RSI={rsi:.1f}")
    if dist_resistencia < umbral and ema2 < ema5 and rsi > 60:
        ultima = df.iloc[-1]
        cuerpo = abs(ultima['close'] - ultima['open'])
        rango = ultima['high'] - ultima['low']
        if cuerpo > rango * 0.6:
            return ('PUT', f"Resistencia micro + EMA2<5, RSI={rsi:.1f}")
    return None

def estrategia_tranquilo(df, precio_actual):
    if len(df) < 16:
        return None
    ultimas15 = df.iloc[-15:]
    soporte = ultimas15['low'].min()
    resistencia = ultimas15['high'].max()
    dist_soporte = abs(precio_actual - soporte) / precio_actual
    dist_resistencia = abs(precio_actual - resistencia) / precio_actual
    umbral = 0.001
    ultimas3 = df.iloc[-3:]
    tendencia_alcista = all(ultimas3['close'] > ultimas3['open'])
    tendencia_bajista = all(ultimas3['close'] < ultimas3['open'])
    ultima = df.iloc[-1]
    cuerpo = abs(ultima['close'] - ultima['open'])
    rango = ultima['high'] - ultima['low']
    fuerza = cuerpo > rango * 0.6
    if dist_soporte < umbral and tendencia_alcista and ultima['close'] > ultima['open'] and fuerza:
        return ('CALL', f"Soporte 15v + tendencia alcista + vela fuerte")
    if dist_resistencia < umbral and tendencia_bajista and ultima['close'] < ultima['open'] and fuerza:
        return ('PUT', f"Resistencia 15v + tendencia bajista + vela fuerte")
    return None

def analizar_activo(api, asset, state):
    """Evalúa un activo y devuelve (dirección, descripción) si hay señal."""
    try:
        df = obtener_velas_1min(api, asset, n=50)
        if df is None or len(df) < 50:
            return None
        df = calcular_indicadores(df)
        precio = df['close'].iloc[-1]
        res = estrategia_volatil(df, precio)
        if res:
            state.add_log(f"✅ {asset}: Señal {res[0]} (estrat. volátil) - {res[1]}")
            return res
        res = estrategia_tranquilo(df, precio)
        if res:
            state.add_log(f"✅ {asset}: Señal {res[0]} (estrat. tranquila) - {res[1]}")
            return res
        return None
    except Exception as e:
        state.add_log(f"⚠️ Error analizando {asset}: {e}")
        return None

def seleccionar_mejor_senal(api, state):
    activos = obtener_activos_otc(api)
    if not activos:
        state.add_log("⚠️ No se encontraron activos OTC abiertos.")
        return None
    state.add_log(f"🔍 Analizando {len(activos)} activos OTC...")
    for asset in activos:
        res = analizar_activo(api, asset, state)
        if res:
            return {'asset': asset, 'direccion': res[0], 'desc': res[1]}
        time.sleep(0.05)  # pausa para no saturar
    return None

# =========================
# EJECUCIÓN DE TRADE
# =========================
def ejecutar_trade(api, asset, direccion, monto, state):
    if not is_asset_open(api, asset):
        state.add_log(f"⚠️ {asset} no está disponible para trading.")
        return False
    opcion = "call" if direccion == "CALL" else "put"
    expiracion = int(time.time()) + 50  # 50 segundos para evitar límite
    try:
        success, order_id = api.buy(monto, asset, opcion, expiracion)
        if success:
            entrada = datetime.now(ecuador)
            entrada_str = entrada.strftime("%H:%M:%S")
            vencimiento_str = (entrada + timedelta(minutes=1)).strftime("%H:%M:%S")
            trade = {
                'asset': asset,
                'direccion': direccion,
                'monto': monto,
                'entrada': entrada_str,
                'vencimiento': vencimiento_str,
                'order_id': order_id,
                'estado': 'PENDIENTE'
            }
            state.current_trade = trade
            state.saldo -= monto
            state.add_log(f"💰 Trade ejecutado: {asset} {direccion} ${monto} (ID: {order_id})")
            return True
        else:
            if "Time for purchasing options is over" in str(order_id):
                state.add_log(f"⏰ {asset} no disponible en este momento (tiempo expirado).")
            else:
                state.add_log(f"❌ Error al ejecutar trade en {asset}: {order_id}")
            return False
    except Exception as e:
        state.add_log(f"⚠️ Excepción al ejecutar trade: {e}")
        return False

def verificar_resultado_trade(api, state):
    if not state.current_trade:
        return
    trade = state.current_trade
    # Verificar si ha vencido
    vencimiento_dt = datetime.strptime(trade['vencimiento'], "%H:%M:%S").time()
    ahora = datetime.now(ecuador).time()
    ahora_dt = datetime.combine(datetime.today(), ahora)
    vencimiento_dt_full = datetime.combine(datetime.today(), vencimiento_dt)
    if vencimiento_dt_full < ahora_dt:
        vencimiento_dt_full += timedelta(days=1)
    if ahora_dt >= vencimiento_dt_full:
        try:
            resultado = api.check_win_v4(trade['order_id'])
            if resultado is not None:
                if isinstance(resultado, tuple):
                    estado, ganancia = resultado
                else:
                    estado = resultado
                    ganancia = 0
                if estado == 'win':
                    state.saldo += trade['monto'] + ganancia
                    trade['estado'] = 'GANADA'
                    state.add_log(f"✅ Trade {trade['order_id']} GANADA: +{ganancia:.2f}")
                elif estado == 'loose':
                    trade['estado'] = 'PERDIDA'
                    state.add_log(f"❌ Trade {trade['order_id']} PERDIDA")
                else:
                    trade['estado'] = 'DEVUELTA'
                    state.saldo += trade['monto']
                    state.add_log(f"🔄 Trade {trade['order_id']} DEVUELTA")
            else:
                trade['estado'] = 'SIN RESULTADO'
                state.add_log(f"⚠️ No se pudo obtener resultado para {trade['order_id']}")
        except Exception as e:
            state.add_log(f"⚠️ Error al verificar resultado: {e}")
            trade['estado'] = 'ERROR'
        state.add_trade(trade)
        state.current_trade = None
        return True
    return False

# =========================
# MOTOR PRINCIPAL (corre en hilo)
# =========================
def bot_engine(state):
    while state.running:
        try:
            if not state.api:
                time.sleep(1)
                continue
            # Verificar conexión
            if not state.api.check_connect():
                state.add_log("❌ Conexión perdida. Intentando reconectar...")
                # Podríamos reintentar pero por ahora paramos
                state.running = False
                break
            # Si hay operación en curso, esperar a que termine
            if state.current_trade:
                verificar_resultado_trade(state.api, state)
                time.sleep(1)
                continue
            # Sincronización con el segundo 58-59
            now = datetime.now(ecuador)
            segundo = now.second
            if segundo == 58:
                # Pequeña pausa para evitar ejecutar muy temprano
                time.sleep(0.3)
                mejor = seleccionar_mejor_senal(state.api, state)
                if mejor:
                    state.add_log(f"🎯 Señal encontrada: {mejor['asset']} - {mejor['direccion']}")
                    ejecutar_trade(state.api, mejor['asset'], mejor['direccion'], state.monto, state)
                else:
                    state.add_log("🔍 SIN SEÑAL – ESPERAR PROXIMO MINUTO")
                # Pequeña espera para no repetir en el mismo minuto
                time.sleep(0.5)
            else:
                # Mostrar cuenta regresiva en logs solo ocasionalmente para no saturar
                if segundo == 0:
                    state.add_log("⏳ Esperando próximo minuto...")
                time.sleep(1)
        except Exception as e:
            state.add_log(f"⚠️ Error en el motor: {e}")
            time.sleep(5)

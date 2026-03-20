import pandas as pd
import numpy as np
import time
import logging
from datetime import datetime
import pytz
from collections import defaultdict

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Zona horaria de Ecuador
ecuador = pytz.timezone("America/Guayaquil")

# Lista de activos de fallback ampliada (para cuando la API no devuelva datos)
FALLBACK_ACTIVOS = [
    "EURUSD-OTC", "GBPUSD-OTC", "AUDUSD-OTC", "USDJPY-OTC",
    "USDCHF-OTC", "NZDUSD-OTC", "USDCAD-OTC", "GBPJPY-OTC",
    "EURJPY-OTC", "AUDCAD-OTC", "AUDJPY-OTC", "EURGBP-OTC",
    "EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCHF", "NZDUSD",
    "USDCAD", "GBPJPY", "EURJPY", "AUDCAD", "AUDJPY", "EURGBP",
    "EURCHF", "GBPCHF", "CADCHF", "AUDNZD"
]

# =========================
# INDICADORES COMUNES
# =========================
def calcular_indicadores(df):
    df = df.copy()
    df.rename(columns={'max': 'high', 'min': 'low'}, inplace=True)

    # EMAs
    df['ema9'] = df['close'].ewm(span=9, adjust=False).mean()
    df['ema21'] = df['close'].ewm(span=21, adjust=False).mean()
    df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()

    # RSI
    delta = df['close'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss
    df['rsi'] = 100 - (100 / (1 + rs))

    # ATR
    high, low, close = df['high'], df['low'], df['close']
    tr = pd.concat([high - low, abs(high - close.shift()), abs(low - close.shift())], axis=1).max(axis=1)
    df['atr'] = tr.rolling(14).mean()

    # ADX
    df['tr'] = tr
    df['plus_dm'] = np.where((high - high.shift()) > (low.shift() - low), np.maximum(high - high.shift(), 0), 0)
    df['minus_dm'] = np.where((low.shift() - low) > (high - high.shift()), np.maximum(low.shift() - low, 0), 0)
    df['atr_period'] = df['tr'].rolling(14).mean()
    df['plus_di'] = 100 * (df['plus_dm'].rolling(14).mean() / df['atr_period'])
    df['minus_di'] = 100 * (df['minus_dm'].rolling(14).mean() / df['atr_period'])
    df['dx'] = 100 * (abs(df['plus_di'] - df['minus_di']) / (df['plus_di'] + df['minus_di']))
    df['adx'] = df['dx'].rolling(14).mean()

    # Volumen promedio
    df['vol_avg'] = df['volume'].rolling(20).mean()
    df['vol_ratio'] = df['volume'] / df['vol_avg']

    return df

# =========================
# DETECCIÓN DE TENDENCIA (umbral ADX más bajo)
# =========================
def detectar_tendencia(df):
    """Retorna (dirección, fuerza) si hay tendencia: ADX > 15 y EMAs alineadas."""
    last = df.iloc[-1]
    if last['adx'] < 15:
        return None, 0
    if last['ema9'] > last['ema21'] and last['ema9'] > last['ema50']:
        fuerza = last['adx'] + last['vol_ratio'] * 10
        return 'CALL', min(fuerza, 100)
    elif last['ema9'] < last['ema21'] and last['ema9'] < last['ema50']:
        fuerza = last['adx'] + last['vol_ratio'] * 10
        return 'PUT', min(fuerza, 100)
    return None, 0

# =========================
# CÁLCULO DE NIVELES FIBONACCI
# =========================
def calcular_fibonacci(df, ventana=20):
    if len(df) < ventana:
        return None
    ultimas = df.iloc[-ventana:]
    maximo = ultimas['high'].max()
    minimo = ultimas['low'].min()
    dif = maximo - minimo
    return {
        '382': maximo - 0.382 * dif,
        '500': maximo - 0.5 * dif,
        '618': maximo - 0.618 * dif,
        'max': maximo,
        'min': minimo
    }

# =========================
# DETECCIÓN DE RETROCESO A NIVEL FIBONACCI
# =========================
def retroceso_a_fibonacci(df, direccion, fib, tolerancia=0.5):
    if fib is None:
        return None
    last = df.iloc[-1]
    atr = last['atr']
    niveles = []
    for key in ['382', '500', '618']:
        nivel = fib[key]
        if abs(last['close'] - nivel) / last['close'] < 0.001 or abs(last['close'] - nivel) < atr * tolerancia:
            niveles.append((nivel, key))
    if not niveles:
        return None
    nivel, clave = min(niveles, key=lambda x: abs(x[0] - last['close']))
    return {'nivel': nivel, 'clave': clave, 'distancia': abs(last['close'] - nivel)}

# =========================
# CONFIRMACIÓN CON VELA DE 1 MINUTO
# =========================
def confirmar_vela_1min(api, asset, direccion_esperada):
    try:
        candles = api.get_candles(asset, 60, 1, time.time())
        if not candles:
            return False
        df = pd.DataFrame(candles)
        last = df.iloc[-1]
        # Volumen promedio de 20 velas anteriores
        candles_avg = api.get_candles(asset, 60, 20, time.time())
        if candles_avg and len(candles_avg) >= 20:
            vol_avg = pd.DataFrame(candles_avg)['volume'].mean()
            vol_ratio = last['volume'] / vol_avg if vol_avg > 0 else 1
        else:
            vol_ratio = 1
        if direccion_esperada == 'CALL':
            return last['close'] > last['open'] and vol_ratio > 1.2
        else:
            return last['close'] < last['open'] and vol_ratio > 1.2
    except Exception as e:
        logger.error(f"Error en confirmación 1min de {asset}: {e}")
        return False

# =========================
# EVALUAR UN ACTIVO
# =========================
def evaluar_activo(api, asset):
    try:
        candles = api.get_candles(asset, 300, 100, time.time())
        if not candles or len(candles) < 50:
            return None
        df = pd.DataFrame(candles)
        for col in ['open', 'max', 'min', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df.dropna(inplace=True)
        if len(df) < 50:
            return None

        df = calcular_indicadores(df)
        direccion, fuerza = detectar_tendencia(df)
        if direccion is None:
            return None

        fib = calcular_fibonacci(df)
        return {
            'asset': asset,
            'direccion': direccion,
            'fuerza': fuerza,
            'fib': fib,
            'precio': df['close'].iloc[-1],
            'timestamp': datetime.now(ecuador)
        }
    except Exception as e:
        logger.error(f"Error evaluando {asset}: {e}")
        return None

# =========================
# OBTENER ACTIVOS ABIERTOS (con fallback ampliado)
# =========================
def obtener_activos_abiertos(api, tipo_mercado="AMBOS"):
    try:
        open_time = api.get_all_open_time()
        activos = []
        if 'binary' in open_time:
            for asset, data in open_time['binary'].items():
                if data.get('open', False):
                    if tipo_mercado == 'OTC' and '-OTC' in asset:
                        activos.append(asset)
                    elif tipo_mercado == 'REAL' and '-OTC' not in asset:
                        activos.append(asset)
                    elif tipo_mercado == 'AMBOS':
                        activos.append(asset)
        logger.info(f"Activos obtenidos: {len(activos)}")
        if not activos:
            logger.warning("Usando lista de fallback")
            if tipo_mercado == 'OTC':
                return [a for a in FALLBACK_ACTIVOS if '-OTC' in a]
            elif tipo_mercado == 'REAL':
                return [a for a in FALLBACK_ACTIVOS if '-OTC' not in a]
            else:
                return FALLBACK_ACTIVOS
        return activos
    except Exception as e:
        logger.error(f"Error obteniendo activos: {e}")
        return FALLBACK_ACTIVOS

# =========================
# SELECCIONAR EL MEJOR ACTIVO (hasta 60 por ronda)
# =========================
def seleccionar_mejor_activo(api, lista_activos):
    mejor = None
    mejor_fuerza = -1
    for asset in lista_activos:
        res = evaluar_activo(api, asset)
        if res and res['fuerza'] > mejor_fuerza:
            mejor_fuerza = res['fuerza']
            mejor = res
        time.sleep(0.1)
    return mejor

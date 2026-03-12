import pandas as pd
import numpy as np
import time
import logging
from datetime import datetime
import pytz

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Zona horaria de Ecuador
ecuador = pytz.timezone("America/Guayaquil")

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
# DETECCIÓN DE TENDENCIA (usando EMAs y ADX)
# =========================
def detectar_tendencia(df):
    if len(df) < 50:
        return None, 0
    last = df.iloc[-1]
    # Tendencia alcista: EMA9 > EMA21 y ADX > 25
    if last['ema9'] > last['ema21'] and last['adx'] > 25:
        return 'CALL', last['adx'] + (last['vol_ratio'] * 5)
    # Tendencia bajista: EMA9 < EMA21 y ADX > 25
    elif last['ema9'] < last['ema21'] and last['adx'] > 25:
        return 'PUT', last['adx'] + (last['vol_ratio'] * 5)
    else:
        return None, 0

# =========================
# DETECCIÓN DE RETROCESO (precio moviéndose en contra de la tendencia)
# =========================
def detectar_retroceso(df, tendencia):
    """
    Detecta si el precio se está moviendo en contra de la tendencia principal.
    Retorna True si está en retroceso.
    """
    if len(df) < 5:
        return False
    ultimas = df.iloc[-5:]
    if tendencia == 'CALL':
        # En tendencia alcista, retroceso es cuando el precio baja
        return all(ultimas['close'].iloc[i] >= ultimas['close'].iloc[i+1] for i in range(4))
    else:
        # En tendencia bajista, retroceso es cuando el precio sube
        return all(ultimas['close'].iloc[i] <= ultimas['close'].iloc[i+1] for i in range(4))

# =========================
# CONFIRMACIÓN DE CRUCE DE EMAs
# =========================
def confirmar_cruce_ema(df, tendencia):
    """
    Verifica si en la última vela se ha producido un cruce de EMA9 y EMA21 en la dirección de la tendencia.
    """
    if len(df) < 2:
        return False
    prev = df.iloc[-2]
    last = df.iloc[-1]
    if tendencia == 'CALL':
        return prev['ema9'] <= prev['ema21'] and last['ema9'] > last['ema21']
    else:
        return prev['ema9'] >= prev['ema21'] and last['ema9'] < last['ema21']

# =========================
# EVALUAR ACTIVO PARA SELECCIÓN (solo tendencia)
# =========================
def evaluar_activo_seleccion(api, asset):
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
        tendencia, fuerza = detectar_tendencia(df)

        if tendencia is None:
            return None

        return {
            'asset': asset,
            'tendencia': tendencia,
            'fuerza': fuerza,
            'precio': df['close'].iloc[-1],
            'df': df  # guardamos para usar en seguimiento
        }
    except Exception as e:
        logger.error(f"Error evaluando {asset}: {e}")
        return None

# =========================
# EVALUAR ACTIVO EN SEGUIMIENTO (retroceso y cruce)
# =========================
def evaluar_activo_seguimiento(api, asset, tendencia_principal):
    """
    Evalúa si el activo está en retroceso y si se ha producido un cruce de EMAs.
    Retorna (en_retroceso, cruce_confirmado, precio_actual)
    """
    try:
        candles = api.get_candles(asset, 300, 50, time.time())  # menos velas para rapidez
        if not candles or len(candles) < 20:
            return False, False, 0
        df = pd.DataFrame(candles)
        for col in ['open', 'max', 'min', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df.dropna(inplace=True)
        if len(df) < 20:
            return False, False, 0

        df = calcular_indicadores(df)
        en_retroceso = detectar_retroceso(df, tendencia_principal)
        cruce = confirmar_cruce_ema(df, tendencia_principal)
        precio = df['close'].iloc[-1]
        return en_retroceso, cruce, precio
    except Exception as e:
        logger.error(f"Error en seguimiento de {asset}: {e}")
        return False, False, 0

# =========================
# OBTENER ACTIVOS ABIERTOS
# =========================
def obtener_activos_abiertos(api, tipo_mercado):
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
        return activos
    except Exception as e:
        logger.error(f"Error obteniendo activos: {e}")
        return []

# =========================
# SELECCIONAR EL MEJOR ACTIVO (por fuerza de tendencia)
# =========================
def seleccionar_mejor_activo(api, lista_activos, min_fuerza=30):
    mejores = []
    for asset in lista_activos:
        try:
            res = evaluar_activo_seleccion(api, asset)
            if res and res['fuerza'] >= min_fuerza:
                mejores.append(res)
            time.sleep(0.1)
        except:
            continue
    if not mejores:
        return None
    mejores.sort(key=lambda x: x['fuerza'], reverse=True)
    return mejores[0]

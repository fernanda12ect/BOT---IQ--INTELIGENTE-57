import pandas as pd
import numpy as np
import time
import logging
from datetime import datetime
import pytz

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

ecuador = pytz.timezone("America/Guayaquil")

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

    # Volumen
    df['vol_avg'] = df['volume'].rolling(20).mean()
    df['vol_ratio'] = df['volume'] / df['vol_avg']

    return df

def detectar_cambio_tendencia(df):
    """Detecta posible cambio de tendencia usando divergencias y patrones."""
    if len(df) < 10:
        return None
    ultimas = df.iloc[-5:]
    # Condiciones para posible cambio alcista
    if (ultimas['low'].iloc[-1] > ultimas['low'].iloc[-3] and
        ultimas['rsi'].iloc[-1] < 40 and
        ultimas['vol_ratio'].iloc[-1] > 1.5):
        return "CALL"
    # Condiciones para posible cambio bajista
    if (ultimas['high'].iloc[-1] < ultimas['high'].iloc[-3] and
        ultimas['rsi'].iloc[-1] > 60 and
        ultimas['vol_ratio'].iloc[-1] > 1.5):
        return "PUT"
    return None

def estrategia_tendencia(df):
    """Estrategia principal: tendencia fuerte con EMA y volumen."""
    if len(df) < 50:
        return None
    ultima = df.iloc[-1]
    previa = df.iloc[-2]
    # Tendencia alcista
    if (ultima['ema9'] > ultima['ema21'] and
        ultima['close'] > ultima['ema9'] and
        ultima['adx'] > 25 and
        ultima['vol_ratio'] > 1.3):
        # Confirmación de continuación (sin fuerza contraria)
        if previa['close'] < previa['open'] and ultima['close'] > ultima['open']:  # vela bajista seguida de alcista
            return "CALL"
    # Tendencia bajista
    if (ultima['ema9'] < ultima['ema21'] and
        ultima['close'] < ultima['ema9'] and
        ultima['adx'] > 25 and
        ultima['vol_ratio'] > 1.3):
        if previa['close'] > previa['open'] and ultima['close'] < ultima['open']:
            return "PUT"
    return None

def estrategia_agotamiento(df):
    """Estrategia de agotamiento de fuerza contraria."""
    if len(df) < 10:
        return None
    ultima = df.iloc[-1]
    previa = df.iloc[-2]
    # Detectar agotamiento de vendedores (para compra)
    if (previa['close'] < previa['open'] and  # vela bajista
        abs(previa['close'] - previa['open']) < (previa['high'] - previa['low']) * 0.3 and  # cuerpo pequeño
        ultima['close'] > ultima['open'] and  # vela alcista
        ultima['vol_ratio'] > 1.5):
        return "CALL"
    # Detectar agotamiento de compradores (para venta)
    if (previa['close'] > previa['open'] and
        abs(previa['close'] - previa['open']) < (previa['high'] - previa['low']) * 0.3 and
        ultima['close'] < ultima['open'] and
        ultima['vol_ratio'] > 1.5):
        return "PUT"
    return None

def evaluar_activo(api, asset):
    """Evalúa un activo y retorna dirección si hay señal, o None."""
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

        # Evaluar estrategias en orden de prioridad
        resultado = estrategia_tendencia(df)
        if resultado:
            return resultado, "Tendencia con EMA"
        resultado = estrategia_agotamiento(df)
        if resultado:
            return resultado, "Agotamiento de fuerza"
        cambio = detectar_cambio_tendencia(df)
        if cambio:
            return cambio, "Cambio de tendencia"
        return None
    except Exception as e:
        logger.error(f"Error evaluando {asset}: {e}")
        return None

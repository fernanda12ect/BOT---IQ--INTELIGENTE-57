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
# DETECCIÓN DE SEÑAL PARA LA PRÓXIMA VELA DE 1 MINUTO
# =========================
def evaluar_activo_1min(api, asset, umbral_adx=20):
    """
    Evalúa un activo en timeframe de 1 minuto y determina si la próxima vela será alcista o bajista.
    Retorna un dict con:
        - direccion: 'CALL' o 'PUT'
        - fuerza: valor entre 0 y 100 (basado en volumen y cruce)
        - confirmacion: si hay cruce de EMA y volumen alto
        - alerta: si está cerca de una señal (para avisar con antelación)
    Si no hay señal, retorna None.
    """
    try:
        # Obtener últimas 50 velas de 1 minuto
        candles = api.get_candles(asset, 60, 50, time.time())
        if not candles or len(candles) < 30:
            return None
        df = pd.DataFrame(candles)
        for col in ['open', 'max', 'min', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df.dropna(inplace=True)
        if len(df) < 30:
            return None

        df = calcular_indicadores(df)
        last = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else last

        # Detectar cruce de EMA
        cruce_call = prev['ema9'] <= prev['ema21'] and last['ema9'] > last['ema21']
        cruce_put = prev['ema9'] >= prev['ema21'] and last['ema9'] < last['ema21']

        # Volumen alto
        volumen_alto = last['vol_ratio'] > 1.5

        # Fuerza de la vela: cuerpo grande
        cuerpo = abs(last['close'] - last['open'])
        rango = last['high'] - last['low']
        vela_fuerte = cuerpo > rango * 0.6

        # Dirección de la vela actual
        vela_alcista = last['close'] > last['open']
        vela_bajista = last['close'] < last['open']

        # ADX
        tendencia_fuerte = last['adx'] > umbral_adx

        # Puntuación
        fuerza = 0
        direccion = None

        # Señal CALL
        if vela_alcista and cruce_call and volumen_alto and vela_fuerte and tendencia_fuerte:
            fuerza = 80 + (last['vol_ratio'] * 5)
            direccion = 'CALL'
        # Señal PUT
        elif vela_bajista and cruce_put and volumen_alto and vela_fuerte and tendencia_fuerte:
            fuerza = 80 + (last['vol_ratio'] * 5)
            direccion = 'PUT'
        # Señal débil (solo cruce o solo volumen)
        elif cruce_call and volumen_alto and tendencia_fuerte:
            fuerza = 60
            direccion = 'CALL'
        elif cruce_put and volumen_alto and tendencia_fuerte:
            fuerza = 60
            direccion = 'PUT'
        else:
            return None

        # Determinar si es una alerta (la señal es inminente)
        # Por ejemplo, si el precio está cerca de la EMA o si el volumen está aumentando
        alerta = False
        if not (cruce_call or cruce_put) and last['vol_ratio'] > 1.2 and last['adx'] > umbral_adx:
            # Podría estar por venir un cruce
            alerta = True

        return {
            'asset': asset,
            'direccion': direccion,
            'fuerza': min(fuerza, 100),
            'confirmacion': (cruce_call or cruce_put) and volumen_alto and vela_fuerte,
            'alerta': alerta,
            'precio': last['close'],
            'timestamp': datetime.now(ecuador)
        }
    except Exception as e:
        logger.error(f"Error evaluando {asset} en 1min: {e}")
        return None

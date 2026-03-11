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
    """
    Calcula EMA, RSI, MACD, Bollinger Bands, ADX, ATR sobre un DataFrame de velas.
    Devuelve el DataFrame con las columnas añadidas.
    """
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

    # MACD
    df['ema12'] = df['close'].ewm(span=12, adjust=False).mean()
    df['ema26'] = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = df['ema12'] - df['ema26']
    df['signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    df['hist'] = df['macd'] - df['signal']

    # Bollinger Bands (20,2)
    df['bb_ma'] = df['close'].rolling(20).mean()
    df['bb_std'] = df['close'].rolling(20).std()
    df['bb_upper'] = df['bb_ma'] + 2 * df['bb_std']
    df['bb_lower'] = df['bb_ma'] - 2 * df['bb_std']

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
# 10 ESTRATEGIAS DE 5 MINUTOS
# =========================
def estrategia_1_ema_crossover(df):
    """EMA9 cruce EMA21 + volumen + tendencia M15"""
    if len(df) < 50:
        return None
    ultima = df.iloc[-1]
    previa = df.iloc[-2]
    if previa['ema9'] <= previa['ema21'] and ultima['ema9'] > ultima['ema21'] and ultima['vol_ratio'] > 1.5:
        if ultima['close'] > ultima['ema9'] and ultima['adx'] > 20:
            return 'CALL', 'EMA Crossover Alcista'
    if previa['ema9'] >= previa['ema21'] and ultima['ema9'] < ultima['ema21'] and ultima['vol_ratio'] > 1.5:
        if ultima['close'] < ultima['ema9'] and ultima['adx'] > 20:
            return 'PUT', 'EMA Crossover Bajista'
    return None

def estrategia_2_rsi_reversion(df):
    """RSI extremo + Bollinger + patrón de vela"""
    if len(df) < 50:
        return None
    ultima = df.iloc[-1]
    if ultima['rsi'] < 30 and ultima['close'] <= ultima['bb_lower'] and ultima['vol_ratio'] > 2.0:
        if ultima['close'] > ultima['open'] and (ultima['low'] < ultima['open'] * 0.998):
            return 'CALL', 'RSI Reversión Alcista'
    if ultima['rsi'] > 70 and ultima['close'] >= ultima['bb_upper'] and ultima['vol_ratio'] > 2.0:
        if ultima['close'] < ultima['open'] and (ultima['high'] > ultima['open'] * 1.002):
            return 'PUT', 'RSI Reversión Bajista'
    return None

def estrategia_3_macd_divergence(df):
    """Divergencia MACD (últimas 2 velas)"""
    if len(df) < 5:
        return None
    ultimas2 = df.iloc[-2:]
    if len(ultimas2) < 2:
        return None
    if (ultimas2['low'].iloc[0] > ultimas2['low'].iloc[1] and
        ultimas2['macd'].iloc[0] < ultimas2['macd'].iloc[1] and
        ultimas2['hist'].iloc[1] > 0):
        return 'CALL', 'MACD Divergencia Alcista'
    if (ultimas2['high'].iloc[0] < ultimas2['high'].iloc[1] and
        ultimas2['macd'].iloc[0] > ultimas2['macd'].iloc[1] and
        ultimas2['hist'].iloc[1] < 0):
        return 'PUT', 'MACD Divergencia Bajista'
    return None

def estrategia_4_bb_squeeze(df):
    """Bollinger squeeze + breakout con volumen"""
    if len(df) < 50:
        return None
    ultimas5 = df.iloc[-5:]
    squeeze = all((ultimas5['bb_upper'] - ultimas5['bb_lower']) / ultimas5['close'] < 0.005)
    if not squeeze:
        return None
    ultima = df.iloc[-1]
    if ultima['close'] > ultima['bb_upper'] and ultima['vol_ratio'] > 2.0:
        return 'CALL', 'BB Squeeze Alcista'
    if ultima['close'] < ultima['bb_lower'] and ultima['vol_ratio'] > 2.0:
        return 'PUT', 'BB Squeeze Bajista'
    return None

def estrategia_5_adx_trend(df):
    """ADX fuerte + dirección DI + EMAs alineadas"""
    if len(df) < 50:
        return None
    ultima = df.iloc[-1]
    if ultima['adx'] > 30 and ultima['plus_di'] > ultima['minus_di'] and ultima['ema9'] > ultima['ema21']:
        return 'CALL', 'ADX Tendencia Alcista'
    if ultima['adx'] > 30 and ultima['minus_di'] > ultima['plus_di'] and ultima['ema9'] < ultima['ema21']:
        return 'PUT', 'ADX Tendencia Bajista'
    return None

def estrategia_6_sr_ema(df):
    """Soporte/Resistencia + EMA (simulado con máximos/mínimos recientes)"""
    if len(df) < 50:
        return None
    ultimas20 = df.iloc[-20:]
    soporte = ultimas20['low'].min()
    resistencia = ultimas20['high'].max()
    precio = df.iloc[-1]['close']
    distancia_soporte = abs(precio - soporte) / precio
    distancia_resistencia = abs(precio - resistencia) / precio
    if distancia_soporte < 0.001 and precio > df.iloc[-1]['ema9'] and df.iloc[-1]['vol_ratio'] > 1.5:
        return 'CALL', 'Soporte + EMA'
    if distancia_resistencia < 0.001 and precio < df.iloc[-1]['ema9'] and df.iloc[-1]['vol_ratio'] > 1.5:
        return 'PUT', 'Resistencia + EMA'
    return None

def estrategia_7_macd_zero_cross(df):
    """MACD cruza la línea cero con volumen"""
    if len(df) < 5:
        return None
    prev = df.iloc[-2]
    ultima = df.iloc[-1]
    if prev['macd'] <= 0 and ultima['macd'] > 0 and ultima['vol_ratio'] > 1.5:
        return 'CALL', 'MACD Zero Cross Alcista'
    if prev['macd'] >= 0 and ultima['macd'] < 0 and ultima['vol_ratio'] > 1.5:
        return 'PUT', 'MACD Zero Cross Bajista'
    return None

def estrategia_8_volume_spike(df):
    """Pico de volumen + vela grande en dirección"""
    if len(df) < 50:
        return None
    ultima = df.iloc[-1]
    if ultima['vol_ratio'] > 3.0:
        cuerpo = abs(ultima['close'] - ultima['open'])
        rango = ultima['high'] - ultima['low']
        if cuerpo > rango * 0.7:
            if ultima['close'] > ultima['open']:
                return 'CALL', 'Volumen Spike Alcista'
            else:
                return 'PUT', 'Volumen Spike Bajista'
    return None

def estrategia_9_ema_aligned(df):
    """EMA9 y EMA21 alineadas con pendiente y volumen"""
    if len(df) < 50:
        return None
    ultima = df.iloc[-1]
    pendiente = (ultima['ema9'] - df.iloc[-5]['ema9']) / 5
    if ultima['ema9'] > ultima['ema21'] and pendiente > 0 and ultima['vol_ratio'] > 1.3:
        return 'CALL', 'EMAs Alineadas Alcista'
    if ultima['ema9'] < ultima['ema21'] and pendiente < 0 and ultima['vol_ratio'] > 1.3:
        return 'PUT', 'EMAs Alineadas Bajista'
    return None

def estrategia_10_atr_breakout(df):
    """Breakout con expansión de ATR"""
    if len(df) < 50:
        return None
    ultima = df.iloc[-1]
    atr_medio = df['atr'].iloc[-20:].mean()
    if ultima['atr'] > atr_medio * 1.5 and ultima['vol_ratio'] > 2.0:
        if ultima['close'] > df.iloc[-2]['high']:
            return 'CALL', 'ATR Breakout Alcista'
        if ultima['close'] < df.iloc[-2]['low']:
            return 'PUT', 'ATR Breakout Bajista'
    return None

# Lista de todas las estrategias (nombre, función)
ESTRATEGIAS = [
    ("EMA Crossover", estrategia_1_ema_crossover),
    ("RSI Reversión", estrategia_2_rsi_reversion),
    ("MACD Divergencia", estrategia_3_macd_divergence),
    ("BB Squeeze", estrategia_4_bb_squeeze),
    ("ADX Trend", estrategia_5_adx_trend),
    ("Soporte/Resistencia + EMA", estrategia_6_sr_ema),
    ("MACD Zero Cross", estrategia_7_macd_zero_cross),
    ("Volumen Spike", estrategia_8_volume_spike),
    ("EMAs Alineadas", estrategia_9_ema_aligned),
    ("ATR Breakout", estrategia_10_atr_breakout)
]

# =========================
# EVALUAR UN ACTIVO
# =========================
def evaluar_activo(api, asset, estrategias_activas):
    """
    Obtiene velas M5 del activo, aplica las estrategias activas y retorna la primera señal encontrada.
    Devuelve (direccion, nombre_estrategia) o None.
    """
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

        for nombre, funcion in ESTRATEGIAS:
            if nombre in estrategias_activas:
                try:
                    resultado = funcion(df)
                    if resultado:
                        direccion, nombre_estr = resultado
                        return direccion, nombre_estr
                except Exception as e:
                    logger.error(f"Error en estrategia {nombre} para {asset}: {e}")
                    continue
        return None
    except Exception as e:
        logger.error(f"Error evaluando {asset}: {e}")
        return None

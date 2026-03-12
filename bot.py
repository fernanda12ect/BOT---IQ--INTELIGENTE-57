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

    # MACD
    df['ema12'] = df['close'].ewm(span=12, adjust=False).mean()
    df['ema26'] = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = df['ema12'] - df['ema26']
    df['signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    df['hist'] = df['macd'] - df['signal']

    # Bollinger Bands
    df['bb_ma'] = df['close'].rolling(20).mean()
    df['bb_std'] = df['close'].rolling(20).std()
    df['bb_upper'] = df['bb_ma'] + 2 * df['bb_std']
    df['bb_lower'] = df['bb_ma'] - 2 * df['bb_std']

    # Stochastic
    low14 = df['low'].rolling(14).min()
    high14 = df['high'].rolling(14).max()
    df['stoch_k'] = 100 * (df['close'] - low14) / (high14 - low14)
    df['stoch_d'] = df['stoch_k'].rolling(3).mean()

    # CCI
    tp = (df['high'] + df['low'] + df['close']) / 3
    sma_tp = tp.rolling(20).mean()
    mad = tp.rolling(20).apply(lambda x: np.abs(x - x.mean()).mean())
    df['cci'] = (tp - sma_tp) / (0.015 * mad)

    # Heiken Ashi
    df['ha_close'] = (df['open'] + df['high'] + df['low'] + df['close']) / 4
    df['ha_open'] = (df['open'].shift(1) + df['close'].shift(1)) / 2
    df['ha_high'] = df[['high', 'ha_open', 'ha_close']].max(axis=1)
    df['ha_low'] = df[['low', 'ha_open', 'ha_close']].min(axis=1)

    # Alligator (simplificado)
    df['jaw'] = df['close'].rolling(13).mean().shift(8)
    df['teeth'] = df['close'].rolling(8).mean().shift(5)
    df['lips'] = df['close'].rolling(5).mean().shift(3)

    # Momentum
    df['momentum'] = df['close'] - df['close'].shift(14)

    # Volumen promedio
    df['vol_avg'] = df['volume'].rolling(20).mean()
    df['vol_ratio'] = df['volume'] / df['vol_avg']

    return df

# =========================
# 10 ESTRATEGIAS (cada una retorna True/False y la dirección)
# =========================
def estrategia_1_ema_adx(df):
    """Cruce de EMAs + ADX > 25"""
    if len(df) < 2:
        return None
    last = df.iloc[-1]
    prev = df.iloc[-2]
    if prev['ema9'] <= prev['ema21'] and last['ema9'] > last['ema21'] and last['adx'] > 25:
        return 'CALL'
    if prev['ema9'] >= prev['ema21'] and last['ema9'] < last['ema21'] and last['adx'] > 25:
        return 'PUT'
    return None

def estrategia_2_macd_adx(df):
    """MACD crossover + ADX < 25 o bajando"""
    if len(df) < 2:
        return None
    last = df.iloc[-1]
    prev = df.iloc[-2]
    if prev['macd'] <= prev['signal'] and last['macd'] > last['signal'] and last['hist'] > 0 and last['adx'] < 25:
        return 'CALL'
    if prev['macd'] >= prev['signal'] and last['macd'] < last['signal'] and last['hist'] < 0 and last['adx'] < 25:
        return 'PUT'
    return None

def estrategia_3_bb_rsi(df):
    """Bollinger + RSI extremo"""
    last = df.iloc[-1]
    if last['close'] <= last['bb_lower'] and last['rsi'] < 30:
        return 'CALL'
    if last['close'] >= last['bb_upper'] and last['rsi'] > 70:
        return 'PUT'
    return None

def estrategia_4_sar_ema(df):
    """Parabolic SAR + EMA 50 (simulado con cruce de precio y EMA50)"""
    if len(df) < 2:
        return None
    last = df.iloc[-1]
    prev = df.iloc[-2]
    if prev['close'] <= prev['ema50'] and last['close'] > last['ema50']:
        return 'CALL'
    if prev['close'] >= prev['ema50'] and last['close'] < last['ema50']:
        return 'PUT'
    return None

def estrategia_5_stoch_adx(df):
    """Stochastic + ADX"""
    if len(df) < 2:
        return None
    last = df.iloc[-1]
    prev = df.iloc[-2]
    if prev['stoch_k'] < 20 and last['stoch_k'] > last['stoch_d'] and last['adx'] > 25:
        return 'CALL'
    if prev['stoch_k'] > 80 and last['stoch_k'] < last['stoch_d'] and last['adx'] > 25:
        return 'PUT'
    return None

def estrategia_6_supertrend_adx(df):
    """Supertrend simulado con EMA + ADX"""
    last = df.iloc[-1]
    if last['ema9'] > last['ema21'] and last['adx'] > 25:
        return 'CALL'
    if last['ema9'] < last['ema21'] and last['adx'] > 25:
        return 'PUT'
    return None

def estrategia_7_heiken_ashi_ema(df):
    """Heiken Ashi + EMA 9"""
    if len(df) < 2:
        return None
    last = df.iloc[-1]
    prev = df.iloc[-2]
    if prev['ha_close'] > prev['ha_open'] and last['ha_close'] > last['ha_open'] and last['close'] > last['ema9']:
        return 'CALL'
    if prev['ha_close'] < prev['ha_open'] and last['ha_close'] < last['ha_open'] and last['close'] < last['ema9']:
        return 'PUT'
    return None

def estrategia_8_cci_bb(df):
    """CCI + Bollinger"""
    last = df.iloc[-1]
    if last['cci'] > -100 and last['close'] <= last['bb_lower']:
        return 'CALL'
    if last['cci'] < 100 and last['close'] >= last['bb_upper']:
        return 'PUT'
    return None

def estrategia_9_alligator_momentum(df):
    """Alligator + Momentum"""
    last = df.iloc[-1]
    if last['lips'] > last['teeth'] > last['jaw'] and last['momentum'] > 0:
        return 'CALL'
    if last['lips'] < last['teeth'] < last['jaw'] and last['momentum'] < 0:
        return 'PUT'
    return None

def estrategia_10_pivot_stoch(df):
    """Pivot Points + Stochastic (simulado)"""
    last = df.iloc[-1]
    max20 = df['high'].iloc[-20:].max()
    min20 = df['low'].iloc[-20:].min()
    if last['close'] < min20 * 1.002 and last['stoch_k'] < 20 and last['stoch_k'] > last['stoch_d']:
        return 'CALL'
    if last['close'] > max20 * 0.998 and last['stoch_k'] > 80 and last['stoch_k'] < last['stoch_d']:
        return 'PUT'
    return None

# Lista de estrategias (nombre, función)
ESTRATEGIAS = [
    ("EMA + ADX", estrategia_1_ema_adx),
    ("MACD + ADX", estrategia_2_macd_adx),
    ("BB + RSI", estrategia_3_bb_rsi),
    ("SAR + EMA50", estrategia_4_sar_ema),
    ("Stoch + ADX", estrategia_5_stoch_adx),
    ("Supertrend + ADX", estrategia_6_supertrend_adx),
    ("Heiken Ashi + EMA9", estrategia_7_heiken_ashi_ema),
    ("CCI + BB", estrategia_8_cci_bb),
    ("Alligator + Momentum", estrategia_9_alligator_momentum),
    ("Pivot + Stoch", estrategia_10_pivot_stoch)
]

# =========================
# EVALUAR UN ACTIVO (retorna puntuación y lista de estrategias cumplidas)
# =========================
def evaluar_activo(api, asset, estrategias_activas):
    """
    Retorna un dict con la información del activo si es estable y tiene al menos una estrategia cumplida.
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

        # Evaluar cada estrategia activa
        puntuacion = 0
        estrategias_cumplidas = []
        direccion_general = None
        for nombre, funcion in ESTRATEGIAS:
            if nombre not in estrategias_activas:
                continue
            try:
                direccion = funcion(df)
                if direccion:
                    puntuacion += 100
                    estrategias_cumplidas.append(nombre)
                    if direccion_general is None:
                        direccion_general = direccion
                    elif direccion_general != direccion:
                        # Si hay estrategias que apuntan en direcciones opuestas, anulamos
                        direccion_general = None
            except Exception as e:
                continue

        # Calcular estabilidad (baja volatilidad)
        volatilidad = (df['high'].iloc[-20:].max() - df['low'].iloc[-20:].min()) / df['close'].iloc[-1]
        estable = volatilidad < 0.015  # 1.5% en 20 velas

        if puntuacion > 0 and estable and direccion_general is not None:
            return {
                'asset': asset,
                'puntuacion': puntuacion,
                'estrategias': estrategias_cumplidas,
                'direccion': direccion_general,
                'precio': df['close'].iloc[-1]
            }
        return None
    except Exception as e:
        logger.error(f"Error evaluando {asset}: {e}")
        return None

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
# SELECCIONAR LOS MEJORES ACTIVOS DE UNA RONDA (hasta 2)
# =========================
def seleccionar_mejores_de_ronda(api, lista_activos, estrategias_activas, max_activos=2):
    """
    Evalúa una lista de activos y retorna los mejores (hasta max_activos) basado en puntuación y estabilidad.
    """
    resultados = []
    for asset in lista_activos:
        try:
            res = evaluar_activo(api, asset, estrategias_activas)
            if res:
                resultados.append(res)
            time.sleep(0.1)
        except:
            continue
    resultados.sort(key=lambda x: x['puntuacion'], reverse=True)
    return resultados[:max_activos]

# =========================
# GENERAR ALERTA PREVIA (simulada)
# =========================
def generar_alerta_previa(activo):
    return f"🔔 {activo['asset']} - Preparándose: cumple {len(activo['estrategias'])} estrategias. Señal inminente en ~2-3 min."

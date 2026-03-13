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

# Lista de activos comunes (fallback)
FALLBACK_ACTIVOS = [
    "EURUSD-OTC", "GBPUSD-OTC", "AUDUSD-OTC", "USDJPY-OTC",
    "USDCHF-OTC", "NZDUSD-OTC", "USDCAD-OTC", "GBPJPY-OTC",
    "EURJPY-OTC", "AUDCAD-OTC", "AUDJPY-OTC", "EURGBP-OTC",
    "EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCHF", "NZDUSD", "USDCAD"
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

    # Alligator
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
# 10 ESTRATEGIAS (cada una devuelve dirección y peso)
# =========================
def estrategia_1_ema_adx(df):
    if len(df) < 2:
        return None, 0
    last = df.iloc[-1]
    if last['adx'] > 15:
        if last['ema9'] > last['ema21']:
            return 'CALL', 8
        elif last['ema9'] < last['ema21']:
            return 'PUT', 8
    return None, 0

def estrategia_2_macd_adx(df):
    if len(df) < 2:
        return None, 0
    last = df.iloc[-1]
    prev = df.iloc[-2]
    if last['adx'] < 20:
        if prev['macd'] <= prev['signal'] and last['macd'] > last['signal'] and last['hist'] > 0:
            return 'CALL', 7
        if prev['macd'] >= prev['signal'] and last['macd'] < last['signal'] and last['hist'] < 0:
            return 'PUT', 7
    return None, 0

def estrategia_3_bb_rsi(df):
    last = df.iloc[-1]
    if last['close'] <= last['bb_lower'] and last['rsi'] < 30:
        return 'CALL', 9
    if last['close'] >= last['bb_upper'] and last['rsi'] > 70:
        return 'PUT', 9
    return None, 0

def estrategia_4_sar_ema(df):
    if len(df) < 2:
        return None, 0
    last = df.iloc[-1]
    prev = df.iloc[-2]
    if prev['close'] <= prev['ema50'] and last['close'] > last['ema50']:
        return 'CALL', 6
    if prev['close'] >= prev['ema50'] and last['close'] < last['ema50']:
        return 'PUT', 6
    return None, 0

def estrategia_5_stoch_adx(df):
    if len(df) < 2:
        return None, 0
    last = df.iloc[-1]
    prev = df.iloc[-2]
    if last['adx'] > 20:
        if prev['stoch_k'] < 20 and last['stoch_k'] > last['stoch_d']:
            return 'CALL', 8
        if prev['stoch_k'] > 80 and last['stoch_k'] < last['stoch_d']:
            return 'PUT', 8
    return None, 0

def estrategia_6_supertrend_ema(df):
    last = df.iloc[-1]
    if last['ema9'] > last['ema21'] and last['ema9'] > last['ema50']:
        return 'CALL', 6
    if last['ema9'] < last['ema21'] and last['ema9'] < last['ema50']:
        return 'PUT', 6
    return None, 0

def estrategia_7_heiken_ashi_ema(df):
    if len(df) < 2:
        return None, 0
    last = df.iloc[-1]
    prev = df.iloc[-2]
    if prev['ha_close'] > prev['ha_open'] and last['ha_close'] > last['ha_open'] and last['close'] > last['ema9']:
        return 'CALL', 7
    if prev['ha_close'] < prev['ha_open'] and last['ha_close'] < last['ha_open'] and last['close'] < last['ema9']:
        return 'PUT', 7
    return None, 0

def estrategia_8_cci_bb(df):
    last = df.iloc[-1]
    if last['cci'] > -100 and last['close'] <= last['bb_lower']:
        return 'CALL', 8
    if last['cci'] < 100 and last['close'] >= last['bb_upper']:
        return 'PUT', 8
    return None, 0

def estrategia_9_alligator_momentum(df):
    last = df.iloc[-1]
    if last['lips'] > last['teeth'] > last['jaw'] and last['momentum'] > 0:
        return 'CALL', 7
    if last['lips'] < last['teeth'] < last['jaw'] and last['momentum'] < 0:
        return 'PUT', 7
    return None, 0

def estrategia_10_volumen_ema(df):
    last = df.iloc[-1]
    if last['vol_ratio'] > 1.5 and last['ema9'] > last['ema21']:
        return 'CALL', 6
    if last['vol_ratio'] > 1.5 and last['ema9'] < last['ema21']:
        return 'PUT', 6
    return None, 0

# Lista de estrategias (nombre, función, peso base)
ESTRATEGIAS = [
    ("EMA + ADX", estrategia_1_ema_adx, 8),
    ("MACD reversión", estrategia_2_macd_adx, 7),
    ("BB + RSI", estrategia_3_bb_rsi, 9),
    ("Cruce EMA50", estrategia_4_sar_ema, 6),
    ("Stoch + ADX", estrategia_5_stoch_adx, 8),
    ("Supertrend", estrategia_6_supertrend_ema, 6),
    ("Heiken Ashi", estrategia_7_heiken_ashi_ema, 7),
    ("CCI + BB", estrategia_8_cci_bb, 8),
    ("Alligator", estrategia_9_alligator_momentum, 7),
    ("Volumen + EMA", estrategia_10_volumen_ema, 6)
]

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

        votos_call = 0
        votos_put = 0
        peso_call = 0
        peso_put = 0
        estrategias_activas = []

        for nombre, func, peso_base in ESTRATEGIAS:
            try:
                direc, peso_extra = func(df)
                if direc:
                    estrategias_activas.append(nombre)
                    if direc == 'CALL':
                        votos_call += 1
                        peso_call += peso_base + (peso_extra or 0)
                    else:
                        votos_put += 1
                        peso_put += peso_base + (peso_extra or 0)
            except:
                continue

        if votos_call + votos_put == 0:
            return None

        if votos_call > votos_put:
            direccion = 'CALL'
            fuerza = peso_call / votos_call
        elif votos_put > votos_call:
            direccion = 'PUT'
            fuerza = peso_put / votos_put
        else:
            if peso_call > peso_put:
                direccion = 'CALL'
                fuerza = peso_call / votos_call if votos_call > 0 else 0
            else:
                direccion = 'PUT'
                fuerza = peso_put / votos_put if votos_put > 0 else 0

        puntuacion = (votos_call + votos_put) * 10 + (peso_call + peso_put)

        return {
            'asset': asset,
            'direccion': direccion,
            'votos_call': votos_call,
            'votos_put': votos_put,
            'fuerza': fuerza,
            'estrategias': estrategias_activas,
            'puntuacion': puntuacion,
            'precio': df['close'].iloc[-1]
        }
    except Exception as e:
        logger.error(f"Error evaluando {asset}: {e}")
        return None

# =========================
# OBTENER ACTIVOS ABIERTOS
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
        logger.info(f"Se obtuvieron {len(activos)} activos abiertos")
        if not activos:
            logger.warning("Usando lista de activos predeterminada (fallback)")
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
# SELECCIONAR EL MEJOR ACTIVO DE UNA RONDA
# =========================
def seleccionar_mejor_activo(api, lista_activos, min_votos=2):
    mejores = []
    for asset in lista_activos:
        try:
            res = evaluar_activo(api, asset)
            if res and (res['votos_call'] + res['votos_put']) >= min_votos:
                mejores.append(res)
            time.sleep(0.1)
        except:
            continue
    if not mejores:
        return None
    mejores.sort(key=lambda x: x['puntuacion'], reverse=True)
    return mejores[0]

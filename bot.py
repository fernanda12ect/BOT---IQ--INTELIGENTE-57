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

# Lista de activos comunes por si la API no devuelve datos
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
    df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()

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
    df['bb_width'] = df['bb_upper'] - df['bb_lower']

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

    # Parabolic SAR (aproximación simple)
    df['sar'] = df['close'].shift(1)  # placeholder, se podría implementar

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
# 10 ESTRATEGIAS (cada una devuelve (direccion, fuerza) o (None, 0))
# =========================
def estrategia_1_ema_adx(df):
    """EMA 9/21 + ADX > 20"""
    if len(df) < 2:
        return None, 0
    last = df.iloc[-1]
    if last['adx'] > 20:
        if last['ema9'] > last['ema21']:
            return 'CALL', last['adx']
        elif last['ema9'] < last['ema21']:
            return 'PUT', last['adx']
    return None, 0

def estrategia_2_macd_crossover(df):
    """MACD cruce sobre cero"""
    if len(df) < 2:
        return None, 0
    last = df.iloc[-1]
    prev = df.iloc[-2]
    if prev['macd'] <= 0 and last['macd'] > 0 and last['hist'] > 0:
        return 'CALL', 70
    if prev['macd'] >= 0 and last['macd'] < 0 and last['hist'] < 0:
        return 'PUT', 70
    return None, 0

def estrategia_3_bb_rsi(df):
    """Bollinger + RSI extremo"""
    last = df.iloc[-1]
    if last['close'] <= last['bb_lower'] and last['rsi'] < 30:
        return 'CALL', 80
    if last['close'] >= last['bb_upper'] and last['rsi'] > 70:
        return 'PUT', 80
    return None, 0

def estrategia_4_stoch_adx(df):
    """Stochastic + ADX > 25"""
    if len(df) < 2:
        return None, 0
    last = df.iloc[-1]
    if last['adx'] > 25 and last['stoch_k'] < 20 and last['stoch_k'] > last['stoch_d']:
        return 'CALL', 75
    if last['adx'] > 25 and last['stoch_k'] > 80 and last['stoch_k'] < last['stoch_d']:
        return 'PUT', 75
    return None, 0

def estrategia_5_ha_ema(df):
    """Heiken Ashi + EMA9"""
    if len(df) < 2:
        return None, 0
    last = df.iloc[-1]
    if last['ha_close'] > last['ha_open'] and last['close'] > last['ema9']:
        return 'CALL', 65
    if last['ha_close'] < last['ha_open'] and last['close'] < last['ema9']:
        return 'PUT', 65
    return None, 0

def estrategia_6_cci_bb(df):
    """CCI + Bollinger"""
    last = df.iloc[-1]
    if last['cci'] > -100 and last['close'] <= last['bb_lower']:
        return 'CALL', 70
    if last['cci'] < 100 and last['close'] >= last['bb_upper']:
        return 'PUT', 70
    return None, 0

def estrategia_7_alligator_momentum(df):
    """Alligator + Momentum"""
    last = df.iloc[-1]
    if last['lips'] > last['teeth'] > last['jaw'] and last['momentum'] > 0:
        return 'CALL', 75
    if last['lips'] < last['teeth'] < last['jaw'] and last['momentum'] < 0:
        return 'PUT', 75
    return None, 0

def estrategia_8_pivot_stoch(df):
    """Pivotes + Stochastic (simulado con máximos/mínimos)"""
    last = df.iloc[-1]
    max20 = df['high'].iloc[-20:].max()
    min20 = df['low'].iloc[-20:].min()
    if last['close'] < min20 * 1.002 and last['stoch_k'] < 20 and last['stoch_k'] > last['stoch_d']:
        return 'CALL', 70
    if last['close'] > max20 * 0.998 and last['stoch_k'] > 80 and last['stoch_k'] < last['stoch_d']:
        return 'PUT', 70
    return None, 0

def estrategia_9_ema_trend(df):
    """EMA 50/200 tendencia de largo plazo"""
    last = df.iloc[-1]
    if last['ema50'] > last['ema200']:
        return 'CALL', 60
    elif last['ema50'] < last['ema200']:
        return 'PUT', 60
    return None, 0

def estrategia_10_atr_breakout(df):
    """Breakout con ATR"""
    if len(df) < 2:
        return None, 0
    last = df.iloc[-1]
    prev = df.iloc[-2]
    if last['close'] > prev['high'] and last['vol_ratio'] > 1.5:
        return 'CALL', 70
    if last['close'] < prev['low'] and last['vol_ratio'] > 1.5:
        return 'PUT', 70
    return None, 0

# Lista de estrategias (nombre, función)
ESTRATEGIAS = [
    ("EMA + ADX", estrategia_1_ema_adx),
    ("MACD Crossover", estrategia_2_macd_crossover),
    ("BB + RSI", estrategia_3_bb_rsi),
    ("Stoch + ADX", estrategia_4_stoch_adx),
    ("Heiken Ashi + EMA9", estrategia_5_ha_ema),
    ("CCI + BB", estrategia_6_cci_bb),
    ("Alligator + Momentum", estrategia_7_alligator_momentum),
    ("Pivot + Stoch", estrategia_8_pivot_stoch),
    ("Tendencia Largo Plazo", estrategia_9_ema_trend),
    ("ATR Breakout", estrategia_10_atr_breakout)
]

# =========================
# EVALUAR UN ACTIVO (retorna puntuación, dirección y estrategias que coinciden)
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

        resultados = []
        direcciones = []
        for nombre, funcion in ESTRATEGIAS:
            try:
                direc, fuerza = funcion(df)
                if direc:
                    resultados.append((nombre, direc, fuerza))
                    direcciones.append(direc)
            except:
                continue

        if not resultados:
            return None

        # Determinar dirección mayoritaria
        if not direcciones:
            return None
        call_count = direcciones.count('CALL')
        put_count = direcciones.count('PUT')
        if call_count == put_count:
            return None  # empate, no hay consenso
        direccion_final = 'CALL' if call_count > put_count else 'PUT'
        fuerza_total = sum(f for _, _, f in resultados) / len(resultados)  # promedio
        estrategias_que_cumplen = [nombre for nombre, dir, _ in resultados if dir == direccion_final]

        return {
            'asset': asset,
            'direccion': direccion_final,
            'fuerza': fuerza_total,
            'num_estrategias': len(estrategias_que_cumplen),
            'estrategias': estrategias_que_cumplen,
            'precio': df['close'].iloc[-1]
        }
    except Exception as e:
        logger.error(f"Error evaluando {asset}: {e}")
        return None

# =========================
# VERIFICAR CRUCE DE EMA (para confirmación de entrada)
# =========================
def verificar_cruce_ema(api, asset, direccion_esperada):
    """
    Retorna True si en la última vela se ha producido un cruce de EMA9/21 en la dirección esperada.
    """
    try:
        candles = api.get_candles(asset, 60, 5, time.time())  # últimas 5 velas de 1 min
        if not candles or len(candles) < 2:
            return False
        df = pd.DataFrame(candles)
        for col in ['open', 'max', 'min', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df.dropna(inplace=True)
        if len(df) < 2:
            return False

        # Calcular EMAs sobre velas de 1 min
        df['ema9'] = df['close'].ewm(span=9, adjust=False).mean()
        df['ema21'] = df['close'].ewm(span=21, adjust=False).mean()

        last = df.iloc[-1]
        prev = df.iloc[-2]
        if direccion_esperada == 'CALL':
            return prev['ema9'] <= prev['ema21'] and last['ema9'] > last['ema21']
        else:
            return prev['ema9'] >= prev['ema21'] and last['ema9'] < last['ema21']
    except Exception as e:
        logger.error(f"Error verificando cruce para {asset}: {e}")
        return False

# =========================
# OBTENER ACTIVOS ABIERTOS (con fallback)
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
# SELECCIONAR EL MEJOR ACTIVO (basado en número de estrategias y fuerza)
# =========================
def seleccionar_mejor_activo(api, lista_activos, min_estrategias=2):
    """
    Elige el activo con mayor número de estrategias en la misma dirección.
    Si hay empate, el de mayor fuerza promedio.
    """
    mejores = []
    for asset in lista_activos:
        try:
            res = evaluar_activo(api, asset)
            if res and res['num_estrategias'] >= min_estrategias:
                mejores.append(res)
            time.sleep(0.1)
        except:
            continue
    if not mejores:
        return None
    # Ordenar: primero por número de estrategias, luego por fuerza
    mejores.sort(key=lambda x: (x['num_estrategias'], x['fuerza']), reverse=True)
    return mejores[0]

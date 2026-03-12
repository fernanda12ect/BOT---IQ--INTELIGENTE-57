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

# Lista de activos por si falla la API
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
# 10 ESTRATEGIAS (devuelven dirección si se cumplen)
# =========================
def estrategia_1_ema_adx(df):
    """EMA9 cruza EMA21 + ADX > 20"""
    if len(df) < 2:
        return None
    last = df.iloc[-1]
    prev = df.iloc[-2]
    if prev['ema9'] <= prev['ema21'] and last['ema9'] > last['ema21'] and last['adx'] > 20:
        return 'CALL'
    if prev['ema9'] >= prev['ema21'] and last['ema9'] < last['ema21'] and last['adx'] > 20:
        return 'PUT'
    return None

def estrategia_2_macd_adx(df):
    """MACD cruza señal + ADX < 25 (mercado lateral con posible reversión)"""
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
    """Precio cruza EMA50 (simula SAR)"""
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
    """Stochastic + ADX > 20"""
    if len(df) < 2:
        return None
    last = df.iloc[-1]
    prev = df.iloc[-2]
    if prev['stoch_k'] < 20 and last['stoch_k'] > last['stoch_d'] and last['adx'] > 20:
        return 'CALL'
    if prev['stoch_k'] > 80 and last['stoch_k'] < last['stoch_d'] and last['adx'] > 20:
        return 'PUT'
    return None

def estrategia_6_supertrend_adx(df):
    """EMA9/21 alineadas + ADX > 20 (simula Supertrend)"""
    last = df.iloc[-1]
    if last['ema9'] > last['ema21'] and last['adx'] > 20:
        return 'CALL'
    if last['ema9'] < last['ema21'] and last['adx'] > 20:
        return 'PUT'
    return None

def estrategia_7_heiken_ashi_ema(df):
    """Heiken Ashi + EMA9"""
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
    """Niveles de 20 velas + Stochastic"""
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
# EVALUAR ACTIVO PARA SELECCIÓN (consenso de estrategias)
# =========================
def evaluar_activo_seleccion(api, asset, min_consenso=2):
    """
    Evalúa un activo y retorna:
        - consenso: número de estrategias que coinciden en la misma dirección
        - direccion: la dirección mayoritaria ('CALL'/'PUT')
        - fuerza: ADX
        - estrategias_cumplidas: lista de nombres
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
        conteo = {'CALL': 0, 'PUT': 0}
        estrategias_cumplidas = {'CALL': [], 'PUT': []}

        for nombre, funcion in ESTRATEGIAS:
            try:
                direc = funcion(df)
                if direc:
                    conteo[direc] += 1
                    estrategias_cumplidas[direc].append(nombre)
            except Exception as e:
                continue

        if conteo['CALL'] >= min_consenso or conteo['PUT'] >= min_consenso:
            direccion = 'CALL' if conteo['CALL'] > conteo['PUT'] else 'PUT'
            consenso = conteo[direccion]
            return {
                'asset': asset,
                'direccion': direccion,
                'consenso': consenso,
                'fuerza': df['adx'].iloc[-1],
                'precio': df['close'].iloc[-1],
                'estrategias': estrategias_cumplidas[direccion]
            }
        return None
    except Exception as e:
        logger.error(f"Error evaluando {asset}: {e}")
        return None

# =========================
# DETECCIÓN DE PULLBACK
# =========================
def detectar_pullback(df, direccion, umbral_pullback=0.3):
    if len(df) < 5:
        return False
    ultimas = df.iloc[-5:]
    precio_actual = ultimas['close'].iloc[-1]
    atr_actual = df['atr'].iloc[-1]

    if direccion == 'CALL':
        maximo_reciente = ultimas['high'].max()
        if maximo_reciente - precio_actual > umbral_pullback * atr_actual:
            return True
    else:
        minimo_reciente = ultimas['low'].min()
        if precio_actual - minimo_reciente > umbral_pullback * atr_actual:
            return True
    return False

# =========================
# CONFIRMACIÓN DE CRUCE DE EMA
# =========================
def confirmar_cruce_ema(df, direccion, ventana=2):
    if len(df) < ventana + 1:
        return False
    for i in range(1, ventana + 1):
        prev = df.iloc[-i-1]
        last = df.iloc[-i]
        if direccion == 'CALL':
            if prev['ema9'] <= prev['ema21'] and last['ema9'] > last['ema21']:
                return True
        else:
            if prev['ema9'] >= prev['ema21'] and last['ema9'] < last['ema21']:
                return True
    return False

# =========================
# DETECCIÓN DE RUPTURA DE PULLBACK
# =========================
def detectar_ruptura_pullback(df, direccion):
    """
    Detecta si el precio ha roto el nivel del pullback (máximo en CALL, mínimo en PUT).
    """
    if len(df) < 5:
        return False
    ultimas = df.iloc[-5:]
    precio_actual = ultimas['close'].iloc[-1]
    if direccion == 'CALL':
        maximo_reciente = ultimas['high'].max()
        return precio_actual > maximo_reciente
    else:
        minimo_reciente = ultimas['low'].min()
        return precio_actual < minimo_reciente

# =========================
# EVALUAR ACTIVO EN SEGUIMIENTO (para señal)
# =========================
def evaluar_activo_seguimiento(api, asset, direccion_esperada, umbral_pullback=0.3, ventana_cruce=2):
    """
    Retorna (lista_para_entrar, direccion, fuerza, estrategia)
    """
    try:
        candles = api.get_candles(asset, 300, 100, time.time())
        if not candles or len(candles) < 50:
            return False, None, 0, None
        df = pd.DataFrame(candles)
        for col in ['open', 'max', 'min', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df.dropna(inplace=True)
        if len(df) < 50:
            return False, None, 0, None

        df = calcular_indicadores(df)
        # Verificar que la dirección sigue siendo la misma
        conteo = {'CALL': 0, 'PUT': 0}
        for _, funcion in ESTRATEGIAS:
            try:
                direc = funcion(df)
                if direc:
                    conteo[direc] += 1
            except:
                continue
        direccion_actual = 'CALL' if conteo['CALL'] > conteo['PUT'] else 'PUT' if conteo['PUT'] > conteo['CALL'] else None
        if direccion_actual != direccion_esperada:
            return False, None, 0, None

        # Detectar condiciones
        pullback = detectar_pullback(df, direccion_esperada, umbral_pullback)
        cruce = confirmar_cruce_ema(df, direccion_esperada, ventana_cruce)
        ruptura = detectar_ruptura_pullback(df, direccion_esperada)

        # La señal es válida si hay pullback y (cruce o ruptura)
        lista_para_entrar = pullback and (cruce or ruptura)
        estrategia = f"Pullback + {'cruce EMA' if cruce else 'ruptura de nivel'}"
        return lista_para_entrar, direccion_esperada, df['adx'].iloc[-1], estrategia
    except Exception as e:
        logger.error(f"Error en seguimiento de {asset}: {e}")
        return False, None, 0, None

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
        if not activos:
            return FALLBACK_ACTIVOS
        return activos
    except Exception as e:
        logger.error(f"Error obteniendo activos: {e}")
        return FALLBACK_ACTIVOS

# =========================
# SELECCIONAR EL MEJOR ACTIVO
# =========================
def seleccionar_mejor_activo(api, lista_activos, min_consenso=2):
    mejores = []
    for asset in lista_activos:
        try:
            res = evaluar_activo_seleccion(api, asset, min_consenso)
            if res:
                mejores.append(res)
            time.sleep(0.1)
        except:
            continue
    if not mejores:
        return None
    # Ordenar por consenso descendente y luego por fuerza
    mejores.sort(key=lambda x: (x['consenso'], x['fuerza']), reverse=True)
    return mejores[0]

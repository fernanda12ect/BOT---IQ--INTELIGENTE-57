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

    # Bollinger Bands
    df['bb_ma'] = df['close'].rolling(20).mean()
    df['bb_std'] = df['close'].rolling(20).std()
    df['bb_upper'] = df['bb_ma'] + 2 * df['bb_std']
    df['bb_lower'] = df['bb_ma'] - 2 * df['bb_std']
    df['bb_width'] = df['bb_upper'] - df['bb_lower']

    return df

# =========================
# DETECCIÓN DE TENDENCIA (más flexible)
# =========================
def detectar_tendencia(df, umbral_adx=12):
    """
    Retorna dirección de tendencia ('CALL'/'PUT') y fuerza (ADX) si:
    - ADX > umbral (por defecto 12)
    - EMA9 y EMA21 están alineadas (EMA9 > EMA21 para CALL, EMA9 < EMA21 para PUT)
    """
    if len(df) < 50:
        return None, 0
    last = df.iloc[-1]
    if last['adx'] <= umbral_adx:
        return None, 0

    if last['ema9'] > last['ema21']:
        return 'CALL', last['adx']
    elif last['ema9'] < last['ema21']:
        return 'PUT', last['adx']
    return None, 0

# =========================
# DETECCIÓN DE PULLBACK
# =========================
def detectar_pullback(df, tendencia, umbral_pullback=0.3):
    if len(df) < 5:
        return False
    ultimas = df.iloc[-5:]
    precio_actual = ultimas['close'].iloc[-1]
    atr_actual = df['atr'].iloc[-1]

    if tendencia == 'CALL':
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
def confirmar_cruce_ema(df, tendencia, ventana=2):
    if len(df) < ventana + 1:
        return False
    for i in range(1, ventana + 1):
        prev = df.iloc[-i-1]
        last = df.iloc[-i]
        if tendencia == 'CALL':
            if prev['ema9'] <= prev['ema21'] and last['ema9'] > last['ema21']:
                return True
        else:
            if prev['ema9'] >= prev['ema21'] and last['ema9'] < last['ema21']:
                return True
    return False

# =========================
# EVALUAR ACTIVO PARA SELECCIÓN
# =========================
def evaluar_activo_seleccion(api, asset, umbral_adx=12):
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
        tendencia, fuerza = detectar_tendencia(df, umbral_adx)
        if tendencia is None:
            return None

        # Puntuación solo basada en ADX (más simple)
        puntuacion = fuerza
        return {
            'asset': asset,
            'tendencia': tendencia,
            'fuerza': fuerza,
            'puntuacion': puntuacion,
            'precio': df['close'].iloc[-1]
        }
    except Exception as e:
        logger.error(f"Error evaluando {asset}: {e}")
        return None

# =========================
# EVALUAR ACTIVO EN SEGUIMIENTO
# =========================
def evaluar_activo_seguimiento(api, asset, tendencia_esperada, umbral_pullback=0.3, ventana_cruce=2):
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
        tendencia_actual, fuerza = detectar_tendencia(df, umbral_adx=10)  # umbral más bajo en seguimiento
        if tendencia_actual != tendencia_esperada:
            return False, None, 0, None

        pullback = detectar_pullback(df, tendencia_actual, umbral_pullback)
        cruce = confirmar_cruce_ema(df, tendencia_actual, ventana_cruce)

        lista_para_entrar = pullback and cruce
        estrategia = f"Pullback + cruce EMA en tendencia {'alcista' if tendencia_actual == 'CALL' else 'bajista'}"
        return lista_para_entrar, tendencia_actual, fuerza, estrategia
    except Exception as e:
        logger.error(f"Error en seguimiento de {asset}: {e}")
        return False, None, 0, None

# =========================
# OBTENER ACTIVOS ABIERTOS (todos los binarios)
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
        return activos
    except Exception as e:
        logger.error(f"Error obteniendo activos: {e}")
        return []

# =========================
# SELECCIONAR EL MEJOR ACTIVO DE UNA RONDA
# =========================
def seleccionar_mejor_activo(api, lista_activos, umbral_adx=12, min_puntuacion=12):
    """
    Elige el activo con mayor puntuación (ADX) que supere el mínimo.
    """
    mejores = []
    for asset in lista_activos:
        try:
            res = evaluar_activo_seleccion(api, asset, umbral_adx)
            if res and res['puntuacion'] >= min_puntuacion:
                mejores.append(res)
            time.sleep(0.1)
        except:
            continue
    if not mejores:
        return None
    mejores.sort(key=lambda x: x['puntuacion'], reverse=True)
    return mejores[0]

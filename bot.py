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
# DETECCIÓN DE TENDENCIA (flexible)
# =========================
def detectar_tendencia(df):
    """
    Retorna la dirección de la tendencia ('CALL'/'PUT') y su fuerza (ADX)
    si se cumplen: ADX > 20 y EMAs alineadas (ema9 > ema21 para CALL, inverso para PUT)
    """
    if len(df) < 50:
        return None, 0
    last = df.iloc[-1]
    if last['adx'] > 20:
        if last['ema9'] > last['ema21']:
            return 'CALL', last['adx']
        elif last['ema9'] < last['ema21']:
            return 'PUT', last['adx']
    return None, 0

# =========================
# DETECCIÓN DE RETROCESO
# =========================
def detectar_retroceso(df, tendencia):
    """
    Analiza las últimas 5 velas para ver si ha ocurrido un retroceso contra la tendencia.
    Retorna True si el precio se ha movido en contra al menos un 0.5 * ATR y luego se ha estabilizado.
    """
    if len(df) < 5:
        return False
    ultimas = df.iloc[-5:]
    precio_actual = ultimas['close'].iloc[-1]
    atr_medio = df['atr'].iloc[-1]

    if tendencia == 'CALL':
        # Retroceso bajista: precio baja respecto al máximo reciente
        maximo_reciente = ultimas['high'].max()
        if maximo_reciente - precio_actual > 0.5 * atr_medio:
            return True
    else:  # PUT
        # Retroceso alcista: precio sube respecto al mínimo reciente
        minimo_reciente = ultimas['low'].min()
        if precio_actual - minimo_reciente > 0.5 * atr_medio:
            return True
    return False

# =========================
# CONFIRMACIÓN DE CRUCE DE EMA
# =========================
def confirmar_cruce_ema(df, tendencia):
    """
    Verifica si ha ocurrido un cruce de EMAs en la dirección de la tendencia en la última vela.
    """
    if len(df) < 2:
        return False
    last = df.iloc[-1]
    prev = df.iloc[-2]
    if tendencia == 'CALL':
        return prev['ema9'] <= prev['ema21'] and last['ema9'] > last['ema21']
    else:
        return prev['ema9'] >= prev['ema21'] and last['ema9'] < last['ema21']

# =========================
# EVALUAR UN ACTIVO PARA SELECCIÓN
# =========================
def evaluar_activo_seleccion(api, asset):
    """
    Versión ligera para selección inicial: solo verifica tendencia y devuelve puntuación.
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
        tendencia, fuerza = detectar_tendencia(df)
        if tendencia is None:
            return None

        # Puntuación simple: fuerza (ADX) + bonus por volumen
        puntuacion = fuerza + (df['vol_ratio'].iloc[-1] * 10)
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
# EVALUAR UN ACTIVO EN SEGUIMIENTO (con retroceso y cruce)
# =========================
def evaluar_activo_seguimiento(api, asset, tendencia_esperada):
    """
    Para un activo ya seleccionado, verifica si hay retroceso y cruce de EMA.
    Retorna: (lista_para_entrar, direccion, fuerza, estrategia) o (False, None, 0, None)
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
        tendencia_actual, fuerza = detectar_tendencia(df)
        if tendencia_actual != tendencia_esperada:
            # La tendencia cambió, ya no es válido
            return False, None, 0, None

        retroceso = detectar_retroceso(df, tendencia_actual)
        cruce = confirmar_cruce_ema(df, tendencia_actual)

        lista_para_entrar = retroceso and cruce
        estrategia = f"Retroceso + cruce EMA en tendencia {'alcista' if tendencia_actual == 'CALL' else 'bajista'}"
        return lista_para_entrar, tendencia_actual, fuerza, estrategia
    except Exception as e:
        logger.error(f"Error en seguimiento de {asset}: {e}")
        return False, None, 0, None

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
# SELECCIONAR EL MEJOR ACTIVO DE UNA RONDA
# =========================
def seleccionar_mejor_activo(api, lista_activos, min_puntuacion=20):
    """
    Elige el activo con mayor puntuación (ADX + volumen) que supere el mínimo.
    """
    mejores = []
    for asset in lista_activos:
        try:
            res = evaluar_activo_seleccion(api, asset)
            if res and res['puntuacion'] >= min_puntuacion:
                mejores.append(res)
            time.sleep(0.1)
        except:
            continue
    if not mejores:
        return None
    mejores.sort(key=lambda x: x['puntuacion'], reverse=True)
    return mejores[0]

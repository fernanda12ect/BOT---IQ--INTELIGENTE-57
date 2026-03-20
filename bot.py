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
    df['ema12'] = df['close'].ewm(span=12, adjust=False).mean()
    df['ema26'] = df['close'].ewm(span=26, adjust=False).mean()
    df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()

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
    df['ema12_macd'] = df['close'].ewm(span=12, adjust=False).mean()
    df['ema26_macd'] = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = df['ema12_macd'] - df['ema26_macd']
    df['signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    df['hist'] = df['macd'] - df['signal']

    # Volumen promedio
    df['vol_avg'] = df['volume'].rolling(20).mean()
    df['vol_ratio'] = df['volume'] / df['vol_avg']

    return df

# =========================
# DETECCIÓN DE DIVERGENCIAS (más sensible, ventana 3)
# =========================
def detectar_divergencia(df, ventana=3):
    """
    Detecta divergencias alcistas/bajistas en las últimas `ventana` velas.
    Retorna (direccion, descripcion, fuerza) o None.
    """
    if len(df) < ventana:
        return None
    segmento = df.iloc[-ventana:].copy()

    # Para ventana pequeña, necesitamos al menos 3 puntos para comparar
    if len(segmento) < 3:
        return None

    # Divergencia alcista: precio hace mínimo más bajo, indicador hace mínimo más alto
    # Buscamos el mínimo más bajo de precio y el mínimo más alto del indicador
    min_precio = segmento['low'].min()
    min_precio_idx = segmento['low'].idxmin()
    min_rsi = segmento['rsi'].min()
    min_rsi_idx = segmento['rsi'].idxmin()
    min_macd = segmento['macd'].min()
    min_macd_idx = segmento['macd'].idxmin()

    # Divergencia bajista: precio hace máximo más alto, indicador hace máximo más bajo
    max_precio = segmento['high'].max()
    max_precio_idx = segmento['high'].idxmax()
    max_rsi = segmento['rsi'].max()
    max_rsi_idx = segmento['rsi'].idxmax()
    max_macd = segmento['macd'].max()
    max_macd_idx = segmento['macd'].idxmax()

    # ADX para dar fuerza
    adx_actual = df['adx'].iloc[-1] if not pd.isna(df['adx'].iloc[-1]) else 0
    fuerza_base = 50 + min(adx_actual, 50)  # hasta 100

    # Divergencia alcista RSI
    if min_precio_idx != min_rsi_idx and segmento.loc[min_precio_idx, 'low'] < segmento.loc[min_rsi_idx, 'low']:
        if segmento.loc[min_rsi_idx, 'rsi'] > segmento.loc[min_precio_idx, 'rsi']:
            fuerza = fuerza_base + (segmento['vol_ratio'].iloc[-1] * 10)
            return ('CALL', 'Divergencia alcista RSI', min(fuerza, 100))

    # Divergencia bajista RSI
    if max_precio_idx != max_rsi_idx and segmento.loc[max_precio_idx, 'high'] > segmento.loc[max_rsi_idx, 'high']:
        if segmento.loc[max_rsi_idx, 'rsi'] < segmento.loc[max_precio_idx, 'rsi']:
            fuerza = fuerza_base + (segmento['vol_ratio'].iloc[-1] * 10)
            return ('PUT', 'Divergencia bajista RSI', min(fuerza, 100))

    # Divergencia alcista MACD
    if min_precio_idx != min_macd_idx and segmento.loc[min_precio_idx, 'low'] < segmento.loc[min_macd_idx, 'low']:
        if segmento.loc[min_macd_idx, 'macd'] > segmento.loc[min_precio_idx, 'macd']:
            fuerza = fuerza_base + (segmento['vol_ratio'].iloc[-1] * 10)
            return ('CALL', 'Divergencia alcista MACD', min(fuerza, 100))

    # Divergencia bajista MACD
    if max_precio_idx != max_macd_idx and segmento.loc[max_precio_idx, 'high'] > segmento.loc[max_macd_idx, 'high']:
        if segmento.loc[max_macd_idx, 'macd'] < segmento.loc[max_precio_idx, 'macd']:
            fuerza = fuerza_base + (segmento['vol_ratio'].iloc[-1] * 10)
            return ('PUT', 'Divergencia bajista MACD', min(fuerza, 100))

    return None

# =========================
# DETECCIÓN DE RUPTURA FUERTE (continuación)
# =========================
def detectar_ruptura_fuerte(df, ventana=5, umbral_volumen=1.5, umbral_adx=30):
    """
    Detecta ruptura de máximos/mínimos recientes con ADX alto y volumen alto.
    Retorna (direccion, descripcion, fuerza) o None.
    """
    if len(df) < ventana + 1:
        return None
    last = df.iloc[-1]
    prev = df.iloc[-2]

    # Verificar ADX
    if last['adx'] < umbral_adx:
        return None

    # Verificar volumen
    if last['vol_ratio'] < umbral_volumen:
        return None

    # Máximo de las últimas ventana velas (excluyendo la actual)
    max_anterior = df.iloc[-ventana-1:-1]['high'].max()
    min_anterior = df.iloc[-ventana-1:-1]['low'].min()

    # Ruptura alcista: precio actual supera el máximo anterior
    if last['close'] > max_anterior:
        fuerza = 70 + (last['adx'] / 100) * 30
        return ('CALL', 'Ruptura alcista fuerte', min(fuerza, 100))

    # Ruptura bajista: precio actual perfora el mínimo anterior
    if last['close'] < min_anterior:
        fuerza = 70 + (last['adx'] / 100) * 30
        return ('PUT', 'Ruptura bajista fuerte', min(fuerza, 100))

    return None

# =========================
# CALCULAR PUNTUACIÓN DE FUERZA DE UN ACTIVO
# =========================
def calcular_fuerza(df):
    """
    Calcula una puntuación basada en ADX y volumen relativo.
    """
    last = df.iloc[-1]
    fuerza = last['adx'] + (last['vol_ratio'] * 10) if not pd.isna(last['adx']) else 0
    return min(fuerza, 100)

# =========================
# EVALUAR UN ACTIVO (para selección y seguimiento)
# =========================
def evaluar_activo(api, asset):
    """
    Obtiene velas de 5 min, calcula indicadores y devuelve:
        - dirección de señal si hay divergencia o ruptura
        - fuerza del activo (ADX + volumen)
        - precio actual
        - descripción de la señal
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
        fuerza = calcular_fuerza(df)

        # Primero buscar divergencia
        divergencia = detectar_divergencia(df, ventana=3)
        if divergencia:
            direccion, descripcion, fuerza_div = divergencia
            fuerza_final = (fuerza + fuerza_div) / 2
            return {
                'asset': asset,
                'direccion': direccion,
                'descripcion': descripcion,
                'fuerza': fuerza_final,
                'precio': df['close'].iloc[-1],
                'timestamp': datetime.now(ecuador)
            }

        # Si no hay divergencia, buscar ruptura fuerte
        ruptura = detectar_ruptura_fuerte(df, ventana=5)
        if ruptura:
            direccion, descripcion, fuerza_rup = ruptura
            fuerza_final = (fuerza + fuerza_rup) / 2
            return {
                'asset': asset,
                'direccion': direccion,
                'descripcion': descripcion,
                'fuerza': fuerza_final,
                'precio': df['close'].iloc[-1],
                'timestamp': datetime.now(ecuador)
            }

        # Si no hay señal, devolvemos solo la fuerza para selección
        return {
            'asset': asset,
            'fuerza': fuerza,
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
                    activos.append(asset)
        logger.info(f"Se obtuvieron {len(activos)} activos abiertos")
        if not activos:
            logger.warning("Usando lista de activos predeterminada (fallback)")
            return FALLBACK_ACTIVOS
        return activos
    except Exception as e:
        logger.error(f"Error obteniendo activos: {e}")
        return FALLBACK_ACTIVOS

# =========================
# SELECCIONAR LOS N ACTIVOS MÁS FUERTES
# =========================
def seleccionar_activos_fuertes(api, lista_activos, num_activos=2):
    """
    Evalúa todos los activos y devuelve una lista de los `num_activos` con mayor fuerza.
    """
    puntuaciones = []
    for asset in lista_activos:
        res = evaluar_activo(api, asset)
        if res and 'fuerza' in res:
            puntuaciones.append((res['fuerza'], asset))
        time.sleep(0.1)
    puntuaciones.sort(reverse=True)
    return [asset for _, asset in puntuaciones[:num_activos]]

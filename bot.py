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
# DETECCIÓN DE TENDENCIA (para filtrar señales)
# =========================
def detectar_tendencia(df):
    """Retorna la dirección de la tendencia basada en EMA20/50 y ADX."""
    last = df.iloc[-1]
    if last['adx'] < 20:
        return None, 0
    if last['ema20'] > last['ema50']:
        return 'CALL', last['adx']
    elif last['ema20'] < last['ema50']:
        return 'PUT', last['adx']
    return None, 0

# =========================
# CÁLCULO DE FUERZA DEL ACTIVO (para selección)
# =========================
def calcular_fuerza(df):
    """Fuerza basada en ADX + volumen + alineación de tendencia."""
    last = df.iloc[-1]
    fuerza = last['adx'] + (last['vol_ratio'] * 10) if not pd.isna(last['adx']) else 0
    # Bonus por tendencia fuerte (ADX > 25)
    if last['adx'] > 25:
        fuerza += 10
    return min(fuerza, 100)

# =========================
# DETECCIÓN DE DIVERGENCIAS (con volumen)
# =========================
def detectar_divergencia(df, ventana=5, umbral_adx=20):
    """Detecta divergencias con confirmación de volumen."""
    if len(df) < ventana:
        return None
    segmento = df.iloc[-ventana:].copy()
    last = df.iloc[-1]

    # Filtro ADX mínimo
    if last['adx'] < umbral_adx:
        return None

    # Índices de mínimos y máximos
    min_precio_idx = segmento['low'].idxmin()
    max_precio_idx = segmento['high'].idxmax()
    min_rsi_idx = segmento['rsi'].idxmin()
    max_rsi_idx = segmento['rsi'].idxmax()
    min_macd_idx = segmento['macd'].idxmin()
    max_macd_idx = segmento['macd'].idxmax()

    # Función para calcular presión de volumen
    def volumen_confirmacion(direccion):
        # Últimas 3 velas
        ultimas = df.iloc[-3:]
        if direccion == 'CALL':
            # Queremos que las velas alcistas tengan volumen > promedio
            alcistas = ultimas[ultimas['close'] > ultimas['open']]
            if len(alcistas) > 0:
                vol_alcista = alcistas['volume'].mean()
                vol_total = ultimas['volume'].mean()
                if vol_alcista > vol_total * 1.2:
                    return True
        else:  # PUT
            bajistas = ultimas[ultimas['close'] < ultimas['open']]
            if len(bajistas) > 0:
                vol_bajista = bajistas['volume'].mean()
                vol_total = ultimas['volume'].mean()
                if vol_bajista > vol_total * 1.2:
                    return True
        return False

    # Divergencia alcista RSI
    if min_precio_idx < min_rsi_idx and segmento.loc[min_precio_idx, 'low'] < segmento.loc[min_rsi_idx, 'low']:
        if segmento.loc[min_rsi_idx, 'rsi'] > segmento.loc[min_precio_idx, 'rsi']:
            if volumen_confirmacion('CALL'):
                fuerza = 70 + (last['adx'] / 100) * 30
                return ('CALL', 'Divergencia alcista RSI', min(fuerza, 100))

    # Divergencia bajista RSI
    if max_precio_idx > max_rsi_idx and segmento.loc[max_precio_idx, 'high'] > segmento.loc[max_rsi_idx, 'high']:
        if segmento.loc[max_rsi_idx, 'rsi'] < segmento.loc[max_precio_idx, 'rsi']:
            if volumen_confirmacion('PUT'):
                fuerza = 70 + (last['adx'] / 100) * 30
                return ('PUT', 'Divergencia bajista RSI', min(fuerza, 100))

    # Divergencia alcista MACD
    if min_precio_idx < min_macd_idx and segmento.loc[min_precio_idx, 'low'] < segmento.loc[min_macd_idx, 'low']:
        if segmento.loc[min_macd_idx, 'macd'] > segmento.loc[min_precio_idx, 'macd']:
            if volumen_confirmacion('CALL'):
                fuerza = 70 + (last['adx'] / 100) * 30
                return ('CALL', 'Divergencia alcista MACD', min(fuerza, 100))

    # Divergencia bajista MACD
    if max_precio_idx > max_macd_idx and segmento.loc[max_precio_idx, 'high'] > segmento.loc[max_macd_idx, 'high']:
        if segmento.loc[max_macd_idx, 'macd'] < segmento.loc[max_precio_idx, 'macd']:
            if volumen_confirmacion('PUT'):
                fuerza = 70 + (last['adx'] / 100) * 30
                return ('PUT', 'Divergencia bajista MACD', min(fuerza, 100))

    return None

# =========================
# EVALUAR UN ACTIVO (para selección y seguimiento)
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
        fuerza = calcular_fuerza(df)
        tendencia_dir, _ = detectar_tendencia(df)
        divergencia = detectar_divergencia(df)

        # Solo consideramos divergencia si va en la dirección de la tendencia
        if divergencia and tendencia_dir and divergencia[0] == tendencia_dir:
            direccion, descripcion, fuerza_senal = divergencia
            return {
                'asset': asset,
                'direccion': direccion,
                'descripcion': descripcion,
                'fuerza': (fuerza + fuerza_senal) / 2,
                'precio': df['close'].iloc[-1],
                'timestamp': datetime.now(ecuador)
            }
        else:
            # Sin señal, pero devolvemos fuerza para selección
            return {
                'asset': asset,
                'fuerza': fuerza,
                'precio': df['close'].iloc[-1]
            }
    except Exception as e:
        logger.error(f"Error evaluando {asset}: {e}")
        return None

# =========================
# OBTENER ACTIVOS ABIERTOS (con conteo)
# =========================
def obtener_activos_abiertos(api, tipo_mercado="AMBOS"):
    try:
        open_time = api.get_all_open_time()
        activos = []
        otc_count = 0
        real_count = 0
        if 'binary' in open_time:
            for asset, data in open_time['binary'].items():
                if data.get('open', False):
                    if '-OTC' in asset:
                        otc_count += 1
                        if tipo_mercado in ['OTC', 'AMBOS']:
                            activos.append(asset)
                    else:
                        real_count += 1
                        if tipo_mercado in ['REAL', 'AMBOS']:
                            activos.append(asset)
        logger.info(f"Activos disponibles: OTC={otc_count}, REAL={real_count}, total={len(activos)}")
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
# SELECCIONAR LOS N ACTIVOS MÁS FUERTES
# =========================
def seleccionar_activos_fuertes(api, lista_activos, num_activos=3):
    puntuaciones = []
    for asset in lista_activos:
        res = evaluar_activo(api, asset)
        if res and 'fuerza' in res:
            puntuaciones.append((res['fuerza'], asset))
        time.sleep(0.1)
    puntuaciones.sort(reverse=True)
    return [asset for _, asset in puntuaciones[:num_activos]]

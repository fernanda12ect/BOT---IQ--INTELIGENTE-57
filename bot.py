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

    # EMAs para tendencia
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
# DETECCIÓN DE TENDENCIA (a favor de la cual operaremos)
# =========================
def detectar_tendencia(df):
    """Retorna la dirección de la tendencia ('CALL'/'PUT') y su fuerza (ADX) si ADX > 20."""
    if len(df) < 50:
        return None, 0
    last = df.iloc[-1]
    if last['adx'] < 20:
        return None, 0
    if last['ema9'] > last['ema21'] and last['ema21'] > last['ema50']:
        return 'CALL', last['adx']
    elif last['ema9'] < last['ema21'] and last['ema21'] < last['ema50']:
        return 'PUT', last['adx']
    return None, 0

# =========================
# CÁLCULO DE FUERZA DEL ACTIVO (para seleccionar los mejores)
# =========================
def calcular_fuerza(df):
    """Fuerza basada en ADX + volumen + RSI."""
    last = df.iloc[-1]
    fuerza = last['adx'] + (last['vol_ratio'] * 10)
    # Bonus por RSI en zona de continuación (45-55)
    if 45 <= last['rsi'] <= 55:
        fuerza += 10
    return min(fuerza, 100)

# =========================
# DETECCIÓN DE NIVELES (soportes, resistencias, líneas de tendencia)
# =========================
def detectar_niveles_sr(df, ventana=50, num_toques=2):
    """Detecta niveles horizontales (soportes/resistencias) con al menos `num_toques` toques."""
    if len(df) < ventana:
        return []
    df = df.iloc[-ventana:].copy()
    highs = df['high']
    lows = df['low']
    conteo = defaultdict(int)
    for i in range(1, len(df)-1):
        if highs.iloc[i] > highs.iloc[i-1] and highs.iloc[i] > highs.iloc[i+1]:
            conteo[round(highs.iloc[i], 5)] += 1
        if lows.iloc[i] < lows.iloc[i-1] and lows.iloc[i] < lows.iloc[i+1]:
            conteo[round(lows.iloc[i], 5)] += 1
    niveles = []
    precio_actual = df['close'].iloc[-1]
    for precio, cnt in conteo.items():
        if cnt >= num_toques:
            tipo = 'resistencia' if precio > precio_actual else 'soporte'
            niveles.append({'precio': precio, 'tipo': tipo, 'toques': cnt})
    niveles.sort(key=lambda x: abs(x['precio'] - precio_actual))
    return niveles

def detectar_lineas_tendencia(df, ventana=30):
    """Detecta líneas de tendencia alcistas y bajistas con 2 toques."""
    if len(df) < ventana:
        return []
    df = df.iloc[-ventana:].copy()
    indices = np.arange(len(df))
    minimos = df['low'].values
    maximos = df['high'].values

    lineas = []
    # Tendencia alcista: 2 mínimos crecientes
    for i in range(len(minimos)-5):
        for j in range(i+3, len(minimos)):
            if minimos[j] > minimos[i] and (j - i) > 3:
                pendiente = (minimos[j] - minimos[i]) / (j - i)
                intercepto = minimos[i] - pendiente * i
                precio_linea = intercepto + pendiente * (len(df)-1)
                lineas.append({
                    'tipo': 'alcista',
                    'precio': precio_linea,
                    'pendiente': pendiente,
                    'toques': 2
                })
    # Tendencia bajista: 2 máximos decrecientes
    for i in range(len(maximos)-5):
        for j in range(i+3, len(maximos)):
            if maximos[j] < maximos[i] and (j - i) > 3:
                pendiente = (maximos[j] - maximos[i]) / (j - i)
                intercepto = maximos[i] - pendiente * i
                precio_linea = intercepto + pendiente * (len(df)-1)
                lineas.append({
                    'tipo': 'bajista',
                    'precio': precio_linea,
                    'pendiente': pendiente,
                    'toques': 2
                })
    # Ordenar por cercanía al precio actual
    precio_actual = df['close'].iloc[-1]
    for l in lineas:
        l['distancia'] = abs(precio_actual - l['precio'])
    lineas.sort(key=lambda x: x['distancia'])
    return lineas[:3]  # las 3 más cercanas

# =========================
# EVALUAR UN ACTIVO (fuerza + niveles + línea de tendencia)
# =========================
def evaluar_activo(api, asset):
    try:
        candles = api.get_candles(asset, 60, 100, time.time())  # velas de 1 minuto
        if not candles or len(candles) < 50:
            return None
        df = pd.DataFrame(candles)
        for col in ['open', 'max', 'min', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df.dropna(inplace=True)
        if len(df) < 50:
            return None

        df = calcular_indicadores(df)
        tendencia, fuerza_tendencia = detectar_tendencia(df)
        fuerza = calcular_fuerza(df)
        niveles = detectar_niveles_sr(df, ventana=50, num_toques=2)
        lineas = detectar_lineas_tendencia(df, ventana=30)

        # Si no hay tendencia clara, no operamos
        if tendencia is None:
            return {
                'asset': asset,
                'tendencia': None,
                'fuerza': fuerza,
                'niveles': niveles,
                'lineas': lineas,
                'precio': df['close'].iloc[-1]
            }

        return {
            'asset': asset,
            'tendencia': tendencia,
            'fuerza_tendencia': fuerza_tendencia,
            'fuerza': fuerza,
            'niveles': niveles,
            'lineas': lineas,
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
def seleccionar_activos_fuertes(api, lista_activos, num_activos=5):
    puntuaciones = []
    for asset in lista_activos:
        res = evaluar_activo(api, asset)
        if res and res['fuerza'] > 0:
            # Priorizamos los que tienen tendencia clara
            if res['tendencia']:
                puntuaciones.append((res['fuerza'] + res['fuerza_tendencia'], asset, res))
            else:
                puntuaciones.append((res['fuerza'], asset, res))
        time.sleep(0.1)
    puntuaciones.sort(reverse=True)
    return [p[2] for p in puntuaciones[:num_activos]]

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

    # Volumen promedio
    df['vol_avg'] = df['volume'].rolling(20).mean()
    df['vol_ratio'] = df['volume'] / df['vol_avg']

    return df

# =========================
# DETECCIÓN DE SEÑAL PARA LA PRÓXIMA VELA DE 1 MINUTO
# =========================
def evaluar_activo_1min(api, asset, umbral_adx=20):
    """
    Evalúa un activo en timeframe de 1 minuto y determina si la próxima vela será alcista o bajista.
    Retorna un dict con:
        - direccion: 'CALL' o 'PUT'
        - fuerza: valor entre 0 y 100 (basado en volumen y cruce)
        - confirmacion: si hay cruce de EMA y volumen alto
        - alerta: si está cerca de una señal (para avisar con antelación)
    Si no hay señal, retorna None.
    """
    try:
        candles = api.get_candles(asset, 60, 50, time.time())
        if not candles or len(candles) < 30:
            return None
        df = pd.DataFrame(candles)
        for col in ['open', 'max', 'min', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df.dropna(inplace=True)
        if len(df) < 30:
            return None

        df = calcular_indicadores(df)
        last = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else last

        cruce_call = prev['ema9'] <= prev['ema21'] and last['ema9'] > last['ema21']
        cruce_put = prev['ema9'] >= prev['ema21'] and last['ema9'] < last['ema21']
        volumen_alto = last['vol_ratio'] > 1.5
        cuerpo = abs(last['close'] - last['open'])
        rango = last['high'] - last['low']
        vela_fuerte = cuerpo > rango * 0.6
        vela_alcista = last['close'] > last['open']
        vela_bajista = last['close'] < last['open']
        tendencia_fuerte = last['adx'] > umbral_adx

        fuerza = 0
        direccion = None

        if vela_alcista and cruce_call and volumen_alto and vela_fuerte and tendencia_fuerte:
            fuerza = 80 + (last['vol_ratio'] * 5)
            direccion = 'CALL'
        elif vela_bajista and cruce_put and volumen_alto and vela_fuerte and tendencia_fuerte:
            fuerza = 80 + (last['vol_ratio'] * 5)
            direccion = 'PUT'
        elif cruce_call and volumen_alto and tendencia_fuerte:
            fuerza = 60
            direccion = 'CALL'
        elif cruce_put and volumen_alto and tendencia_fuerte:
            fuerza = 60
            direccion = 'PUT'
        else:
            return None

        alerta = False
        if not (cruce_call or cruce_put) and last['vol_ratio'] > 1.2 and last['adx'] > umbral_adx:
            alerta = True

        return {
            'asset': asset,
            'direccion': direccion,
            'fuerza': min(fuerza, 100),
            'confirmacion': (cruce_call or cruce_put) and volumen_alto and vela_fuerte,
            'alerta': alerta,
            'precio': last['close'],
            'timestamp': datetime.now(ecuador)
        }
    except Exception as e:
        logger.error(f"Error evaluando {asset} en 1min: {e}")
        return None

# =========================
# DETECCIÓN DE ZONAS DE OFERTA/DEMANDA (simplificada)
# =========================
def detectar_zonas_od(df, ventana=50):
    if len(df) < ventana:
        return []
    df = df.iloc[-ventana:].copy()
    highs = df['high']
    lows = df['low']
    # Detectar máximos y mínimos locales
    picos = []
    valles = []
    for i in range(2, len(df)-2):
        if highs.iloc[i] > highs.iloc[i-1] and highs.iloc[i] > highs.iloc[i-2] and \
           highs.iloc[i] > highs.iloc[i+1] and highs.iloc[i] > highs.iloc[i+2]:
            picos.append((i, highs.iloc[i]))
        if lows.iloc[i] < lows.iloc[i-1] and lows.iloc[i] < lows.iloc[i-2] and \
           lows.iloc[i] < lows.iloc[i+1] and lows.iloc[i] < lows.iloc[i+2]:
            valles.append((i, lows.iloc[i]))
    # Crear zonas alrededor de esos niveles (con un rango estrecho)
    zonas = []
    for idx, precio in picos:
        zonas.append({'tipo': 'oferta', 'precio': precio, 'fuerza': 3})
    for idx, precio in valles:
        zonas.append({'tipo': 'demanda', 'precio': precio, 'fuerza': 3})
    # Ordenar por cercanía al precio actual
    precio_actual = df['close'].iloc[-1]
    for z in zonas:
        z['distancia'] = abs(precio_actual - z['precio'])
    zonas.sort(key=lambda x: x['distancia'])
    return zonas[:5]

# =========================
# EVALUAR ACTIVO PARA SELECCIÓN (con zonas)
# =========================
def evaluar_activo_seleccion(api, asset, umbral_adx=18):
    try:
        candles = api.get_candles(asset, 60, 100, time.time())
        if not candles or len(candles) < 50:
            return None
        df = pd.DataFrame(candles)
        for col in ['open', 'max', 'min', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df.dropna(inplace=True)
        if len(df) < 50:
            return None

        df = calcular_indicadores(df)
        precio_actual = df['close'].iloc[-1]
        atr_actual = df['atr'].iloc[-1]

        # Zonas de oferta/demanda
        zonas = detectar_zonas_od(df, ventana=50)
        if not zonas:
            return None

        # Coger la zona más cercana
        zona = zonas[0]
        distancia = zona['distancia'] / atr_actual

        # Evaluar dirección con algunas estrategias simples
        last = df.iloc[-1]
        direccion = None
        if last['ema9'] > last['ema21'] and last['adx'] > umbral_adx:
            direccion = 'CALL'
        elif last['ema9'] < last['ema21'] and last['adx'] > umbral_adx:
            direccion = 'PUT'
        else:
            return None

        # Coherencia con zona
        if direccion == 'CALL' and zona['tipo'] != 'demanda':
            return None
        if direccion == 'PUT' and zona['tipo'] != 'oferta':
            return None

        # Puntuación: fuerza de zona + cercanía + ADX
        puntuacion = zona['fuerza'] * 10 + (10 - min(distancia, 10)) + last['adx']

        return {
            'asset': asset,
            'direccion': direccion,
            'puntuacion': puntuacion,
            'zona': zona,
            'distancia': distancia,
            'fuerza_adx': last['adx'],
            'precio': precio_actual
        }
    except Exception as e:
        logger.error(f"Error evaluando {asset} para selección: {e}")
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
# SELECCIONAR EL MEJOR ACTIVO
# =========================
def seleccionar_mejor_activo(api, lista_activos):
    mejores = []
    for asset in lista_activos:
        try:
            res = evaluar_activo_seleccion(api, asset)
            if res:
                mejores.append(res)
            time.sleep(0.1)
        except:
            continue
    if not mejores:
        return None
    mejores.sort(key=lambda x: x['puntuacion'], reverse=True)
    return mejores[0]

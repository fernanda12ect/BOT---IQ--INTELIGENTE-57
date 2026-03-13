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
# INDICADORES BÁSICOS
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

    # ATR para medir volatilidad
    high, low, close = df['high'], df['low'], df['close']
    tr = pd.concat([high - low, abs(high - close.shift()), abs(low - close.shift())], axis=1).max(axis=1)
    df['atr'] = tr.rolling(14).mean()

    # Volumen promedio
    df['vol_avg'] = df['volume'].rolling(20).mean()
    df['vol_ratio'] = df['volume'] / df['vol_avg']

    return df

# =========================
# DETECCIÓN DE SOPORTES/RESISTENCIAS HORIZONTALES
# =========================
def detectar_niveles_sr(df, num_toques=2, ventana=100):
    """
    Detecta niveles horizontales (soportes/resistencias) basados en máximos y mínimos locales.
    Retorna lista de niveles con tipo y precio.
    """
    if len(df) < ventana:
        return []
    df = df.iloc[-ventara:].copy()
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
    # Ordenar por cercanía al precio actual
    niveles.sort(key=lambda x: abs(x['precio'] - precio_actual))
    return niveles

# =========================
# DETECCIÓN DE LÍNEAS DE TENDENCIA
# =========================
def detectar_lineas_tendencia(df, ventana=50):
    """
    Detecta líneas de tendencia alcistas (conectando mínimos) y bajistas (conectando máximos).
    Retorna lista de líneas con tipo y ecuación.
    """
    if len(df) < ventana:
        return []
    df = df.iloc[-ventana:].copy()
    indices = np.arange(len(df))
    minimos = df['low'].values
    maximos = df['high'].values

    lineas = []
    # Tendencia alcista: buscar 2 mínimos crecientes
    for i in range(len(minimos)-5):
        for j in range(i+3, len(minimos)):
            if minimos[j] > minimos[i] and (j - i) > 3:
                pendiente = (minimos[j] - minimos[i]) / (j - i)
                intercepto = minimos[i] - pendiente * i
                # Calcular precio en la línea en el índice actual
                precio_linea = intercepto + pendiente * (len(df)-1)
                lineas.append({
                    'tipo': 'alcista',
                    'pendiente': pendiente,
                    'intercepto': intercepto,
                    'precio_actual': precio_linea,
                    'puntos': (i, j)
                })
    # Tendencia bajista: buscar 2 máximos decrecientes
    for i in range(len(maximos)-5):
        for j in range(i+3, len(maximos)):
            if maximos[j] < maximos[i] and (j - i) > 3:
                pendiente = (maximos[j] - maximos[i]) / (j - i)
                intercepto = maximos[i] - pendiente * i
                precio_linea = intercepto + pendiente * (len(df)-1)
                lineas.append({
                    'tipo': 'bajista',
                    'pendiente': pendiente,
                    'intercepto': intercepto,
                    'precio_actual': precio_linea,
                    'puntos': (i, j)
                })
    # Ordenar por cercanía al precio actual
    precio_actual = df['close'].iloc[-1]
    for l in lineas:
        l['distancia'] = abs(precio_actual - l['precio_actual'])
    lineas.sort(key=lambda x: x['distancia'])
    return lineas[:5]  # devolver las 5 más cercanas

# =========================
# EVALUAR UN ACTIVO (buscar niveles y tendencias cercanas)
# =========================
def evaluar_activo(api, asset, umbral_distancia=0.002):
    """
    Retorna una lista de señales (hasta 2) para el activo:
        - si hay un nivel de soporte/resistencia cerca
        - si hay una línea de tendencia cerca
    Cada señal incluye tipo, dirección, distancia y fuerza.
    """
    try:
        candles = api.get_candles(asset, 300, 100, time.time())  # velas de 5 min
        if not candles or len(candles) < 50:
            return []
        df = pd.DataFrame(candles)
        for col in ['open', 'max', 'min', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df.dropna(inplace=True)
        if len(df) < 50:
            return []
        df = calcular_indicadores(df)
        precio_actual = df['close'].iloc[-1]

        señales = []

        # 1. Buscar niveles S/R cercanos
        niveles = detectar_niveles_sr(df, num_toques=2)
        for nivel in niveles[:2]:  # solo los 2 más cercanos
            distancia = abs(precio_actual - nivel['precio']) / precio_actual
            if distancia <= umbral_distancia:
                # Calcular fuerza basada en volumen y RSI
                fuerza = 50  # base
                if nivel['tipo'] == 'soporte' and df['rsi'].iloc[-1] < 40:
                    fuerza += 20
                if nivel['tipo'] == 'resistencia' and df['rsi'].iloc[-1] > 60:
                    fuerza += 20
                if df['vol_ratio'].iloc[-1] > 1.5:
                    fuerza += 10
                señales.append({
                    'tipo': 'soporte/resistencia',
                    'subtipo': nivel['tipo'],
                    'direccion': 'CALL' if nivel['tipo'] == 'soporte' else 'PUT',
                    'nivel': nivel['precio'],
                    'distancia': distancia * 100,  # en porcentaje
                    'fuerza': min(fuerza, 100)
                })

        # 2. Buscar líneas de tendencia cercanas
        lineas = detectar_lineas_tendencia(df)
        for linea in lineas[:2]:
            distancia = abs(precio_actual - linea['precio_actual']) / precio_actual
            if distancia <= umbral_distancia:
                direccion = 'CALL' if linea['tipo'] == 'alcista' else 'PUT'
                fuerza = 50
                if linea['tipo'] == 'alcista' and df['ema9'].iloc[-1] > df['ema21'].iloc[-1]:
                    fuerza += 20
                if linea['tipo'] == 'bajista' and df['ema9'].iloc[-1] < df['ema21'].iloc[-1]:
                    fuerza += 20
                if df['vol_ratio'].iloc[-1] > 1.5:
                    fuerza += 10
                señales.append({
                    'tipo': 'línea de tendencia',
                    'subtipo': linea['tipo'],
                    'direccion': direccion,
                    'nivel': linea['precio_actual'],
                    'distancia': distancia * 100,
                    'fuerza': min(fuerza, 100)
                })

        return señales
    except Exception as e:
        logger.error(f"Error evaluando {asset}: {e}")
        return []

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
# SELECCIONAR LOS MEJORES ACTIVOS CON SEÑALES (hasta 4)
# =========================
def seleccionar_mejores_senales(api, lista_activos, max_activos=4):
    """
    Analiza todos los activos y devuelve una lista de hasta `max_activos` señales,
    ordenadas por menor distancia al nivel.
    """
    todas_senales = []
    for asset in lista_activos:
        try:
            senales = evaluar_activo(api, asset)
            for s in senales:
                s['asset'] = asset
                todas_senales.append(s)
            time.sleep(0.1)
        except:
            continue
    # Ordenar por distancia (menor primero)
    todas_senales.sort(key=lambda x: x['distancia'])
    return todas_senales[:max_activos]

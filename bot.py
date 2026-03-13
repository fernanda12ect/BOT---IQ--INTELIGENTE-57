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

# Lista de activos OTC y reales (fallback si la API falla)
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
    # Solo necesitamos highs y lows para los niveles
    return df

# =========================
# DETECCIÓN DE SOPORTES Y RESISTENCIAS HORIZONTALES
# =========================
def detectar_soportes_resistencias(df, num_toques=2, ventana=100):
    """
    Detecta niveles horizontales con al menos `num_toques` toques.
    Retorna lista de dicts: {'precio': float, 'tipo': 'soporte'/'resistencia', 'toques': int}
    """
    if len(df) < ventana:
        return []
    df = df.iloc[-ventana:].copy()
    highs = df['high']
    lows = df['low']
    conteo = defaultdict(int)
    # Identificar máximos y mínimos locales
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
# DETECCIÓN DE LÍNEAS DE TENDENCIA (2 toques)
# =========================
def detectar_lineas_tendencia(df, ventana=50):
    """
    Encuentra posibles líneas de tendencia con 2 toques.
    Retorna lista de dicts: {'tipo': 'alcista'/'bajista', 'pendiente': float, 'intercepto': float, 'toques': 2}
    """
    if len(df) < ventana:
        return []
    df = df.iloc[-ventana:].copy()
    minimos = df['low'].values
    maximos = df['high'].values
    indices = np.arange(len(df))
    lineas = []
    # Tendencia alcista: 2 mínimos crecientes
    for i in range(len(minimos)-10):
        for j in range(i+5, len(minimos)):
            if minimos[j] > minimos[i]:
                pendiente = (minimos[j] - minimos[i]) / (j - i)
                lineas.append({
                    'tipo': 'alcista',
                    'pendiente': pendiente,
                    'intercepto': minimos[i] - pendiente * i,
                    'toques': 2,
                    'puntos': (i, j)
                })
    # Tendencia bajista: 2 máximos decrecientes
    for i in range(len(maximos)-10):
        for j in range(i+5, len(maximos)):
            if maximos[j] < maximos[i]:
                pendiente = (maximos[j] - maximos[i]) / (j - i)
                lineas.append({
                    'tipo': 'bajista',
                    'pendiente': pendiente,
                    'intercepto': maximos[i] - pendiente * i,
                    'toques': 2,
                    'puntos': (i, j)
                })
    # Devolver las líneas más recientes (ordenadas por índice)
    lineas.sort(key=lambda x: x['puntos'][1], reverse=True)
    return lineas[:5]

# =========================
# EVALUAR UN ACTIVO (para determinar si está cerca de algún nivel)
# =========================
def evaluar_activo(api, asset):
    """
    Obtiene velas de 1 minuto y detecta niveles.
    Retorna un dict con:
        - asset
        - niveles: lista de niveles horizontales cercanos
        - lineas: lista de líneas de tendencia cercanas
        - precio_actual
    """
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
        precio_actual = df['close'].iloc[-1]
        niveles = detectar_soportes_resistencias(df, num_toques=2, ventana=100)
        lineas = detectar_lineas_tendencia(df, ventana=50)
        # Calcular distancia a los niveles (para ordenar)
        for nivel in niveles:
            nivel['distancia'] = abs(precio_actual - nivel['precio']) / precio_actual
        # Para líneas de tendencia, calcular precio en la línea en el índice actual
        idx_actual = len(df) - 1
        for linea in lineas:
            precio_linea = linea['intercepto'] + linea['pendiente'] * idx_actual
            linea['precio'] = precio_linea
            linea['distancia'] = abs(precio_actual - precio_linea) / precio_actual
        return {
            'asset': asset,
            'precio': precio_actual,
            'niveles': niveles,
            'lineas': lineas
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
            return FALLBACK_ACTIVOS
        return activos
    except Exception as e:
        logger.error(f"Error obteniendo activos: {e}")
        return FALLBACK_ACTIVOS

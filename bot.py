import pandas as pd
import numpy as np
import time
import logging
from datetime import datetime, timedelta
import pytz

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Zona horaria de Ecuador
ecuador = pytz.timezone("America/Guayaquil")

# Lista de activos OTC (fallback)
OTC_ASSETS = [
    "EURUSD-OTC", "GBPUSD-OTC", "AUDUSD-OTC", "USDJPY-OTC",
    "USDCHF-OTC", "NZDUSD-OTC", "USDCAD-OTC", "GBPJPY-OTC",
    "EURJPY-OTC", "AUDCAD-OTC", "AUDJPY-OTC", "EURGBP-OTC",
    "USDINR-OTC", "USDHKD-OTC", "USDSGD-OTC", "USDZAR-OTC",
    "EURCHF-OTC", "GBPCHF-OTC", "CADCHF-OTC", "AUDNZD-OTC"
]

# =========================
# OBTENER ACTIVOS ABIERTOS (solo OTC)
# =========================
def obtener_activos_otc(api):
    try:
        open_time = api.get_all_open_time()
        activos = []
        if 'binary' in open_time:
            for asset, data in open_time['binary'].items():
                if data.get('open', False) and '-OTC' in asset:
                    activos.append(asset)
        logger.info(f"Se obtuvieron {len(activos)} activos OTC abiertos")
        if not activos:
            logger.warning("Usando lista de activos OTC predeterminada (fallback)")
            return OTC_ASSETS
        return activos
    except Exception as e:
        logger.error(f"Error obteniendo activos OTC: {e}")
        return OTC_ASSETS

# =========================
# FUNCIONES PARA OBTENER VELAS Y PRECIOS EN TIEMPO REAL
# =========================
def obtener_velas_1min(api, asset, n=50):
    try:
        candles = api.get_candles(asset, 60, n, time.time())
        if not candles or len(candles) < n:
            return None
        df = pd.DataFrame(candles)
        for col in ['open', 'max', 'min', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df.dropna(inplace=True)
        return df
    except Exception as e:
        logger.error(f"Error obteniendo velas de {asset}: {e}")
        return None

def obtener_precio_actual(api, asset):
    try:
        # Usar get_candles con 1 vela para obtener el último precio
        candles = api.get_candles(asset, 60, 1, time.time())
        if candles and len(candles) > 0:
            return candles[0]['close']
        else:
            return None
    except:
        return None

# =========================
# INDICADORES BÁSICOS
# =========================
def calcular_indicadores(df):
    df = df.copy()
    df.rename(columns={'max': 'high', 'min': 'low'}, inplace=True)

    # EMAs cortas
    df['ema2'] = df['close'].ewm(span=2, adjust=False).mean()
    df['ema5'] = df['close'].ewm(span=5, adjust=False).mean()
    df['ema9'] = df['close'].ewm(span=9, adjust=False).mean()
    df['ema21'] = df['close'].ewm(span=21, adjust=False).mean()

    # RSI 9
    delta = df['close'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(9).mean()
    avg_loss = loss.rolling(9).mean()
    rs = avg_gain / avg_loss
    df['rsi9'] = 100 - (100 / (1 + rs))

    # Volumen
    df['vol_avg'] = df['volume'].rolling(20).mean()
    df['vol_ratio'] = df['volume'] / df['vol_avg']

    return df

# =========================
# ESTRATEGIA 1: ACTIVOS MODERADAMENTE VOLÁTILES
# =========================
def estrategia_volatil(df, precio_actual):
    """Basada en EMAs 2/5 y RSI9, con niveles de soporte/resistencia de últimas 5 velas."""
    if len(df) < 6:
        return None
    # Micro niveles: máximos y mínimos de las últimas 5 velas
    ultimas5 = df.iloc[-5:]
    soporte = ultimas5['low'].min()
    resistencia = ultimas5['high'].max()

    # Distancia al nivel
    dist_soporte = abs(precio_actual - soporte) / precio_actual
    dist_resistencia = abs(precio_actual - resistencia) / precio_actual
    umbral = 0.001  # 0.1% (para 1 minuto es razonable)

    # Tendencia EMAs
    ema2 = df['ema2'].iloc[-1]
    ema5 = df['ema5'].iloc[-1]
    rsi = df['rsi9'].iloc[-1]

    # Compra: cerca de soporte, EMAs alcistas (ema2 > ema5), RSI < 40 y subiendo
    if dist_soporte < umbral and ema2 > ema5 and rsi < 40:
        # Verificar si la vela actual está mostrando fuerza (cuerpo grande)
        ultima = df.iloc[-1]
        cuerpo = abs(ultima['close'] - ultima['open'])
        rango = ultima['high'] - ultima['low']
        fuerza_vela = cuerpo > rango * 0.6
        if fuerza_vela:
            return ('CALL', f"Soporte micro + EMA2>5, RSI={rsi:.1f}")

    # Venta: cerca de resistencia, EMAs bajistas (ema2 < ema5), RSI > 60 y bajando
    if dist_resistencia < umbral and ema2 < ema5 and rsi > 60:
        ultima = df.iloc[-1]
        cuerpo = abs(ultima['close'] - ultima['open'])
        rango = ultima['high'] - ultima['low']
        fuerza_vela = cuerpo > rango * 0.6
        if fuerza_vela:
            return ('PUT', f"Resistencia micro + EMA2<5, RSI={rsi:.1f}")

    return None

# =========================
# ESTRATEGIA 2: ACTIVOS TRANQUILOS
# =========================
def estrategia_tranquilo(df, precio_actual):
    """Basada en niveles de soporte/resistencia de las últimas 15 velas y estructura de vela."""
    if len(df) < 16:
        return None
    # Niveles de 15 velas
    ultimas15 = df.iloc[-15:]
    soporte = ultimas15['low'].min()
    resistencia = ultimas15['high'].max()
    dist_soporte = abs(precio_actual - soporte) / precio_actual
    dist_resistencia = abs(precio_actual - resistencia) / precio_actual
    umbral = 0.001

    # Determinar tendencia de las últimas 3 velas
    ultimas3 = df.iloc[-3:]
    tendencia_alcista = all(ultimas3['close'] > ultimas3['open'])
    tendencia_bajista = all(ultimas3['close'] < ultimas3['open'])

    # Vela actual (última)
    ultima = df.iloc[-1]
    cuerpo = abs(ultima['close'] - ultima['open'])
    rango = ultima['high'] - ultima['low']
    fuerza = cuerpo > rango * 0.6

    # Compra: cerca de soporte, tendencia alcista reciente, vela actual alcista con fuerza
    if dist_soporte < umbral and tendencia_alcista and ultima['close'] > ultima['open'] and fuerza:
        return ('CALL', f"Soporte 15 velas + tendencia alcista + vela fuerte")
    # Venta: cerca de resistencia, tendencia bajista reciente, vela actual bajista con fuerza
    if dist_resistencia < umbral and tendencia_bajista and ultima['close'] < ultima['open'] and fuerza:
        return ('PUT', f"Resistencia 15 velas + tendencia bajista + vela fuerte")
    return None

# =========================
# ANÁLISIS DE UN ACTIVO (puntuación para elegir el mejor)
# =========================
def analizar_activo(api, asset):
    """
    Obtiene datos del activo, calcula indicadores y evalúa las dos estrategias.
    Retorna un dict con:
        - asset: nombre
        - senal: ('CALL'/'PUT', descripción) o None
        - puntuacion: fuerza de la señal (para comparar)
        - precio_actual
    """
    try:
        df = obtener_velas_1min(api, asset, n=50)
        if df is None or len(df) < 50:
            return None
        df = calcular_indicadores(df)
        precio_actual = df['close'].iloc[-1]

        # Intentar primero estrategia volátil
        res = estrategia_volatil(df, precio_actual)
        if res:
            direccion, desc = res
            return {
                'asset': asset,
                'senal': (direccion, desc),
                'puntuacion': 100,  # alta prioridad
                'precio': precio_actual
            }
        # Si no, intentar estrategia tranquilo
        res = estrategia_tranquilo(df, precio_actual)
        if res:
            direccion, desc = res
            return {
                'asset': asset,
                'senal': (direccion, desc),
                'puntuacion': 80,
                'precio': precio_actual
            }
        # Si ninguna, devolver sin señal
        return None
    except Exception as e:
        logger.error(f"Error analizando {asset}: {e}")
        return None

# =========================
# SELECCIONAR LA MEJOR SEÑAL ENTRE TODOS LOS ACTIVOS OTC
# =========================
def seleccionar_mejor_senal(api, lista_activos):
    mejor = None
    mejor_puntuacion = -1
    for asset in lista_activos:
        res = analizar_activo(api, asset)
        if res and res['puntuacion'] > mejor_puntuacion:
            mejor_puntuacion = res['puntuacion']
            mejor = res
        time.sleep(0.05)  # pequeña pausa para no saturar
    return mejor

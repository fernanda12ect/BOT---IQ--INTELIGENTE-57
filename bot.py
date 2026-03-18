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

    # Bollinger Bands
    df['bb_ma'] = df['close'].rolling(20).mean()
    df['bb_std'] = df['close'].rolling(20).std()
    df['bb_upper'] = df['bb_ma'] + 2 * df['bb_std']
    df['bb_lower'] = df['bb_ma'] - 2 * df['bb_std']

    # Volumen promedio
    df['vol_avg'] = df['volume'].rolling(20).mean()
    df['vol_ratio'] = df['volume'] / df['vol_avg']

    return df

# =========================
# DETECCIÓN DE NIVELES (SOPORTE/RESISTENCIA + BOX)
# =========================
def detectar_niveles_sr(df, num_toques=2, ventana=100):
    """
    Detecta niveles horizontales (soportes/resistencias) basados en máximos y mínimos locales.
    """
    if len(df) < ventana:
        return []
    df = df.iloc[-ventana:].copy()
    highs = df['high']
    lows = df['low']
    conteo = {}
    for i in range(1, len(df)-1):
        if highs.iloc[i] > highs.iloc[i-1] and highs.iloc[i] > highs.iloc[i+1]:
            precio = round(highs.iloc[i], 5)
            conteo[precio] = conteo.get(precio, 0) + 1
        if lows.iloc[i] < lows.iloc[i-1] and lows.iloc[i] < lows.iloc[i+1]:
            precio = round(lows.iloc[i], 5)
            conteo[precio] = conteo.get(precio, 0) + 1
    niveles = []
    precio_actual = df['close'].iloc[-1]
    for precio, cnt in conteo.items():
        if cnt >= num_toques:
            tipo = 'resistencia' if precio > precio_actual else 'soporte'
            niveles.append({'precio': precio, 'tipo': tipo, 'toques': cnt})
    # Ordenar por cercanía
    niveles.sort(key=lambda x: abs(x['precio'] - precio_actual))
    return niveles

# =========================
# ESTRATEGIA 1: CRUCE DE EMAs
# =========================
def estrategia_cruce_emas(df):
    """
    EMA12 cruza EMA26, precio fuera de Bollinger, RSI coherente.
    """
    if len(df) < 2:
        return None
    last = df.iloc[-1]
    prev = df.iloc[-2]

    # Cruce alcista
    if prev['ema12'] <= prev['ema26'] and last['ema12'] > last['ema26']:
        if last['close'] > last['bb_upper'] or last['close'] < last['bb_lower']:
            return None  # fuera de BB no es ideal para cruce
        if last['rsi'] < 70 and last['rsi'] > 30:
            return 'CALL', 'Cruce EMAs Alcista'
    # Cruce bajista
    if prev['ema12'] >= prev['ema26'] and last['ema12'] < last['ema26']:
        if last['close'] > last['bb_upper'] or last['close'] < last['bb_lower']:
            return None
        if last['rsi'] < 70 and last['rsi'] > 30:
            return 'PUT', 'Cruce EMAs Bajista'
    return None

# =========================
# ESTRATEGIA 2: DIVERGENCIAS (RSI o MACD)
# =========================
def estrategia_divergencias(df):
    """
    Divergencia alcista: precio hace mínimo más bajo, RSI hace mínimo más alto.
    Divergencia bajista: precio hace máximo más alto, RSI hace máximo más bajo.
    Requiere ADX > 25 para confirmar fuerza.
    """
    if len(df) < 5:
        return None
    last = df.iloc[-1]
    if last['adx'] < 25:
        return None

    # Tomar últimas 5 velas para buscar divergencias
    segmento = df.iloc[-5:]
    min_precio_idx = segmento['low'].idxmin()
    max_precio_idx = segmento['high'].idxmax()
    min_rsi_idx = segmento['rsi'].idxmin()
    max_rsi_idx = segmento['rsi'].idxmax()

    # Divergencia alcista
    if min_precio_idx < min_rsi_idx and segmento.loc[min_precio_idx, 'low'] < segmento.loc[min_rsi_idx, 'low']:
        if segmento.loc[min_rsi_idx, 'rsi'] > segmento.loc[min_precio_idx, 'rsi']:
            return 'CALL', 'Divergencia alcista RSI'

    # Divergencia bajista
    if max_precio_idx > max_rsi_idx and segmento.loc[max_precio_idx, 'high'] > segmento.loc[max_rsi_idx, 'high']:
        if segmento.loc[max_rsi_idx, 'rsi'] < segmento.loc[max_precio_idx, 'rsi']:
            return 'PUT', 'Divergencia bajista RSI'

    # También podemos buscar divergencias con MACD
    min_macd_idx = segmento['macd'].idxmin()
    max_macd_idx = segmento['macd'].idxmax()
    if min_precio_idx < min_macd_idx and segmento.loc[min_precio_idx, 'low'] < segmento.loc[min_macd_idx, 'low']:
        if segmento.loc[min_macd_idx, 'macd'] > segmento.loc[min_precio_idx, 'macd']:
            return 'CALL', 'Divergencia alcista MACD'
    if max_precio_idx > max_macd_idx and segmento.loc[max_precio_idx, 'high'] > segmento.loc[max_macd_idx, 'high']:
        if segmento.loc[max_macd_idx, 'macd'] < segmento.loc[max_precio_idx, 'macd']:
            return 'PUT', 'Divergencia bajista MACD'

    return None

# =========================
# ESTRATEGIA 3: SOPORTE/RESISTENCIA + BOX
# =========================
def estrategia_sr_box(df, umbral_distancia=0.001):
    """
    Busca niveles de soporte/resistencia cercanos y verifica si el precio está reaccionando.
    """
    niveles = detectar_niveles_sr(df, num_toques=2)
    if not niveles:
        return None
    precio_actual = df['close'].iloc[-1]
    nivel_cercano = niveles[0]
    distancia = abs(precio_actual - nivel_cercano['precio']) / precio_actual
    if distancia > umbral_distancia:
        return None

    # Verificar EMA20 para tendencia general
    if nivel_cercano['tipo'] == 'soporte' and precio_actual > df['ema20'].iloc[-1]:
        # Rebote en soporte con tendencia alcista
        return 'CALL', f'Soporte + EMA20'
    if nivel_cercano['tipo'] == 'resistencia' and precio_actual < df['ema20'].iloc[-1]:
        # Rechazo en resistencia con tendencia bajista
        return 'PUT', f'Resistencia + EMA20'

    # Si no hay alineación con EMA, pero el nivel es fuerte, igual puede ser señal
    if nivel_cercano['toques'] >= 3:
        if nivel_cercano['tipo'] == 'soporte':
            return 'CALL', f'Soporte fuerte ({nivel_cercano["toques"]} toques)'
        else:
            return 'PUT', f'Resistencia fuerte ({nivel_cercano["toques"]} toques)'

    return None

# Lista de estrategias (nombre, función)
ESTRATEGIAS = [
    ("Cruce EMAs", estrategia_cruce_emas),
    ("Divergencias", estrategia_divergencias),
    ("Soporte/Resistencia", estrategia_sr_box)
]

# =========================
# EVALUAR UN ACTIVO (buscar señales de todas las estrategias)
# =========================
def evaluar_activo(api, asset):
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
        señales = []
        for nombre, funcion in ESTRATEGIAS:
            try:
                res = funcion(df)
                if res:
                    direccion, descripcion = res
                    señales.append({
                        'estrategia': nombre,
                        'direccion': direccion,
                        'descripcion': descripcion,
                        'fuerza': 70,  # valor base, se podría calcular
                        'precio': df['close'].iloc[-1]
                    })
            except Exception as e:
                logger.error(f"Error en {nombre} para {asset}: {e}")
                continue
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
# SELECCIONAR SEÑALES (hasta 20 por ciclo, con prioridad a coincidencias)
# =========================
def buscar_senales(api, lista_activos, max_activos=20):
    """
    Analiza hasta max_activos y devuelve una lista de señales, priorizando aquellas
    donde más estrategias coinciden.
    """
    resultados = []
    for asset in lista_activos[:max_activos]:
        señales = evaluar_activo(api, asset)
        if señales:
            # Contar cuántas estrategias dan la misma dirección
            calls = sum(1 for s in señales if s['direccion'] == 'CALL')
            puts = sum(1 for s in señales if s['direccion'] == 'PUT')
            if calls > puts:
                direccion = 'CALL'
                fuerza = calls * 20  # 20 puntos por estrategia
            elif puts > calls:
                direccion = 'PUT'
                fuerza = puts * 20
            else:
                continue  # empate, no señal clara
            # Usamos la primera señal como representativa (o podríamos guardar todas)
            primera = señales[0]
            resultados.append({
                'asset': asset,
                'direccion': direccion,
                'estrategias': [s['estrategia'] for s in señales],
                'fuerza': fuerza,
                'descripcion': primera['descripcion'],
                'precio': primera['precio']
            })
        time.sleep(0.1)
    # Ordenar por fuerza (más estrategias primero)
    resultados.sort(key=lambda x: x['fuerza'], reverse=True)
    return resultados

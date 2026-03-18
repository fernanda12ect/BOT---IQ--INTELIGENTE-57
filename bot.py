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
# FUNCIONES AUXILIARES PARA OBTENER VELAS
# =========================
def obtener_velas_5min(api, asset, n=100):
    try:
        candles = api.get_candles(asset, 300, n, time.time())
        if not candles or len(candles) < n:
            return None
        df = pd.DataFrame(candles)
        for col in ['open', 'max', 'min', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df.dropna(inplace=True)
        return df
    except Exception as e:
        logger.error(f"Error obteniendo velas 5min de {asset}: {e}")
        return None

def obtener_velas_1min(api, asset, n=100):
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
        logger.error(f"Error obteniendo velas 1min de {asset}: {e}")
        return None

# =========================
# DETECCIÓN DE NIVELES (SOPORTE/RESISTENCIA)
# =========================
def detectar_niveles_sr(df, num_toques=2, ventana=100):
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
    niveles.sort(key=lambda x: abs(x['precio'] - precio_actual))
    return niveles

# =========================
# DETECCIÓN DE LÍNEAS DE TENDENCIA
# =========================
def detectar_lineas_tendencia(df, ventana=50):
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
                    'pendiente': pendiente,
                    'intercepto': intercepto,
                    'precio_actual': precio_linea,
                    'puntos': (i, j)
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
    return lineas[:5]

# =========================
# ESTRATEGIA 1: DIVERGENCIAS (5 min)
# =========================
def estrategia_divergencias(df):
    if len(df) < 5:
        return None
    last = df.iloc[-1]
    if last['adx'] < 25:
        return None

    segmento = df.iloc[-5:]
    min_precio_idx = segmento['low'].idxmin()
    max_precio_idx = segmento['high'].idxmax()
    min_rsi_idx = segmento['rsi'].idxmin()
    max_rsi_idx = segmento['rsi'].idxmax()
    min_macd_idx = segmento['macd'].idxmin()
    max_macd_idx = segmento['macd'].idxmax()

    # Divergencia alcista RSI
    if min_precio_idx < min_rsi_idx and segmento.loc[min_precio_idx, 'low'] < segmento.loc[min_rsi_idx, 'low']:
        if segmento.loc[min_rsi_idx, 'rsi'] > segmento.loc[min_precio_idx, 'rsi']:
            return ('CALL', 'Divergencia alcista RSI')
    # Divergencia bajista RSI
    if max_precio_idx > max_rsi_idx and segmento.loc[max_precio_idx, 'high'] > segmento.loc[max_rsi_idx, 'high']:
        if segmento.loc[max_rsi_idx, 'rsi'] < segmento.loc[max_precio_idx, 'rsi']:
            return ('PUT', 'Divergencia bajista RSI')
    # Divergencia alcista MACD
    if min_precio_idx < min_macd_idx and segmento.loc[min_precio_idx, 'low'] < segmento.loc[min_macd_idx, 'low']:
        if segmento.loc[min_macd_idx, 'macd'] > segmento.loc[min_precio_idx, 'macd']:
            return ('CALL', 'Divergencia alcista MACD')
    # Divergencia bajista MACD
    if max_precio_idx > max_macd_idx and segmento.loc[max_precio_idx, 'high'] > segmento.loc[max_macd_idx, 'high']:
        if segmento.loc[max_macd_idx, 'macd'] < segmento.loc[max_precio_idx, 'macd']:
            return ('PUT', 'Divergencia bajista MACD')
    return None

# =========================
# ESTRATEGIA 2: CRUCE DE EMAs (5 min)
# =========================
def estrategia_cruce_emas(df):
    if len(df) < 2:
        return None
    last = df.iloc[-1]
    prev = df.iloc[-2]

    if prev['ema12'] <= prev['ema26'] and last['ema12'] > last['ema26']:
        if last['close'] > last['bb_upper'] or last['close'] < last['bb_lower']:
            return None
        if 30 <= last['rsi'] <= 70:
            return ('CALL', 'Cruce EMAs Alcista')
    if prev['ema12'] >= prev['ema26'] and last['ema12'] < last['ema26']:
        if last['close'] > last['bb_upper'] or last['close'] < last['bb_lower']:
            return None
        if 30 <= last['rsi'] <= 70:
            return ('PUT', 'Cruce EMAs Bajista')
    return None

# =========================
# ESTRATEGIA 3: SOPORTE/RESISTENCIA + LÍNEAS DE TENDENCIA (1 min)
# =========================
def estrategia_sr_tendencia_1min(api, asset, umbral_distancia=0.001):
    df = obtener_velas_1min(api, asset, n=50)
    if df is None or len(df) < 30:
        return None
    df = calcular_indicadores(df)
    precio_actual = df['close'].iloc[-1]
    atr = df['atr'].iloc[-1]

    # Filtro de volatilidad: ATR no debe ser >0.5% del precio
    if atr / precio_actual > 0.005:
        return None

    # Niveles S/R en últimas 20 velas con 2 toques
    niveles = detectar_niveles_sr(df, num_toques=2, ventana=20)
    # Líneas de tendencia en últimas 15 velas
    lineas = detectar_lineas_tendencia(df, ventana=15)

    mejor_distancia = float('inf')
    tipo = None
    nivel_precio = None
    descripcion = ""

    for n in niveles:
        d = abs(precio_actual - n['precio']) / precio_actual
        if d < mejor_distancia and d <= umbral_distancia:
            mejor_distancia = d
            tipo = n['tipo']
            nivel_precio = n['precio']
            descripcion = f"{tipo} con {n['toques']} toques"

    for l in lineas:
        d = abs(precio_actual - l['precio_actual']) / precio_actual
        if d < mejor_distancia and d <= umbral_distancia:
            mejor_distancia = d
            tipo = l['tipo']
            nivel_precio = l['precio_actual']
            descripcion = f"Línea {tipo}"

    if tipo is None:
        return None

    # Determinar dirección esperada
    if tipo in ('soporte', 'alcista'):
        direccion_esperada = 'CALL'
    else:
        direccion_esperada = 'PUT'

    # Verificar patrón de vela de rebote en la última vela
    ultima = df.iloc[-1]
    cuerpo = abs(ultima['close'] - ultima['open'])
    rango = ultima['high'] - ultima['low']

    if direccion_esperada == 'CALL':
        mecha_inf = min(ultima['open'], ultima['close']) - ultima['low']
        if mecha_inf > 2 * cuerpo and cuerpo < rango * 0.3:
            pass  # OK
        else:
            return None
    else:
        mecha_sup = ultima['high'] - max(ultima['open'], ultima['close'])
        if mecha_sup > 2 * cuerpo and cuerpo < rango * 0.3:
            pass
        else:
            return None

    # Todo OK, devolvemos la señal
    return {
        'direccion': direccion_esperada,
        'descripcion': descripcion,
        'nivel': nivel_precio,
        'distancia': mejor_distancia,
        'fuerza': 70,  # valor base
        'estrategia': 'Soporte/Resistencia + Líneas',
        'vencimiento': 1  # minutos
    }

# =========================
# EVALUAR UN ACTIVO (buscar señales de todas las estrategias)
# =========================
def evaluar_activo(api, asset, activar_estrategia_1min=True):
    señales = []

    # Estrategias de 5 min
    df5 = obtener_velas_5min(api, asset, n=100)
    if df5 is not None and len(df5) >= 50:
        df5 = calcular_indicadores(df5)
        res1 = estrategia_divergencias(df5)
        if res1:
            direc, desc = res1
            señales.append({
                'direccion': direc,
                'descripcion': desc,
                'fuerza': 80,  # ponderación
                'estrategia': 'Divergencias',
                'vencimiento': 5
            })
        res2 = estrategia_cruce_emas(df5)
        if res2:
            direc, desc = res2
            señales.append({
                'direccion': direc,
                'descripcion': desc,
                'fuerza': 70,
                'estrategia': 'Cruce EMAs',
                'vencimiento': 5
            })

    # Estrategia de 1 min (si está activada)
    if activar_estrategia_1min:
        res3 = estrategia_sr_tendencia_1min(api, asset)
        if res3:
            señales.append(res3)

    return señales

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
# SELECCIONAR LA MEJOR SEÑAL DE UN LOTE
# =========================
def buscar_mejor_senal(api, lista_activos, activar_estrategia_1min=True):
    mejor_senal = None
    mejor_fuerza = -1
    for asset in lista_activos:
        señales = evaluar_activo(api, asset, activar_estrategia_1min)
        for s in señales:
            # Asignamos una fuerza combinada (podemos usar la fuerza base o ajustar)
            fuerza = s.get('fuerza', 50)
            # Priorizar señales de 1 minuto ligeramente
            if s['vencimiento'] == 1:
                fuerza += 5
            if fuerza > mejor_fuerza:
                mejor_fuerza = fuerza
                mejor_senal = s
                mejor_senal['asset'] = asset
        time.sleep(0.1)  # pausa entre activos
    return mejor_senal

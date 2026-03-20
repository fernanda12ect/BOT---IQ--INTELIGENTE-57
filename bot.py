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

    # MACD
    df['ema12'] = df['close'].ewm(span=12, adjust=False).mean()
    df['ema26'] = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = df['ema12'] - df['ema26']
    df['signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    df['hist'] = df['macd'] - df['signal']

    # Volumen promedio
    df['vol_avg'] = df['volume'].rolling(20).mean()
    df['vol_ratio'] = df['volume'] / df['vol_avg']

    return df

# =========================
# DETECCIÓN DE DIVERGENCIAS (más flexible)
# =========================
def detectar_divergencia(df, ventana=8, umbral_adx=20):
    """
    Detecta divergencias alcistas/bajistas en las últimas `ventana` velas.
    Requiere ADX > umbral_adx.
    Retorna (direccion, descripcion, fuerza) o None.
    """
    if len(df) < ventana:
        return None
    last = df.iloc[-1]
    if last['adx'] < umbral_adx:
        return None

    segmento = df.iloc[-ventana:].copy()
    # Precios e indicadores
    precio = segmento['close'].values
    rsi = segmento['rsi'].values
    macd = segmento['macd'].values

    # Buscar mínimos y máximos locales en el segmento
    def encontrar_picos(vals):
        picos = []
        for i in range(1, len(vals)-1):
            if vals[i] > vals[i-1] and vals[i] > vals[i+1]:
                picos.append((i, vals[i]))
        return picos
    def encontrar_valles(vals):
        valles = []
        for i in range(1, len(vals)-1):
            if vals[i] < vals[i-1] and vals[i] < vals[i+1]:
                valles.append((i, vals[i]))
        return valles

    # Divergencia alcista: precio hace lower low, RSI o MACD hace higher low
    valles_precio = encontrar_valles(precio)
    valles_rsi = encontrar_valles(rsi)
    valles_macd = encontrar_valles(macd)

    for idx_p, val_p in valles_precio:
        # Buscar valles posteriores en RSI/MACD que sean más altos
        for idx_r, val_r in valles_rsi:
            if idx_r > idx_p and val_r > val_p:
                # También puede ser que el valle de precio sea más bajo que el valle de RSI
                return ('CALL', f'Divergencia alcista RSI (precio {val_p:.5f}, RSI {val_r:.1f})', 75)

        for idx_m, val_m in valles_macd:
            if idx_m > idx_p and val_m > val_p:
                return ('CALL', f'Divergencia alcista MACD (precio {val_p:.5f}, MACD {val_m:.3f})', 75)

    # Divergencia bajista: precio hace higher high, RSI o MACD hace lower high
    picos_precio = encontrar_picos(precio)
    picos_rsi = encontrar_picos(rsi)
    picos_macd = encontrar_picos(macd)

    for idx_p, val_p in picos_precio:
        for idx_r, val_r in picos_rsi:
            if idx_r > idx_p and val_r < val_p:
                return ('PUT', f'Divergencia bajista RSI (precio {val_p:.5f}, RSI {val_r:.1f})', 75)
        for idx_m, val_m in picos_macd:
            if idx_m > idx_p and val_m < val_p:
                return ('PUT', f'Divergencia bajista MACD (precio {val_p:.5f}, MACD {val_m:.3f})', 75)

    return None

# =========================
# DETECCIÓN DE AGOTAMIENTO DE FUERZA CONTRARIA
# =========================
def agotamiento_fuerza_contraria(df, direccion):
    """
    Analiza las últimas 3 velas para ver si hay debilidad en la dirección contraria.
    Para CALL: ver si las velas bajistas son pequeñas o tienen poco volumen.
    Para PUT: ver si las velas alcistas son pequeñas o tienen poco volumen.
    """
    if len(df) < 3:
        return False
    ultimas = df.iloc[-3:]
    if direccion == 'CALL':
        # Buscar velas bajistas
        bajistas = ultimas[ultimas['close'] < ultimas['open']]
        if len(bajistas) > 0:
            for _, vela in bajistas.iterrows():
                cuerpo = vela['open'] - vela['close']
                rango = vela['high'] - vela['low']
                if cuerpo > rango * 0.3:
                    return False
                if vela['vol_ratio'] > 1.2:
                    return False
        # La última vela debe ser alcista o neutral
        return ultimas.iloc[-1]['close'] >= ultimas.iloc[-1]['open']
    else:
        alcistas = ultimas[ultimas['close'] > ultimas['open']]
        if len(alcistas) > 0:
            for _, vela in alcistas.iterrows():
                cuerpo = vela['close'] - vela['open']
                rango = vela['high'] - vela['low']
                if cuerpo > rango * 0.3:
                    return False
                if vela['vol_ratio'] > 1.2:
                    return False
        return ultimas.iloc[-1]['close'] <= ultimas.iloc[-1]['open']

# =========================
# CALCULAR PUNTUACIÓN DE FUERZA DE UN ACTIVO (ADX + volumen + tendencia)
# =========================
def calcular_fuerza(df):
    """
    Puntuación basada en ADX, volumen relativo, y si las EMAs están alineadas.
    """
    last = df.iloc[-1]
    fuerza = last['adx'] + (last['vol_ratio'] * 10)
    if last['ema9'] > last['ema21']:
        fuerza += 10
    if last['ema21'] > last['ema50']:
        fuerza += 10
    return min(fuerza, 100)

# =========================
# EVALUAR UN ACTIVO (para selección y seguimiento)
# =========================
def evaluar_activo(api, asset):
    """
    Obtiene velas de 5 min, calcula indicadores y devuelve:
        - dirección de señal si hay divergencia (y fuerza)
        - fuerza del activo (ADX + volumen + tendencia)
        - precio actual
        - descripción de la divergencia si existe
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
        divergencia = detectar_divergencia(df, ventana=8, umbral_adx=20)

        if divergencia:
            direccion, descripcion, fuerza_div = divergencia
            # Añadir filtro de agotamiento de fuerza contraria para mayor efectividad
            if not agotamiento_fuerza_contraria(df, direccion):
                # Si no hay agotamiento, no emitimos señal (opcional)
                # Podemos relajar: si el volumen es alto, igual emitimos
                if df['vol_ratio'].iloc[-1] < 1.2:
                    return {'asset': asset, 'fuerza': fuerza}
            # Si pasó, crear señal
            fuerza_final = (fuerza + fuerza_div) / 2
            return {
                'asset': asset,
                'direccion': direccion,
                'descripcion': descripcion,
                'fuerza': fuerza_final,
                'precio': df['close'].iloc[-1],
                'timestamp': datetime.now(ecuador)
            }
        else:
            # Si no hay divergencia, devolvemos solo la fuerza para selección
            return {
                'asset': asset,
                'fuerza': fuerza,
                'precio': df['close'].iloc[-1]
            }
    except Exception as e:
        logger.error(f"Error evaluando {asset}: {e}")
        return None

# =========================
# OBTENER ACTIVOS ABIERTOS (con filtro por mercado)
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
                        if tipo_mercado == 'OTC' or tipo_mercado == 'AMBOS':
                            activos.append(asset)
                    else:
                        real_count += 1
                        if tipo_mercado == 'REAL' or tipo_mercado == 'AMBOS':
                            activos.append(asset)
        logger.info(f"Activos disponibles: {len(activos)} (OTC: {otc_count}, REAL: {real_count})")
        if not activos:
            logger.warning("Usando lista de activos predeterminada (fallback)")
            if tipo_mercado == 'OTC':
                return [a for a in FALLBACK_ACTIVOS if '-OTC' in a]
            elif tipo_mercado == 'REAL':
                return [a for a in FALLBACK_ACTIVOS if '-OTC' not in a]
            else:
                return FALLBACK_ACTIVOS
        return activos, otc_count, real_count
    except Exception as e:
        logger.error(f"Error obteniendo activos: {e}")
        return FALLBACK_ACTIVOS, 0, 0

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

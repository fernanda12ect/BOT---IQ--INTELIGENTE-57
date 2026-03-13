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

# Lista de activos comunes (fallback, aunque idealmente se obtienen de la API)
FALLBACK_ACTIVOS = [
    "EURUSD-OTC", "GBPUSD-OTC", "AUDUSD-OTC", "USDJPY-OTC",
    "USDCHF-OTC", "NZDUSD-OTC", "USDCAD-OTC", "GBPJPY-OTC",
    "EURJPY-OTC", "AUDCAD-OTC", "AUDJPY-OTC", "EURGBP-OTC",
    "BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD"
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

    # Bollinger Bands
    df['bb_ma'] = df['close'].rolling(20).mean()
    df['bb_std'] = df['close'].rolling(20).std()
    df['bb_upper'] = df['bb_ma'] + 2 * df['bb_std']
    df['bb_lower'] = df['bb_ma'] - 2 * df['bb_std']

    # Stochastic
    low14 = df['low'].rolling(14).min()
    high14 = df['high'].rolling(14).max()
    df['stoch_k'] = 100 * (df['close'] - low14) / (high14 - low14)
    df['stoch_d'] = df['stoch_k'].rolling(3).mean()

    # CCI
    tp = (df['high'] + df['low'] + df['close']) / 3
    sma_tp = tp.rolling(20).mean()
    mad = tp.rolling(20).apply(lambda x: np.abs(x - x.mean()).mean())
    df['cci'] = (tp - sma_tp) / (0.015 * mad)

    # Volumen promedio
    df['vol_avg'] = df['volume'].rolling(20).mean()
    df['vol_ratio'] = df['volume'] / df['vol_avg']

    return df

# =========================
# DETECCIÓN DE NIVELES OCULTOS
# =========================
def detectar_niveles_ocultos(df, ventana=50, umbral_volumen=0.35):
    """
    Detecta niveles donde se concentró al menos `umbral_volumen` del volumen total en una vela.
    Retorna lista de precios.
    """
    if len(df) < ventana:
        return []
    df = df.iloc[-ventana:].copy()
    niveles = []
    for _, row in df.iterrows():
        # Estimación simple: el punto medio ponderado por volumen (aproximación)
        # Como no tenemos datos de ticks, usamos el precio medio como representativo
        precio_medio = (row['high'] + row['low']) / 2
        if row['vol_ratio'] > 1.5:  # volumen alto
            niveles.append(precio_medio)
    # Agrupar niveles cercanos (tolerancia 0.1%)
    niveles_unicos = []
    tolerancia = 0.001
    for p in sorted(niveles):
        if not niveles_unicos or abs(p - niveles_unicos[-1]) / p > tolerancia:
            niveles_unicos.append(p)
    return niveles_unicos

# =========================
# DETECCIÓN DE ZONAS DE BALANCE
# =========================
def detectar_zonas_balance(df, ventana=20):
    """
    Identifica velas doji o de rango estrecho con delta de volumen pequeño.
    Retorna lista de índices de velas que son zonas de balance.
    """
    if len(df) < ventana:
        return []
    df = df.iloc[-ventana:].copy()
    zonas = []
    for i, row in df.iterrows():
        rango = row['high'] - row['low']
        cuerpo = abs(row['close'] - row['open'])
        # Vela doji o de rango pequeño
        if cuerpo < rango * 0.1 or rango / row['close'] < 0.001:
            zonas.append(i)
    return zonas

# =========================
# DETECCIÓN DE SOPORTES/RESISTENCIAS (niveles que han detenido el precio)
# =========================
def detectar_soportes_resistencias(df, num_toques=3, ventana=100):
    """
    Busca niveles donde el precio ha rebotado al menos `num_toques` veces.
    Retorna lista de niveles con su tipo.
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
# ANÁLISIS DE FUERZA DE UNA VELA
# =========================
def analizar_fuerza_vela(df, indice):
    """
    Analiza la vela en el índice dado y devuelve:
        - direccion: 'CALL' o 'PUT' según el cierre
        - fuerza: 1-10 basado en volumen, rango y delta
        - nivel_activado: descripción del nivel que activó la señal (si aplica)
    """
    if indice < 0 or indice >= len(df):
        return None
    vela = df.iloc[indice]
    cuerpo = abs(vela['close'] - vela['open'])
    rango = vela['high'] - vela['low']
    direccion = 'CALL' if vela['close'] > vela['open'] else 'PUT'
    
    # Fuerza base por tamaño de cuerpo
    fuerza_base = min(10, int(cuerpo / (rango + 1e-6) * 10))
    # Bonus por volumen
    if 'vol_ratio' in vela:
        fuerza_base += min(5, int(vela['vol_ratio'] * 2))
    # Penalización por mechas largas
    if direccion == 'CALL':
        mecha_sup = vela['high'] - vela['close']
        if mecha_sup > rango * 0.3:
            fuerza_base -= 2
    else:
        mecha_inf = vela['low'] - vela['open']
        if mecha_inf > rango * 0.3:
            fuerza_base -= 2
    fuerza = max(1, min(10, fuerza_base))
    
    # Detectar si rompió algún nivel relevante (simplificado)
    nivel_activado = None
    # Aquí se podría integrar con los niveles detectados
    return {'direccion': direccion, 'fuerza': fuerza, 'nivel_activado': nivel_activado}

# =========================
# EVALUAR CONFIABILIDAD DE UN ACTIVO
# =========================
def evaluar_confiabilidad(api, asset):
    """
    Analiza un activo y devuelve un puntaje de confiabilidad basado en:
        - Volumen promedio
        - Estabilidad (baja volatilidad)
        - Niveles detectados (cantidad y calidad)
    Retorna un dict con puntaje y detalles, o None si no se puede evaluar.
    """
    try:
        candles = api.get_candles(asset, 60, 100, time.time())  # velas de 1 min
        if not candles or len(candles) < 50:
            return None
        df = pd.DataFrame(candles)
        for col in ['open', 'max', 'min', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df.dropna(inplace=True)
        if len(df) < 50:
            return None
        df = calcular_indicadores(df)
        
        # Volumen promedio
        vol_prom = df['volume'].mean()
        # Volatilidad (rango porcentual medio)
        rango_medio = ((df['high'] - df['low']) / df['close']).mean()
        # Niveles de soporte/resistencia
        niveles = detectar_soportes_resistencias(df, num_toques=2)
        puntaje_niveles = len(niveles) * 2  # cada nivel suma 2 puntos
        
        # Puntaje total (normalizado a 100)
        puntaje = vol_prom * 0.01 + (1 / (rango_medio + 0.001)) * 10 + puntaje_niveles
        return {
            'asset': asset,
            'puntaje': puntaje,
            'vol_prom': vol_prom,
            'rango_medio': rango_medio,
            'niveles': niveles[:3]  # guardamos los 3 más cercanos
        }
    except Exception as e:
        logger.error(f"Error evaluando confiabilidad de {asset}: {e}")
        return None

# =========================
# SELECCIONAR EL ACTIVO MÁS CONFIABLE
# =========================
def seleccionar_mejor_activo(api, lista_activos):
    """
    Evalúa todos los activos y retorna el que tenga mayor puntaje de confiabilidad.
    """
    mejores = []
    for asset in lista_activos:
        res = evaluar_confiabilidad(api, asset)
        if res:
            mejores.append(res)
        time.sleep(0.1)
    if not mejores:
        return None
    mejores.sort(key=lambda x: x['puntaje'], reverse=True)
    return mejores[0]

# =========================
# OBTENER ACTIVOS ABIERTOS (desde IQ Option)
# =========================
def obtener_activos_abiertos(api, tipo_mercado="AMBOS"):
    try:
        open_time = api.get_all_open_time()
        activos = []
        if 'binary' in open_time:
            for asset, data in open_time['binary'].items():
                if data.get('open', False):
                    # Aquí se pueden incluir tanto OTC como reales
                    activos.append(asset)
        logger.info(f"Se obtuvieron {len(activos)} activos abiertos")
        if not activos:
            logger.warning("Usando lista de activos predeterminada (fallback)")
            return FALLBACK_ACTIVOS
        return activos
    except Exception as e:
        logger.error(f"Error obteniendo activos: {e}")
        return FALLBACK_ACTIVOS

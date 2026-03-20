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

    # Estocástico
    low14 = df['low'].rolling(14).min()
    high14 = df['high'].rolling(14).max()
    df['stoch_k'] = 100 * (df['close'] - low14) / (high14 - low14)
    df['stoch_d'] = df['stoch_k'].rolling(3).mean()

    # Supertrend (simplificado)
    # Usamos una media móvil simple para simular, pero en realidad se implementaría más complejo
    df['supertrend'] = df['close'].rolling(10).mean()  # placeholder

    # Volumen promedio
    df['vol_avg'] = df['volume'].rolling(20).mean()
    df['vol_ratio'] = df['volume'] / df['vol_avg']

    return df

# =========================
# DETECCIÓN DE SOPORTES/RESISTENCIAS (niveles clave)
# =========================
def detectar_niveles_sr(df, num_toques=2, ventana=50):
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

# =========================
# ESTRATEGIA 1: DIVERGENCIAS (la original mejorada)
# =========================
def estrategia_divergencias(df):
    if len(df) < 5:
        return None
    last = df.iloc[-1]
    if last['adx'] < 18:
        return None

    segmento = df.iloc[-5:]
    min_precio_idx = segmento['low'].idxmin()
    max_precio_idx = segmento['high'].idxmax()
    min_rsi_idx = segmento['rsi'].idxmin()
    max_rsi_idx = segmento['rsi'].idxmax()
    min_macd_idx = segmento['macd'].idxmin()
    max_macd_idx = segmento['macd'].idxmax()

    def vol_confirm(direccion):
        ultimas = df.iloc[-3:]
        if direccion == 'CALL':
            alcistas = ultimas[ultimas['close'] > ultimas['open']]
            if len(alcistas) > 0:
                return alcistas['volume'].mean() > ultimas['volume'].mean() * 1.2
        else:
            bajistas = ultimas[ultimas['close'] < ultimas['open']]
            if len(bajistas) > 0:
                return bajistas['volume'].mean() > ultimas['volume'].mean() * 1.2
        return False

    if min_precio_idx < min_rsi_idx and segmento.loc[min_precio_idx, 'low'] < segmento.loc[min_rsi_idx, 'low']:
        if segmento.loc[min_rsi_idx, 'rsi'] > segmento.loc[min_precio_idx, 'rsi'] and vol_confirm('CALL'):
            fuerza = 70 + (last['adx'] / 100) * 30
            return ('CALL', 'Divergencia alcista RSI', min(fuerza, 100))
    if max_precio_idx > max_rsi_idx and segmento.loc[max_precio_idx, 'high'] > segmento.loc[max_rsi_idx, 'high']:
        if segmento.loc[max_rsi_idx, 'rsi'] < segmento.loc[max_precio_idx, 'rsi'] and vol_confirm('PUT'):
            fuerza = 70 + (last['adx'] / 100) * 30
            return ('PUT', 'Divergencia bajista RSI', min(fuerza, 100))
    if min_precio_idx < min_macd_idx and segmento.loc[min_precio_idx, 'low'] < segmento.loc[min_macd_idx, 'low']:
        if segmento.loc[min_macd_idx, 'macd'] > segmento.loc[min_precio_idx, 'macd'] and vol_confirm('CALL'):
            fuerza = 70 + (last['adx'] / 100) * 30
            return ('CALL', 'Divergencia alcista MACD', min(fuerza, 100))
    if max_precio_idx > max_macd_idx and segmento.loc[max_precio_idx, 'high'] > segmento.loc[max_macd_idx, 'high']:
        if segmento.loc[max_macd_idx, 'macd'] < segmento.loc[max_precio_idx, 'macd'] and vol_confirm('PUT'):
            fuerza = 70 + (last['adx'] / 100) * 30
            return ('PUT', 'Divergencia bajista MACD', min(fuerza, 100))
    return None

# =========================
# ESTRATEGIA 2: CRUCE DE EMAs
# =========================
def estrategia_cruce_emas(df):
    if len(df) < 2:
        return None
    last = df.iloc[-1]
    prev = df.iloc[-2]
    if last['adx'] < 25:
        return None
    if prev['ema12'] <= prev['ema26'] and last['ema12'] > last['ema26']:
        if last['close'] > last['bb_lower'] and last['close'] < last['bb_upper']:  # dentro de BB
            fuerza = 70 + (last['adx'] / 100) * 20
            return ('CALL', 'Cruce EMAs alcista', min(fuerza, 100))
    if prev['ema12'] >= prev['ema26'] and last['ema12'] < last['ema26']:
        if last['close'] > last['bb_lower'] and last['close'] < last['bb_upper']:
            fuerza = 70 + (last['adx'] / 100) * 20
            return ('PUT', 'Cruce EMAs bajista', min(fuerza, 100))
    return None

# =========================
# ESTRATEGIA 3: RSI + BOLLINGER
# =========================
def estrategia_rsi_bb(df):
    last = df.iloc[-1]
    if last['rsi'] < 30 and last['close'] <= last['bb_lower']:
        fuerza = 70 + (100 - last['rsi']) / 3
        return ('CALL', 'RSI sobreventa + BB inferior', min(fuerza, 100))
    if last['rsi'] > 70 and last['close'] >= last['bb_upper']:
        fuerza = 70 + (last['rsi'] - 70) / 3
        return ('PUT', 'RSI sobrecompra + BB superior', min(fuerza, 100))
    return None

# =========================
# ESTRATEGIA 4: SUPERTREND + ADX (simulado)
# =========================
def estrategia_supertrend_adx(df):
    if len(df) < 2:
        return None
    last = df.iloc[-1]
    prev = df.iloc[-2]
    if last['adx'] < 25:
        return None
    # Simulamos Supertrend con cruce de precio y EMA20
    if prev['close'] <= prev['ema20'] and last['close'] > last['ema20']:
        fuerza = 60 + (last['adx'] / 100) * 20
        return ('CALL', 'Supertrend alcista', min(fuerza, 100))
    if prev['close'] >= prev['ema20'] and last['close'] < last['ema20']:
        fuerza = 60 + (last['adx'] / 100) * 20
        return ('PUT', 'Supertrend bajista', min(fuerza, 100))
    return None

# =========================
# ESTRATEGIA 5: PATRÓN DE VELAS + VOLUMEN
# =========================
def estrategia_patron_velas(df):
    if len(df) < 2:
        return None
    last = df.iloc[-1]
    cuerpo = abs(last['close'] - last['open'])
    rango = last['high'] - last['low']
    if rango == 0:
        return None
    mecha_inf = min(last['open'], last['close']) - last['low']
    mecha_sup = last['high'] - max(last['open'], last['close'])
    # Martillo (alcista)
    if mecha_inf > 2 * cuerpo and cuerpo < rango * 0.3 and last['close'] > last['open']:
        if last['vol_ratio'] > 1.5:
            return ('CALL', 'Martillo alcista', 75)
    # Estrella fugaz (bajista)
    if mecha_sup > 2 * cuerpo and cuerpo < rango * 0.3 and last['close'] < last['open']:
        if last['vol_ratio'] > 1.5:
            return ('PUT', 'Estrella fugaz bajista', 75)
    # Envolvente alcista
    if len(df) > 1:
        prev = df.iloc[-2]
        if last['close'] > last['open'] and prev['close'] < prev['open'] and last['close'] > prev['high'] and last['open'] < prev['low']:
            if last['vol_ratio'] > 1.2:
                return ('CALL', 'Envolvente alcista', 70)
    # Envolvente bajista
        if last['close'] < last['open'] and prev['close'] > prev['open'] and last['close'] < prev['low'] and last['open'] > prev['high']:
            if last['vol_ratio'] > 1.2:
                return ('PUT', 'Envolvente bajista', 70)
    return None

# =========================
# ESTRATEGIA 6: MACD CRUCE CERO
# =========================
def estrategia_macd_zero(df):
    if len(df) < 2:
        return None
    last = df.iloc[-1]
    prev = df.iloc[-2]
    if prev['macd'] <= 0 and last['macd'] > 0 and last['hist'] > prev['hist']:
        fuerza = 60 + (last['adx'] / 100) * 20
        return ('CALL', 'MACD cruce cero alcista', min(fuerza, 100))
    if prev['macd'] >= 0 and last['macd'] < 0 and last['hist'] < prev['hist']:
        fuerza = 60 + (last['adx'] / 100) * 20
        return ('PUT', 'MACD cruce cero bajista', min(fuerza, 100))
    return None

# =========================
# ESTRATEGIA 7: ESTOCÁSTICO + ADX
# =========================
def estrategia_stoch_adx(df):
    if len(df) < 2:
        return None
    last = df.iloc[-1]
    prev = df.iloc[-2]
    if last['adx'] < 25:
        return None
    if prev['stoch_k'] < 20 and last['stoch_k'] > last['stoch_d']:
        fuerza = 65 + (last['adx'] / 100) * 20
        return ('CALL', 'Estocástico sale sobreventa', min(fuerza, 100))
    if prev['stoch_k'] > 80 and last['stoch_k'] < last['stoch_d']:
        fuerza = 65 + (last['adx'] / 100) * 20
        return ('PUT', 'Estocástico sale sobrecompra', min(fuerza, 100))
    return None

# =========================
# ESTRATEGIA 8: SOPORTE/RESISTENCIA + RSI
# =========================
def estrategia_sr_rsi(df):
    niveles = detectar_niveles_sr(df, num_toques=2, ventana=50)
    if not niveles:
        return None
    last = df.iloc[-1]
    nivel_cercano = niveles[0]
    distancia = abs(last['close'] - nivel_cercano['precio']) / last['close']
    if distancia > 0.002:
        return None
    if nivel_cercano['tipo'] == 'soporte' and last['rsi'] < 40:
        fuerza = 65 + (100 - last['rsi']) / 10
        return ('CALL', f'Soporte + RSI', min(fuerza, 100))
    if nivel_cercano['tipo'] == 'resistencia' and last['rsi'] > 60:
        fuerza = 65 + (last['rsi'] - 60) / 10
        return ('PUT', f'Resistencia + RSI', min(fuerza, 100))
    return None

# =========================
# EVALUAR TODAS LAS ESTRATEGIAS PARA UN ACTIVO
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

        estrategias = [
            estrategia_divergencias,
            estrategia_cruce_emas,
            estrategia_rsi_bb,
            estrategia_supertrend_adx,
            estrategia_patron_velas,
            estrategia_macd_zero,
            estrategia_stoch_adx,
            estrategia_sr_rsi
        ]

        votos_call = 0
        votos_put = 0
        peso_call = 0
        peso_put = 0
        descripciones_call = []
        descripciones_put = []

        for func in estrategias:
            try:
                res = func(df)
                if res:
                    direccion, desc, peso = res
                    if direccion == 'CALL':
                        votos_call += 1
                        peso_call += peso
                        descripciones_call.append(desc)
                    else:
                        votos_put += 1
                        peso_put += peso
                        descripciones_put.append(desc)
            except Exception as e:
                continue

        if votos_call + votos_put == 0:
            # No hay señales, solo devolvemos fuerza para selección
            fuerza = df['adx'].iloc[-1] + (df['vol_ratio'].iloc[-1] * 10)
            return {'asset': asset, 'fuerza': min(fuerza, 100)}

        # Decidir dirección por consenso (mayoría simple)
        if votos_call > votos_put:
            direccion = 'CALL'
            fuerza = peso_call / votos_call
            descripcion = ', '.join(descripciones_call[:3])  # máx 3
        elif votos_put > votos_call:
            direccion = 'PUT'
            fuerza = peso_put / votos_put
            descripcion = ', '.join(descripciones_put[:3])
        else:
            # Empate, decidir por peso total
            if peso_call > peso_put:
                direccion = 'CALL'
                fuerza = peso_call / votos_call if votos_call > 0 else 0
                descripcion = ', '.join(descripciones_call[:3])
            else:
                direccion = 'PUT'
                fuerza = peso_put / votos_put if votos_put > 0 else 0
                descripcion = ', '.join(descripciones_put[:3])

        # Normalizar fuerza a 0-100
        fuerza = min(max(fuerza, 0), 100)

        return {
            'asset': asset,
            'direccion': direccion,
            'descripcion': descripcion,
            'fuerza': fuerza,
            'votos_call': votos_call,
            'votos_put': votos_put,
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
# SELECCIONAR LOS N ACTIVOS MÁS FUERTES (por fuerza, sin señal)
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

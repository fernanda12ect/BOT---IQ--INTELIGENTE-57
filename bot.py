import time
import pandas as pd
import numpy as np
import logging
from datetime import datetime, timedelta
import pytz

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Zona horaria de Ecuador
ecuador = pytz.timezone("America/Guayaquil")

# Activos predefinidos (fallback por si falla la API)
REAL_ASSETS = [
    "EURUSD", "GBPUSD", "AUDUSD", "USDJPY",
    "EURJPY", "GBPJPY", "USDCHF", "USDCAD", "NZDUSD"
]
OTC_ASSETS = ["EURUSD-OTC", "GBPUSD-OTC", "AUDUSD-OTC", "USDJPY-OTC"]

# =========================
# OBTENER ACTIVOS ABIERTOS EN TIEMPO REAL
# =========================

def obtener_activos_abiertos(api):
    """
    Obtiene listas de activos REAL y OTC que están actualmente abiertos para trading binario.
    Considera que los activos REAL solo operan de lunes a viernes (días de semana).
    Retorna (real_abiertos, otc_abiertos)
    """
    try:
        open_time = api.get_all_open_time()
        real = []
        otc = []
        # Determinar si es fin de semana (hora UTC)
        now_utc = datetime.now(pytz.UTC)
        dia_semana = now_utc.weekday()  # 0=lunes, 6=domingo
        es_fin_semana = dia_semana >= 5  # sábado o domingo

        if 'binary' in open_time:
            for asset, data in open_time['binary'].items():
                if data.get('open', False):
                    if '-OTC' in asset:
                        otc.append(asset)
                    else:
                        # Solo agregar REAL si no es fin de semana
                        if not es_fin_semana:
                            real.append(asset)
                        else:
                            logging.debug(f"Activo REAL {asset} ignorado por fin de semana")

        # Si es fin de semana y no hay OTC, usar lista predefinida como fallback
        if es_fin_semana and not otc:
            logging.info("Fin de semana sin OTC detectados, usando lista predefinida OTC")
            otc = OTC_ASSETS.copy()

        logging.info(f"Activos abiertos: {len(real)} REAL, {len(otc)} OTC")
        return real, otc

    except Exception as e:
        logging.error(f"Error obteniendo activos abiertos: {e}")
        # Fallback con filtro de fin de semana
        now_utc = datetime.now(pytz.UTC)
        dia_semana = now_utc.weekday()
        es_fin_semana = dia_semana >= 5
        real = [] if es_fin_semana else REAL_ASSETS
        return real, OTC_ASSETS

# =========================
# INDICADORES BASE
# =========================

def calcular_indicadores(df):
    """
    Calcula todos los indicadores comunes y devuelve un dict con los valores de la última vela
    y también las últimas 5 velas para análisis de punto de entrada.
    """
    df = df.copy()

    # EMA
    df['ema20'] = df['close'].ewm(span=20).mean()
    df['ema50'] = df['close'].ewm(span=50).mean()

    # RSI
    delta = df['close'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss
    df['rsi'] = 100 - (100 / (1 + rs))

    # ATR
    high = df['max']
    low = df['min']
    close = df['close']
    tr = pd.concat([
        high - low,
        abs(high - close.shift()),
        abs(low - close.shift())
    ], axis=1).max(axis=1)
    df['atr'] = tr.rolling(14).mean()

    # Bollinger Bands (20,2)
    ma20 = df['close'].rolling(20).mean()
    std20 = df['close'].rolling(20).std()
    df['bb_upper'] = ma20 + 2 * std20
    df['bb_lower'] = ma20 - 2 * std20

    # Volumen medio (20)
    df['vol_ma20'] = df['volume'].rolling(20).mean()

    # ADX (14 períodos)
    df['tr'] = tr  # True Range
    df['plus_dm'] = np.where((high - high.shift()) > (low.shift() - low), np.maximum(high - high.shift(), 0), 0)
    df['minus_dm'] = np.where((low.shift() - low) > (high - high.shift()), np.maximum(low.shift() - low, 0), 0)
    df['atr_period'] = df['tr'].rolling(14).mean()
    df['plus_di'] = 100 * (df['plus_dm'].rolling(14).mean() / df['atr_period'])
    df['minus_di'] = 100 * (df['minus_dm'].rolling(14).mean() / df['atr_period'])
    df['dx'] = 100 * (abs(df['plus_di'] - df['minus_di']) / (df['plus_di'] + df['minus_di']))
    df['adx'] = df['dx'].rolling(14).mean()

    # Últimas 5 velas para análisis de punto de entrada
    ultimas_5 = df.iloc[-5:].copy()
    ultimas_5['body'] = abs(ultimas_5['close'] - ultimas_5['open'])
    ultimas_5['rango'] = ultimas_5['max'] - ultimas_5['min']
    ultimas_5['candle_bullish'] = ultimas_5['close'] > ultimas_5['open']
    ultimas_5['volumen_rel'] = ultimas_5['volume'] / ultimas_5['vol_ma20']

    # Última fila
    last = df.iloc[-1]

    # Fuerza de vela (cuerpo vs rango)
    body = abs(last['close'] - last['open'])
    rng = last['max'] - last['min']
    strong_candle = body > rng * 0.6 if rng != 0 else False

    # Tipo de vela (alcista/bajista)
    candle_bullish = last['close'] > last['open']

    # Volumen fuerte
    vol_now = last['volume']
    vol_avg = last['vol_ma20']
    strong_volume = vol_now > vol_avg * 1.5 if not pd.isna(vol_avg) else False
    very_strong_volume = vol_now > vol_avg * 2.0 if not pd.isna(vol_avg) else False

    # Detectar soportes y resistencias simples (máximos y mínimos de las últimas 20 velas)
    soporte = df['min'].rolling(20).min().iloc[-1]
    resistencia = df['max'].rolling(20).max().iloc[-1]
    # Distancia relativa
    distancia_soporte = abs(last['close'] - soporte) / (last['close'] + 1e-10)
    distancia_resistencia = abs(last['close'] - resistencia) / (last['close'] + 1e-10)
    cerca_soporte = distancia_soporte < 0.001
    cerca_resistencia = distancia_resistencia < 0.001

    # Determinar niveles de soporte/resistencia cercanos (últimos 20)
    # Para punto de entrada, necesitamos saber si hay soporte cerca en tendencia bajista, etc.
    # Esto se usará en la función de punto de entrada

    return {
        'close': last['close'],
        'open': last['open'],
        'high': last['max'],
        'low': last['min'],
        'ema20': last['ema20'],
        'ema50': last['ema50'],
        'rsi': last['rsi'],
        'atr': last['atr'],
        'bb_upper': last['bb_upper'],
        'bb_lower': last['bb_lower'],
        'vol_actual': vol_now,
        'vol_promedio': vol_avg,
        'strong_candle': strong_candle,
        'candle_bullish': candle_bullish,
        'strong_volume': strong_volume,
        'very_strong_volume': very_strong_volume,
        'adx': last['adx'],
        'plus_di': last['plus_di'],
        'minus_di': last['minus_di'],
        'soporte': soporte,
        'resistencia': resistencia,
        'cerca_soporte': cerca_soporte,
        'cerca_resistencia': cerca_resistencia,
        'ultimas_velas': ultimas_5.to_dict('records'),  # para punto de entrada
        'df': df
    }

# =========================
# EVALUAR PUNTO DE ENTRADA (retroceso agotado)
# =========================

def evaluar_punto_entrada(indicators, direccion):
    """
    Determina si se ha alcanzado el punto de entrada ideal.
    Para CALL (compra): se espera que después de un retroceso bajista, las velas de bajada sean pequeñas y con bajo volumen,
    y que la última vela muestre fuerza alcista.
    Para PUT (venta): similar pero con retroceso alcista.
    Retorna True si se cumplen las condiciones.
    """
    velas = indicators['ultimas_velas']
    if len(velas) < 3:
        return False

    # Dirección principal de la tendencia
    if direccion == "CALL":  # Tendencia alcista, buscamos agotamiento de vendedores
        # Buscar si ha habido un retroceso (velas bajistas) en las últimas velas
        retroceso_detectado = False
        for v in velas[-3:]:
            if not v['candle_bullish'] and v['body'] > 0:  # vela bajista
                retroceso_detectado = True
                break
        if not retroceso_detectado:
            return False  # No ha habido retroceso, no es punto de entrada

        # Verificar que las velas bajistas recientes sean pequeñas y con bajo volumen
        # y que la última vela sea alcista con volumen
        ultima = velas[-1]
        if ultima['candle_bullish'] and ultima['body'] > 0 and ultima['volumen_rel'] > 1.2:
            # Además, comprobar que no haya soporte fuerte muy cerca (que podría detener la subida)
            if indicators['close'] - indicators['soporte'] > 0.001 * indicators['close']:  # no demasiado cerca
                return True
    else:  # PUT, tendencia bajista, buscamos agotamiento de compradores
        retroceso_detectado = False
        for v in velas[-3:]:
            if v['candle_bullish'] and v['body'] > 0:  # vela alcista (retroceso)
                retroceso_detectado = True
                break
        if not retroceso_detectado:
            return False

        ultima = velas[-1]
        if not ultima['candle_bullish'] and ultima['body'] > 0 and ultima['volumen_rel'] > 1.2:
            if indicators['resistencia'] - indicators['close'] > 0.001 * indicators['close']:
                return True
    return False

# =========================
# ESTRATEGIA 1: SOPORTE Y RESISTENCIA FUERTE
# =========================

def estrategia_soporte_resistencia(indicators):
    """
    Retorna (dirección, fuerza, nombre_estrategia) si se cumplen condiciones.
    """
    fuerza = 0
    direccion = None
    nombre = "Soporte/Resistencia Fuerte"

    if indicators['cerca_soporte'] and indicators['candle_bullish'] and indicators['strong_candle'] and indicators['strong_volume']:
        direccion = "CALL"
        fuerza = 60 + (10 if indicators['very_strong_volume'] else 0) + (10 if indicators['candle_bullish'] else 0)
    elif indicators['cerca_resistencia'] and not indicators['candle_bullish'] and indicators['strong_candle'] and indicators['strong_volume']:
        direccion = "PUT"
        fuerza = 60 + (10 if indicators['very_strong_volume'] else 0) + (10 if not indicators['candle_bullish'] else 0)

    if direccion:
        fuerza = min(fuerza, 100)
        return direccion, fuerza, nombre
    return None

# =========================
# ESTRATEGIA 2: FUERZA DE TENDENCIA + ADX
# =========================

def estrategia_tendencia_adx(indicators):
    """
    Retorna (dirección, fuerza, nombre_estrategia) si ADX >= 50 y tendencia definida.
    """
    if indicators['adx'] is None or pd.isna(indicators['adx']):
        return None

    adx = indicators['adx']
    if adx < 50:
        return None

    fuerza = adx
    direccion = None
    nombre = "Tendencia Fuerte + ADX"

    if indicators['ema20'] > indicators['ema50'] and indicators['plus_di'] > indicators['minus_di']:
        direccion = "CALL"
    elif indicators['ema20'] < indicators['ema50'] and indicators['minus_di'] > indicators['plus_di']:
        direccion = "PUT"
    else:
        return None

    if indicators['strong_volume']:
        fuerza = min(fuerza + 10, 100)

    return direccion, fuerza, nombre

# =========================
# ESTRATEGIA 3: REVERSIÓN CON VOLUMEN Y VELA FUERTE
# =========================

def estrategia_reversion_bb_rsi(indicators):
    """
    Retorna (dirección, fuerza, nombre_estrategia) si toca BB y RSI extremo con volumen.
    """
    direccion = None
    nombre = "Reversión BB + RSI"
    fuerza = 0

    if indicators['rsi'] < 25 and indicators['close'] <= indicators['bb_lower'] and indicators['candle_bullish'] and indicators['very_strong_volume']:
        direccion = "CALL"
        fuerza = 70 + (10 if indicators['strong_candle'] else 0)
    elif indicators['rsi'] > 75 and indicators['close'] >= indicators['bb_upper'] and not indicators['candle_bullish'] and indicators['very_strong_volume']:
        direccion = "PUT"
        fuerza = 70 + (10 if indicators['strong_candle'] else 0)

    if direccion:
        fuerza = min(fuerza, 100)
        return direccion, fuerza, nombre
    return None

# =========================
# ESTRATEGIA 4: IMBALANCE + NIVELES OCULTOS
# =========================

def estrategia_imbalance(indicators):
    """
    Retorna (dirección, fuerza, nombre_estrategia) si hay posible imbalance.
    """
    rango = indicators['high'] - indicators['low']
    if indicators['atr'] == 0:
        return None

    fuerza_imbalance = (rango / indicators['atr']) * 100
    if fuerza_imbalance < 80:
        return None

    direccion = None
    nombre = "Imbalance + Nivel Oculto"
    fuerza = 0

    if indicators['candle_bullish'] and indicators['very_strong_volume'] and indicators['close'] > indicators['open']:
        direccion = "CALL"
        fuerza = min(70 + fuerza_imbalance * 0.2, 100)
    elif not indicators['candle_bullish'] and indicators['very_strong_volume'] and indicators['close'] < indicators['open']:
        direccion = "PUT"
        fuerza = min(70 + fuerza_imbalance * 0.2, 100)

    if direccion:
        return direccion, fuerza, nombre
    return None

# =========================
# EVALUADOR PRINCIPAL
# =========================

def evaluar_estrategias(indicators):
    """
    Evalúa las 4 estrategias y retorna una lista de señales encontradas.
    Cada señal es un dict: {'direccion': , 'fuerza': , 'estrategia': }
    """
    señales = []
    res1 = estrategia_soporte_resistencia(indicators)
    if res1:
        direccion, fuerza, nombre = res1
        señales.append({'direccion': direccion, 'fuerza': fuerza, 'estrategia': nombre})

    res2 = estrategia_tendencia_adx(indicators)
    if res2:
        direccion, fuerza, nombre = res2
        señales.append({'direccion': direccion, 'fuerza': fuerza, 'estrategia': nombre})

    res3 = estrategia_reversion_bb_rsi(indicators)
    if res3:
        direccion, fuerza, nombre = res3
        señales.append({'direccion': direccion, 'fuerza': fuerza, 'estrategia': nombre})

    res4 = estrategia_imbalance(indicators)
    if res4:
        direccion, fuerza, nombre = res4
        señales.append({'direccion': direccion, 'fuerza': fuerza, 'estrategia': nombre})

    return señales

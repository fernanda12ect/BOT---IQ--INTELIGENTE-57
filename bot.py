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

# =========================
# INDICADORES COMUNES
# =========================
def calcular_indicadores(df):
    df = df.copy()
    df.rename(columns={'max': 'high', 'min': 'low'}, inplace=True)

    # EMAs (2 y 5 períodos para alta sensibilidad)
    df['ema2'] = df['close'].ewm(span=2, adjust=False).mean()
    df['ema5'] = df['close'].ewm(span=5, adjust=False).mean()
    df['ema9'] = df['close'].ewm(span=9, adjust=False).mean()
    df['ema21'] = df['close'].ewm(span=21, adjust=False).mean()

    # RSI (período 9)
    delta = df['close'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(9).mean()
    avg_loss = loss.rolling(9).mean()
    rs = avg_gain / avg_loss
    df['rsi9'] = 100 - (100 / (1 + rs))

    # ATR (período 14) para medir volatilidad
    high, low, close = df['high'], df['low'], df['close']
    tr = pd.concat([high - low, abs(high - close.shift()), abs(low - close.shift())], axis=1).max(axis=1)
    df['atr'] = tr.rolling(14).mean()

    # Volumen promedio
    df['vol_avg'] = df['volume'].rolling(20).mean()
    df['vol_ratio'] = df['volume'] / df['vol_avg']

    return df

# =========================
# DETECCIÓN DE MICRO NIVELES (soportes/resistencias en últimas 5 velas)
# =========================
def detectar_micro_niveles(df, ventana=5):
    """Detecta máximos y mínimos de las últimas `ventana` velas."""
    if len(df) < ventana:
        return [], []
    segmento = df.iloc[-ventana:].copy()
    highs = segmento['high']
    lows = segmento['low']
    # Máximo y mínimo de la ventana
    maximo = highs.max()
    minimo = lows.min()
    # También consideramos máximos/mínimos locales dentro de la ventana
    # para niveles más precisos
    niveles = []
    for i in range(1, len(segmento)-1):
        if highs.iloc[i] > highs.iloc[i-1] and highs.iloc[i] > highs.iloc[i+1]:
            niveles.append(('resistencia', highs.iloc[i]))
        if lows.iloc[i] < lows.iloc[i-1] and lows.iloc[i] < lows.iloc[i+1]:
            niveles.append(('soporte', lows.iloc[i]))
    # Ordenar por cercanía al precio actual
    precio_actual = df['close'].iloc[-1]
    niveles.sort(key=lambda x: abs(x[1] - precio_actual))
    return niveles[:3], maximo, minimo

# =========================
# EVALUAR FUERZA INTRÁVELA (simulada con datos de velas cerradas, pero podríamos usar ticks)
# =========================
def evaluar_fuerza_intravela(df, ventana=10):
    """
    Evalúa la fuerza del movimiento en los últimos `ventana` segundos.
    Como no tenemos ticks, usamos la relación entre la última vela y la anterior.
    Retorna un valor entre 0 y 100.
    """
    if len(df) < 2:
        return 50
    last = df.iloc[-1]
    prev = df.iloc[-2]
    # Cuerpo relativo de la última vela
    cuerpo = abs(last['close'] - last['open'])
    rango = last['high'] - last['low']
    fuerza_cuerpo = (cuerpo / (rango + 1e-6)) * 100 if rango > 0 else 50
    # Velocidad: diferencia de cierre con la vela anterior
    velocidad = abs(last['close'] - prev['close']) / (last['atr'] + 1e-6) * 100
    fuerza = (fuerza_cuerpo + velocidad) / 2
    return min(100, max(0, fuerza))

# =========================
# CLASIFICAR ACTIVO (volátil o tranquilo) basado en ATR
# =========================
def clasificar_activo(df):
    """Retorna 'volatil' o 'tranquilo' según el ATR relativo al precio."""
    if len(df) < 20:
        return 'tranquilo'
    atr = df['atr'].iloc[-1]
    precio = df['close'].iloc[-1]
    ratio = atr / precio
    if ratio > 0.001:  # 0.1% del precio en ATR -> volátil
        return 'volatil'
    else:
        return 'tranquilo'

# =========================
# ESTRATEGIA 1: PARA ACTIVOS MODERADAMENTE VOLÁTILES
# =========================
def estrategia_volatil(df, niveles, maximo, minimo):
    """
    Retorna (direccion, descripcion, fuerza) o None.
    Se basa en cruce/alineación de EMAs (2 y 5), RSI9 y proximidad a micro niveles.
    """
    if len(df) < 10:
        return None
    last = df.iloc[-1]
    prev = df.iloc[-2]
    precio_actual = last['close']
    atr = last['atr']

    # Determinar tendencia por EMAs
    ema2 = last['ema2']
    ema5 = last['ema5']
    # Cruce
    cruce_call = prev['ema2'] <= prev['ema5'] and ema2 > ema5
    cruce_put = prev['ema2'] >= prev['ema5'] and ema2 < ema5
    # Alineación
    alineado_call = ema2 > ema5 and ema2 > last['ema9']
    alineado_put = ema2 < ema5 and ema2 < last['ema9']

    # RSI9
    rsi = last['rsi9']
    rsi_tendencia = rsi - df['rsi9'].iloc[-3] if len(df) >= 3 else 0  # subiendo/bajando

    # Verificar cercanía a micro niveles
    cerca_nivel = False
    direccion_nivel = None
    for tipo, precio in niveles:
        if abs(precio_actual - precio) / precio_actual < 0.0005:  # 0.05% de distancia
            cerca_nivel = True
            if tipo == 'soporte':
                direccion_nivel = 'CALL'
            else:
                direccion_nivel = 'PUT'
            break

    # Si no hay nivel cercano, no operamos
    if not cerca_nivel:
        return None

    # Evaluar fuerza (simulada con vela actual)
    fuerza = evaluar_fuerza_intravela(df)
    if fuerza < 40:
        return None

    # Decisiones
    if direccion_nivel == 'CALL' and (cruce_call or alineado_call) and rsi < 60 and rsi_tendencia > 0:
        return ('CALL', f'Micro soporte + EMA2/5 alcista', fuerza)
    if direccion_nivel == 'PUT' and (cruce_put or alineado_put) and rsi > 40 and rsi_tendencia < 0:
        return ('PUT', f'Micro resistencia + EMA2/5 bajista', fuerza)
    return None

# =========================
# ESTRATEGIA 2: PARA ACTIVOS TRANQUILOS
# =========================
def estrategia_tranquilo(df, niveles, maximo, minimo):
    """
    Para activos con baja volatilidad. Se basa en la estructura de velas y respeto de niveles.
    """
    if len(df) < 15:
        return None
    last = df.iloc[-1]
    prev = df.iloc[-2]
    precio_actual = last['close']
    cuerpo = abs(last['close'] - last['open'])
    rango = last['high'] - last['low']

    # Verificar si la vela actual tiene cuerpo grande y sombras cortas (fuerza)
    vela_fuerte = cuerpo > rango * 0.7
    # Verificar si la vela sigue la dirección de la tendencia anterior
    tendencia_anterior = prev['close'] > prev['open']  # True si alcista
    sigue_tendencia = (last['close'] > last['open']) == tendencia_anterior

    # Verificar cercanía a niveles que se han respetado varias veces
    # Buscamos niveles con al menos 2 toques en la ventana más amplia (últimas 15 velas)
    df_ventana = df.iloc[-15:]
    conteo_niveles = defaultdict(int)
    for _, row in df_ventana.iterrows():
        for tipo, precio in niveles:
            if abs(row['close'] - precio) / precio < 0.0005:
                conteo_niveles[(tipo, precio)] += 1
    nivel_fuerte = None
    for (tipo, precio), cnt in conteo_niveles.items():
        if cnt >= 2:
            nivel_fuerte = (tipo, precio)
            break

    if not nivel_fuerte:
        return None

    tipo_nivel, precio_nivel = nivel_fuerte
    # Distancia actual al nivel
    distancia = abs(precio_actual - precio_nivel) / precio_actual
    if distancia > 0.0005:
        return None

    if tipo_nivel == 'soporte' and sigue_tendencia and last['close'] > last['open']:
        fuerza = 70 if vela_fuerte else 50
        return ('CALL', f'Soporte fuerte (2 toques) + vela {("fuerte" if vela_fuerte else "moderada")}', fuerza)
    if tipo_nivel == 'resistencia' and sigue_tendencia and last['close'] < last['open']:
        fuerza = 70 if vela_fuerte else 50
        return ('PUT', f'Resistencia fuerte (2 toques) + vela {("fuerte" if vela_fuerte else "moderada")}', fuerza)
    return None

# =========================
# EVALUAR UN ACTIVO (elige automáticamente la estrategia según su perfil)
# =========================
def evaluar_activo(api, asset):
    try:
        # Obtener velas de 1 minuto
        candles = api.get_candles(asset, 60, 100, time.time())
        if not candles or len(candles) < 20:
            return None
        df = pd.DataFrame(candles)
        for col in ['open', 'max', 'min', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df.dropna(inplace=True)
        if len(df) < 20:
            return None

        df = calcular_indicadores(df)
        # Detectar micro niveles en últimas 5 velas
        niveles, maximo, minimo = detectar_micro_niveles(df, ventana=5)
        if not niveles:
            return None

        # Clasificar activo
        tipo_activo = clasificar_activo(df)

        # Aplicar estrategia según tipo
        if tipo_activo == 'volatil':
            resultado = estrategia_volatil(df, niveles, maximo, minimo)
        else:
            resultado = estrategia_tranquilo(df, niveles, maximo, minimo)

        if resultado:
            direccion, descripcion, fuerza = resultado
            return {
                'asset': asset,
                'direccion': direccion,
                'descripcion': descripcion,
                'fuerza': fuerza,
                'tipo_activo': tipo_activo,
                'precio': df['close'].iloc[-1]
            }
        else:
            return None
    except Exception as e:
        logger.error(f"Error evaluando {asset}: {e}")
        return None

# =========================
# OBTENER ACTIVOS OTC ABIERTOS (solo OTC)
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
            return [
                "EURUSD-OTC", "GBPUSD-OTC", "AUDUSD-OTC", "USDJPY-OTC",
                "USDCHF-OTC", "NZDUSD-OTC", "USDCAD-OTC", "GBPJPY-OTC",
                "EURJPY-OTC", "AUDCAD-OTC", "AUDJPY-OTC", "EURGBP-OTC"
            ]
        return activos
    except Exception as e:
        logger.error(f"Error obteniendo activos: {e}")
        return []

# =========================
# SELECCIONAR EL MEJOR ACTIVO (el de mayor fuerza)
# =========================
def seleccionar_mejor_activo(api, lista_activos):
    mejor = None
    mejor_fuerza = -1
    for asset in lista_activos:
        res = evaluar_activo(api, asset)
        if res and res['fuerza'] > mejor_fuerza:
            mejor_fuerza = res['fuerza']
            mejor = res
        time.sleep(0.05)  # pausa muy corta
    return mejor

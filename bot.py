import time
import pandas as pd
import numpy as np
import logging
from datetime import datetime, timedelta
import pytz
from collections import defaultdict

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Zona horaria de Ecuador
ecuador = pytz.timezone("America/Guayaquil")

# Solo activos OTC (para este bot)
OTC_ASSETS = [
    "EURUSD-OTC", "GBPUSD-OTC", "AUDUSD-OTC", "USDJPY-OTC",
    "USDCHF-OTC", "NZDUSD-OTC", "USDCAD-OTC", "GBPJPY-OTC",
    "EURJPY-OTC", "AUDCAD-OTC", "AUDJPY-OTC", "EURGBP-OTC"
]

# =========================
# OBTENER ACTIVOS ABIERTOS (solo OTC)
# =========================
def obtener_activos_abiertos(api):
    try:
        open_time = api.get_all_open_time()
        otc = []
        if 'binary' in open_time:
            for asset, data in open_time['binary'].items():
                if data.get('open', False) and '-OTC' in asset:
                    otc.append(asset)
        if not otc:
            otc = OTC_ASSETS
        return [], otc
    except:
        return [], OTC_ASSETS

# =========================
# INDICADORES BASE (ampliados)
# =========================
def calcular_indicadores(df):
    df = df.copy()
    df.rename(columns={'max': 'high', 'min': 'low'}, inplace=True)

    # EMAs
    df['ema10'] = df['close'].ewm(span=10, adjust=False).mean()
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

    # Estocástico
    low_14 = df['low'].rolling(14).min()
    high_14 = df['high'].rolling(14).max()
    df['stoch_k'] = 100 * (df['close'] - low_14) / (high_14 - low_14)
    df['stoch_d'] = df['stoch_k'].rolling(3).mean()

    # Volumen promedio
    df['vol_avg'] = df['volume'].rolling(20).mean()
    df['vol_ratio'] = df['volume'] / df['vol_avg']

    # Última vela
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else last
    prev2 = df.iloc[-3] if len(df) > 2 else prev

    # Cruce de EMAs
    cruce_ema10_20 = (prev['ema10'] <= prev['ema20'] and last['ema10'] > last['ema20']) or \
                     (prev['ema10'] >= prev['ema20'] and last['ema10'] < last['ema20'])
    direccion_cruce = "CALL" if last['ema10'] > last['ema20'] else "PUT" if last['ema10'] < last['ema20'] else None

    # Estabilidad
    if len(df) >= 10:
        ultimas_10 = df.iloc[-10:]
        precio_min = ultimas_10['low'].min()
        precio_max = ultimas_10['high'].max()
        variacion = (precio_max - precio_min) / precio_min if precio_min > 0 else 0
    else:
        variacion = 1.0

    # Divergencia RSI (simple: comparar máximos/mínimos de precio y RSI en últimas 5 velas)
    divergencia_alcista = False
    divergencia_bajista = False
    if len(df) >= 5:
        precios = df['close'].iloc[-5:].values
        rsis = df['rsi'].iloc[-5:].values
        if precios[-1] < precios[-3] and rsis[-1] > rsis[-3]:
            divergencia_alcista = True
        if precios[-1] > precios[-3] and rsis[-1] < rsis[-3]:
            divergencia_bajista = True

    # Patrón de velas (envolvente)
    envolvente_alcista = prev['close'] < prev['open'] and last['close'] > last['open'] and last['close'] > prev['open'] and last['open'] < prev['close']
    envolvente_bajista = prev['close'] > prev['open'] and last['close'] < last['open'] and last['close'] < prev['open'] and last['open'] > prev['close']

    # Martillo (cuerpo pequeño, mecha inferior larga)
    martillo_alcista = (last['close'] - last['low']) > 2 * (last['high'] - last['close']) and (last['high'] - last['close']) < (last['close'] - last['low']) * 0.3

    # Estrella de la mañana/tarde (simplificado: vela grande, luego doji, luego vela en dirección opuesta)
    estrella_alcista = prev2['close'] < prev2['open'] and abs(prev['close'] - prev['open']) < (prev2['high'] - prev2['low'])*0.2 and last['close'] > last['open'] and last['close'] > (prev2['high'] + prev2['low'])/2
    estrella_bajista = prev2['close'] > prev2['open'] and abs(prev['close'] - prev['open']) < (prev2['high'] - prev2['low'])*0.2 and last['close'] < last['open'] and last['close'] < (prev2['high'] + prev2['low'])/2

    # Rango de consolidación (últimas 10 velas)
    rango_10 = df['high'].iloc[-10:].max() - df['low'].iloc[-10:].min()
    breakout_alcista = last['close'] > df['high'].iloc[-11:-1].max() and last['vol_ratio'] > 1.5
    breakout_bajista = last['close'] < df['low'].iloc[-11:-1].min() and last['vol_ratio'] > 1.5

    # Retroceso de Fibonacci (último movimiento significativo)
    # Buscamos el último mínimo y máximo en las últimas 50 velas
    df_50 = df.iloc[-50:]
    minimo_50 = df_50['low'].min()
    maximo_50 = df_50['high'].max()
    fib_382 = maximo_50 - (maximo_50 - minimo_50) * 0.382
    fib_50 = maximo_50 - (maximo_50 - minimo_50) * 0.5
    fib_618 = maximo_50 - (maximo_50 - minimo_50) * 0.618
    # Para tendencia alcista, el retroceso es desde arriba; para bajista, desde abajo
    # Aquí no sabemos la tendencia, así que simplemente comprobamos si el precio está cerca de algún nivel
    cerca_fib = any(abs(last['close'] - fib) / last['close'] < 0.001 for fib in [fib_382, fib_50, fib_618])

    return {
        'close': last['close'],
        'high': last['high'],
        'low': last['low'],
        'open': last['open'],
        'ema10': last['ema10'],
        'ema20': last['ema20'],
        'ema50': last['ema50'],
        'rsi': last['rsi'],
        'stoch_k': last['stoch_k'],
        'stoch_d': last['stoch_d'],
        'vol_ratio': last['vol_ratio'],
        'cruce_ema': cruce_ema10_20,
        'direccion_cruce': direccion_cruce,
        'variacion': variacion,
        'divergencia_alcista': divergencia_alcista,
        'divergencia_bajista': divergencia_bajista,
        'envolvente_alcista': envolvente_alcista,
        'envolvente_bajista': envolvente_bajista,
        'martillo_alcista': martillo_alcista,
        'estrella_alcista': estrella_alcista,
        'estrella_bajista': estrella_bajista,
        'breakout_alcista': breakout_alcista,
        'breakout_bajista': breakout_bajista,
        'cerca_fib': cerca_fib,
        'df': df
    }

# =========================
# ESTRATEGIAS INDIVIDUALES
# =========================

def estrategia_cruce_ema(indicators):
    if indicators['cruce_ema'] and indicators['direccion_cruce']:
        return indicators['direccion_cruce'], 70, "Cruce EMA"
    return None

def estrategia_soporte_resistencia(indicators, niveles_h):
    # niveles_h viene de detectar_niveles_horizontales
    if not niveles_h:
        return None
    nivel = niveles_h[0]  # el más cercano
    distancia = abs(indicators['close'] - nivel['precio']) / nivel['precio']
    if distancia < 0.001:  # toca el nivel
        # Confirmar con vela: que la vela sea del color contrario al nivel (rebote)
        if nivel['tipo'] == 'soporte' and indicators['close'] > indicators['open'] and indicators['vol_ratio'] > 1.2:
            return "CALL", 80, "Soporte con rebote"
        if nivel['tipo'] == 'resistencia' and indicators['close'] < indicators['open'] and indicators['vol_ratio'] > 1.2:
            return "PUT", 80, "Resistencia con rechazo"
    return None

def estrategia_divergencia_rsi(indicators):
    if indicators['divergencia_alcista']:
        return "CALL", 75, "Divergencia alcista RSI"
    if indicators['divergencia_bajista']:
        return "PUT", 75, "Divergencia bajista RSI"
    return None

def estrategia_patron_velas(indicators):
    if indicators['envolvente_alcista']:
        return "CALL", 85, "Envolvente alcista"
    if indicators['envolvente_bajista']:
        return "PUT", 85, "Envolvente bajista"
    if indicators['martillo_alcista']:
        return "CALL", 80, "Martillo"
    if indicators['estrella_alcista']:
        return "CALL", 90, "Estrella de la mañana"
    if indicators['estrella_bajista']:
        return "PUT", 90, "Estrella de la tarde"
    return None

def estrategia_breakout(indicators):
    if indicators['breakout_alcista']:
        return "CALL", 85, "Breakout alcista"
    if indicators['breakout_bajista']:
        return "PUT", 85, "Breakout bajista"
    return None

def estrategia_volumen_extremo(indicators):
    if indicators['vol_ratio'] > 2.0:
        # Vela grande en dirección
        if indicators['close'] > indicators['open']:
            return "CALL", 70, "Volumen extremo alcista"
        else:
            return "PUT", 70, "Volumen extremo bajista"
    return None

def estrategia_ema_dinamica(indicators):
    # Precio rebota en EMA10 o EMA20
    if abs(indicators['close'] - indicators['ema10']) / indicators['close'] < 0.001 and indicators['close'] > indicators['open']:
        return "CALL", 65, "Rebote en EMA10"
    if abs(indicators['close'] - indicators['ema20']) / indicators['close'] < 0.001 and indicators['close'] > indicators['open']:
        return "CALL", 65, "Rebote en EMA20"
    if abs(indicators['close'] - indicators['ema10']) / indicators['close'] < 0.001 and indicators['close'] < indicators['open']:
        return "PUT", 65, "Rechazo en EMA10"
    if abs(indicators['close'] - indicators['ema20']) / indicators['close'] < 0.001 and indicators['close'] < indicators['open']:
        return "PUT", 65, "Rechazo en EMA20"
    return None

def estrategia_cruce_estocastico(indicators):
    # Cruce en zona de sobrecompra/venta
    if indicators['stoch_k'] > 80 and indicators['stoch_k'] < indicators['stoch_d'] and indicators['stoch_k'] - indicators['stoch_d'] > 5:
        return "PUT", 70, "Estocástico sobrecompra"
    if indicators['stoch_k'] < 20 and indicators['stoch_k'] > indicators['stoch_d'] and indicators['stoch_d'] - indicators['stoch_k'] > 5:
        return "CALL", 70, "Estocástico sobreventa"
    return None

def estrategia_fibonacci(indicators):
    if indicators['cerca_fib']:
        # Asumimos que el precio está cerca de un nivel de Fibonacci
        # Podríamos añadir dirección según la posición, pero por simplicidad,
        # si la vela es alcista y está cerca de un soporte, o bajista cerca de resistencia
        # Esto requeriría saber si el nivel es soporte o resistencia. Lo dejamos como señal genérica
        # y lo refinamos después.
        return "CALL", 60, "Cerca de Fibonacci"
    return None

def estrategia_presion(indicators):
    # Presión compradora/vendedora: si el cierre está en el 70% superior del rango y volumen alto
    rango = indicators['high'] - indicators['low']
    if rango == 0:
        return None
    posicion = (indicators['close'] - indicators['low']) / rango
    if posicion > 0.7 and indicators['vol_ratio'] > 1.5:
        return "CALL", 70, "Presión compradora"
    if posicion < 0.3 and indicators['vol_ratio'] > 1.5:
        return "PUT", 70, "Presión vendedora"
    return None

# =========================
# DETECCIÓN DE NIVELES HORIZONTALES (para estrategia 2)
# =========================
def detectar_niveles_horizontales(df, num_toques=2):
    df = df.iloc[-100:].copy()
    highs = df['high']
    lows = df['low']
    tolerancia = 0.0005
    conteo = defaultdict(int)
    for idx, val in enumerate(highs):
        for j in range(max(0, idx-5), min(len(highs), idx+5)):
            if abs(highs.iloc[j] - val) / val < tolerancia:
                conteo[round(val, 5)] += 1
    for idx, val in enumerate(lows):
        for j in range(max(0, idx-5), min(len(lows), idx+5)):
            if abs(lows.iloc[j] - val) / val < tolerancia:
                conteo[round(val, 5)] += 1
    niveles_h = []
    for precio, cnt in conteo.items():
        if cnt >= num_toques:
            tipo = 'resistencia' if precio > df['close'].iloc[-1] else 'soporte'
            niveles_h.append({'precio': precio, 'tipo': tipo, 'toques': cnt})
    precio_actual = df['close'].iloc[-1]
    niveles_h.sort(key=lambda x: abs(x['precio'] - precio_actual))
    return niveles_h

# =========================
# DETECTAR LÍNEAS DE TENDENCIA (para mantener compatibilidad)
# =========================
def detectar_lineas_tendencia(df):
    # Se mantiene pero no se usa en las nuevas estrategias (opcional)
    return []

# =========================
# EVALUADOR PRINCIPAL (llama a todas las estrategias)
# =========================
def evaluar_activo(indicators, umbral_estabilidad=0.012):
    # Primero, verificar estabilidad
    if indicators['variacion'] > umbral_estabilidad:
        return None

    # Detectar niveles horizontales para la estrategia 2
    niveles_h = detectar_niveles_horizontales(indicators['df'], num_toques=2)

    # Lista de estrategias a evaluar
    estrategias = [
        estrategia_cruce_ema,
        lambda ind: estrategia_soporte_resistencia(ind, niveles_h),
        estrategia_divergencia_rsi,
        estrategia_patron_velas,
        estrategia_breakout,
        estrategia_volumen_extremo,
        estrategia_ema_dinamica,
        estrategia_cruce_estocastico,
        estrategia_fibonacci,
        estrategia_presion
    ]

    mejores = []
    for est in estrategias:
        try:
            res = est(indicators)
            if res:
                direccion, fuerza, nombre = res
                mejores.append((fuerza, direccion, nombre))
        except Exception as e:
            # Si una estrategia falla, la ignoramos
            continue

    if not mejores:
        return None
    mejores.sort(reverse=True)
    fuerza, direccion, nombre = mejores[0]
    # Devolvemos la mejor señal
    return {
        'tipo': nombre,
        'direccion': direccion,
        'nivel': indicators['close'],  # No hay un nivel único, usamos el precio actual
        'fuerza': fuerza,
        'descripcion': nombre
    }

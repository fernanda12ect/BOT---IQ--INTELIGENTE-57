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

# =========================
# INDICADOR DE PRESIÓN (basado en velas de 1 min)
# =========================
def calcular_presion(df_1min, ventana=5):
    """
    Calcula la presión compradora/vendedora en los últimos `ventana` minutos.
    Retorna:
        - direccion: 'CALL' o 'PUT' según la presión predominante
        - fuerza: valor entre 0 y 100
        - delta_volumen: diferencia entre volumen comprador y vendedor
    """
    if len(df_1min) < ventana:
        return None, 0, 0
    
    ultimas = df_1min.iloc[-ventana:].copy()
    # Identificar velas alcistas (close > open) y bajistas (close < open)
    alcistas = ultimas[ultimas['close'] > ultimas['open']]
    bajistas = ultimas[ultimas['close'] < ultimas['open']]
    
    vol_alcista = alcistas['volume'].sum() if not alcistas.empty else 0
    vol_bajista = bajistas['volume'].sum() if not bajistas.empty else 0
    
    # Volumen total
    vol_total = vol_alcista + vol_bajista
    if vol_total == 0:
        return None, 0, 0
    
    # Delta de volumen (positivo = más compra, negativo = más venta)
    delta = vol_alcista - vol_bajista
    fuerza = abs(delta) / vol_total * 100  # fuerza como porcentaje del total
    
    direccion = 'CALL' if delta > 0 else 'PUT'
    return direccion, fuerza, delta

# =========================
# OBTENER DATOS DE VELAS DE 1 MINUTO
# =========================
def obtener_velas_1min(api, asset, minutos=10):
    try:
        candles = api.get_candles(asset, 60, minutos, time.time())
        if not candles or len(candles) < minutos:
            return None
        df = pd.DataFrame(candles)
        for col in ['open', 'max', 'min', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df.dropna(inplace=True)
        return df
    except Exception as e:
        logger.error(f"Error obteniendo velas de {asset}: {e}")
        return None

# =========================
# PREDECIR LA PRÓXIMA VELA (simulado)
# =========================
def predecir_proxima_vela(api, asset, ventana=5):
    """
    Evalúa la presión en los últimos `ventana` minutos y predice la dirección de la próxima vela de 1 min.
    Retorna (direccion, fuerza) o (None, 0) si no hay suficiente datos.
    """
    df = obtener_velas_1min(api, asset, minutos=ventana+1)
    if df is None or len(df) < ventana:
        return None, 0
    
    direccion, fuerza, delta = calcular_presion(df, ventana)
    return direccion, fuerza

# =========================
# EJEMPLO DE USO (para prueba)
# =========================
if __name__ == "__main__":
    # Esto es solo para pruebas, no se ejecutará en el bot real
    pass

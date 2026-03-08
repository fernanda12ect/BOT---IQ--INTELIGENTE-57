from iqoptionapi.stable_api import IQ_Option
import pandas as pd
from datetime import datetime, timedelta
import pytz
import time

ecuador = pytz.timezone("America/Guayaquil")

class IQBot:

    def __init__(self,email,password,log):
        self.email=email
        self.password=password
        self.log=log
        self.API=None

    def connect(self):

        self.API = IQ_Option(self.email,self.password)
        self.API.connect()

        if self.API.check_connect():
            self.log("Conectado a IQ Option")
            return True
        else:
            self.log("Error conectando")
            return False


    def get_assets(self):

        activos=[]

        all_assets=self.API.get_all_open_time()

        for tipo in all_assets:

            for asset,data in all_assets[tipo].items():

                if data["open"]:
                    activos.append(asset)

        return activos


    def get_candles(self,asset):

        try:

            candles=self.API.get_candles(asset,60,100,time.time())

            df=pd.DataFrame(candles)

            return df

        except:
            return None


    def analyze(self,asset):

        df=self.get_candles(asset)

        if df is None or len(df)<60:
            return None

        close=df["close"]

        ema20=close.ewm(span=20).mean()
        ema50=close.ewm(span=50).mean()

        delta=close.diff()

        gain=(delta.where(delta>0,0)).rolling(14).mean()
        loss=(-delta.where(delta<0,0)).rolling(14).mean()

        rs=gain/loss

        rsi=100-(100/(1+rs))

        score=0
        signal=None

        # tendencia
        if ema20.iloc[-1]>ema50.iloc[-1]:
            signal="CALL"
            score+=30

        elif ema20.iloc[-1]<ema50.iloc[-1]:
            signal="PUT"
            score+=30

        else:
            self.log(f"{asset} sin tendencia")
            return None


        price=close.iloc[-1]
        ema20_now=ema20.iloc[-1]

        # retroceso
        if abs(price-ema20_now)/price<0.0015:
            score+=20

        rsi_now=rsi.iloc[-1]

        # fuerza
        if signal=="CALL" and 45<rsi_now<65:
            score+=20

        if signal=="PUT" and 35<rsi_now<55:
            score+=20


        last_open=df["open"].iloc[-1]
        last_close=df["close"].iloc[-1]

        # vela confirmación
        if signal=="CALL" and last_close>last_open:
            score+=15

        if signal=="PUT" and last_close<last_open:
            score+=15

        body=abs(last_close-last_open)

        if body/price>0.0005:
            score+=15


        prob=score

        if prob<75:

            self.log(f"{asset} señal débil {prob}%")

            return None


        now=datetime.now(ecuador)

        entry=now+timedelta(minutes=1)

        entry=entry.replace(second=0,microsecond=0)

        expiry=entry+timedelta(minutes=5)

        self.log(f"{asset} señal fuerte {prob}%")

        return {

            "asset":asset,
            "signal":signal,
            "prob":prob,
            "entry":entry,
            "expiry":expiry,
            "detected":now

        }

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

        try:
            self.API=IQ_Option(self.email,self.password)
            self.API.connect()

            if self.API.check_connect():
                self.log("Conectado a IQ Option")
                return True
            else:
                self.log("Error conectando")
                return False
        except:
            self.log("Error conexión")
            return False

    def get_balance(self):
        try:
            return self.API.get_balance()
        except:
            return 0

    def get_assets(self):

        activos=set()

        try:
            all_assets=self.API.get_all_open_time()

            for tipo in all_assets:

                for asset,data in all_assets[tipo].items():

                    if data["open"]:
                        activos.add(asset)

        except:
            pass

        return list(activos)

    def get_candles(self,asset):

        try:

            candles=self.API.get_candles(asset,60,100,time.time())

            df=pd.DataFrame(candles)

            return df

        except:
            return None


    def analyze(self,asset):

        df=self.get_candles(asset)

        if df is None:
            return None

        if len(df)<50:
            return None

        close=df["close"]

        ema20=close.ewm(span=20).mean()
        ema50=close.ewm(span=50).mean()

        delta=close.diff()

        gain=(delta.where(delta>0,0)).rolling(14).mean()
        loss=(-delta.where(delta<0,0)).rolling(14).mean()

        rs=gain/loss

        rsi=100-(100/(1+rs))

        trend=None

        if ema20.iloc[-1]>ema50.iloc[-1]:
            trend="CALL"

        if ema20.iloc[-1]<ema50.iloc[-1]:
            trend="PUT"

        if trend is None:
            self.log(f"{asset} sin tendencia clara")
            return None

        rsi_now=rsi.iloc[-1]

        if trend=="CALL" and rsi_now>70:
            self.log(f"{asset} sobrecomprado")
            return None

        if trend=="PUT" and rsi_now<30:
            self.log(f"{asset} sobrevendido")
            return None

        now=datetime.now(ecuador)

        entry=now+timedelta(minutes=1)

        entry=entry.replace(second=0,microsecond=0)

        expiry=entry+timedelta(minutes=5)

        return {

            "asset":asset,
            "signal":trend,
            "entry":entry,
            "expiry":expiry,
            "detected":now

        }

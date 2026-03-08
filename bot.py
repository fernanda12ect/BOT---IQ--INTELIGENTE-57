from iqoptionapi.stable_api import IQ_Option
import pandas as pd
import ta
import time
from datetime import datetime, timedelta

class IQBot:

    def __init__(self,email,password,logger):

        self.email=email
        self.password=password
        self.log=logger
        self.API=None

    def connect(self):

        self.API=IQ_Option(self.email,self.password)

        check,reason=self.API.connect()

        if check:
            self.log("Conectado a IQ Option")
            return True
        else:
            self.log("Error de conexión")
            return False


    def get_balance(self):
        return self.API.get_balance()


    def get_assets(self):

        data=self.API.get_all_open_time()

        activos=[]

        for market in data:

            for asset in data[market]:

                if data[market][asset]["open"]:
                    activos.append(asset)

        return activos


    def get_candles(self,asset):

        candles=self.API.get_candles(asset,60,80,time.time())

        df=pd.DataFrame(candles)

        df["close"]=df["close"].astype(float)

        return df


    def analyze(self,asset):

        self.log(f"Analizando {asset}...")

        df=self.get_candles(asset)

        df["ema20"]=ta.trend.ema_indicator(df["close"],20)
        df["ema50"]=ta.trend.ema_indicator(df["close"],50)

        df["rsi"]=ta.momentum.rsi(df["close"],14)

        macd=ta.trend.MACD(df["close"])
        df["macd"]=macd.macd()

        last=df.iloc[-1]

        score=0
        reason=""

        if last["ema20"]>last["ema50"]:
            score+=1
        else:
            reason="EMA sin tendencia"

        if last["rsi"]>55:
            score+=1
        else:
            reason="RSI débil"

        if last["macd"]>0:
            score+=1
        else:
            reason="MACD negativo"

        if score>=3:

            signal="CALL"

        elif score<=1:

            signal="PUT"

        else:

            self.log(f"Descartado {asset} – {reason}")
            return None


        now=datetime.now()

        entry=now+timedelta(minutes=2)

        return {
            "asset":asset.upper(),
            "signal":signal,
            "entry":entry,
            "detected":now
        }

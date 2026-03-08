from iqoptionapi.stable_api import IQ_Option
import pandas as pd
import numpy as np
import time
import ta

class IQBot:

    def __init__(self,email,password):
        self.email=email
        self.password=password
        self.API=None
        self.connected=False

    def connect(self):

        self.API=IQ_Option(self.email,self.password)

        check,reason=self.API.connect()

        if check:
            self.connected=True
            return True
        else:
            return False


    def get_balance(self):
        return self.API.get_balance()


    def get_all_assets(self):

        assets=self.API.get_all_open_time()

        activos=[]

        for market in assets:

            for asset in assets[market]:

                if assets[market][asset]["open"]:

                    activos.append(asset)

        return activos


    def get_candles(self,asset):

        candles=self.API.get_candles(asset,60,100,time.time())

        df=pd.DataFrame(candles)

        df["close"]=df["close"].astype(float)

        return df


    def analyze_asset(self,asset):

        df=self.get_candles(asset)

        df["ema20"]=ta.trend.ema_indicator(df["close"],20)
        df["ema50"]=ta.trend.ema_indicator(df["close"],50)

        df["rsi"]=ta.momentum.rsi(df["close"],14)

        macd=ta.trend.MACD(df["close"])

        df["macd"]=macd.macd()

        last=df.iloc[-1]

        score=0

        if last["ema20"]>last["ema50"]:
            score+=1

        if last["rsi"]>55:
            score+=1

        if last["macd"]>0:
            score+=1

        if score>=3:
            return "CALL"

        if last["ema20"]<last["ema50"] and last["rsi"]<45 and last["macd"]<0:
            return "PUT"

        return None


    def scan_market(self):

        activos=self.get_all_assets()

        signals=[]

        for asset in activos:

            try:

                signal=self.analyze_asset(asset)

                if signal:

                    signals.append((asset,signal))

            except:
                pass

        return signals

import time
import pandas as pd
from iqoptionapi.stable_api import IQ_Option


class IQBot:

    def __init__(self,email,password,logger):

        self.email=email
        self.password=password
        self.API=None
        self.log=logger


    def connect(self):

        try:

            self.API=IQ_Option(self.email,self.password)

            check,reason=self.API.connect()

            if check:

                self.log("Conectado a IQ Option")

                return True

            else:

                self.log(f"Error conexión: {reason}")

                return False

        except Exception as e:

            self.log("Error conectando")
            self.log(str(e))
            return False


    def get_balance(self):

        try:
            return self.API.get_balance()
        except:
            return 0


    def get_assets(self):

        try:

            data=self.API.get_all_open_time()

            activos=[]

            for market in data:

                for asset in data[market]:

                    if data[market][asset]["open"]:

                        activos.append(asset)

            return activos

        except:

            self.log("Error obteniendo activos")

            return []


    def get_candles(self,asset):

        try:

            candles=self.API.get_candles(asset,60,50,time.time())

            df=pd.DataFrame(candles)

            return df

        except:

            self.log(f"Error velas {asset}")

            return None


    def analyze(self,asset):

        try:

            df=self.get_candles(asset)

            if df is None or df.empty:

                return None

            close=df["close"]

            sma_fast=close.rolling(5).mean()

            sma_slow=close.rolling(10).mean()

            if sma_fast.iloc[-1] > sma_slow.iloc[-1]:

                return "CALL"

            elif sma_fast.iloc[-1] < sma_slow.iloc[-1]:

                return "PUT"

            return None

        except:

            self.log(f"Error analizando {asset}")

            return None

import time
import json
import pandas as pd
from iqoptionapi.stable_api import IQ_Option


class TradingBot:

    def __init__(self,email,password):

        self.email=email
        self.password=password
        self.API=None
        self.running=False


    def log(self,msg):

        print(f"[BOT] {msg}")


    def connect(self):

        try:

            self.API=IQ_Option(self.email,self.password)

            check,reason=self.API.connect()

            if check:

                self.log("Conectado correctamente a IQ Option")

                self.API.change_balance("PRACTICE")

                return True

            else:

                self.log(f"Error conexión: {reason}")
                return False

        except Exception as e:

            self.log("Error conectando")
            self.log(str(e))
            return False


    def get_assets(self):

        try:

            data=self.API.get_all_open_time()

            activos=[]

            for market in data:

                for asset in data[market]:

                    if data[market][asset]["open"]:

                        activos.append(asset)

            return activos

        except Exception as e:

            self.log("Error obteniendo activos")
            return []


    def get_candles(self,asset):

        try:

            candles=self.API.get_candles(asset,60,50,time.time())

            df=pd.DataFrame(candles)

            return df

        except Exception as e:

            self.log(f"Error obteniendo velas {asset}")
            return None


    def analyze(self,asset):

        try:

            self.log(f"Analizando {asset}")

            df=self.get_candles(asset)

            if df is None or df.empty:

                return None

            close=df["close"]

            sma_fast=close.rolling(5).mean()
            sma_slow=close.rolling(10).mean()

            if sma_fast.iloc[-1] > sma_slow.iloc[-1]:

                return "call"

            elif sma_fast.iloc[-1] < sma_slow.iloc[-1]:

                return "put"

            return None

        except Exception as e:

            self.log(f"Error analizando {asset}")
            return None


    def trade(self,asset,action):

        try:

            amount=1
            duration=1

            check,id=self.API.buy(amount,asset,action,duration)

            if check:

                self.log(f"Trade ejecutado {asset} {action}")

            else:

                self.log(f"Trade falló {asset}")

        except Exception as e:

            self.log("Error ejecutando trade")


    def start(self):

        self.running=True

        while self.running:

            try:

                activos=self.get_assets()

                for asset in activos:

                    signal=self.analyze(asset)

                    if signal:

                        self.trade(asset,signal)

                    time.sleep(2)

            except Exception as e:

                self.log("Error ciclo bot")
                time.sleep(5)


    def stop(self):

        self.running=False
        self.log("Bot detenido")

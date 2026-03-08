from iqoptionapi.stable_api import IQ_Option
from datetime import datetime, timedelta
import pandas as pd
import time

class IQBot:

    def __init__(self,email,password,log):

        self.email=email
        self.password=password
        self.log=log
        self.API=None


    # -----------------------------
    # CONECTAR A IQ OPTION
    # -----------------------------
    def connect(self):

        try:

            self.API=IQ_Option(self.email,self.password)

            check,reason=self.API.connect()

            if check:

                self.log("Conectado a IQ Option")

                self.API.change_balance("PRACTICE")

                return True

            else:

                self.log(f"Error conexión: {reason}")

                return False

        except Exception as e:

            self.log(f"Error conectando: {e}")

            return False


    # -----------------------------
    # BALANCE
    # -----------------------------
    def get_balance(self):

        try:

            return self.API.get_balance()

        except:

            return "0"


    # -----------------------------
    # OBTENER ACTIVOS
    # -----------------------------
    def get_assets(self):

        assets=[]

        try:

            all_assets=self.API.get_all_open_time()

            # FOREX
            for asset,data in all_assets["forex"].items():

                if data["open"]:

                    assets.append(asset)

            # CRYPTO
            for asset,data in all_assets["crypto"].items():

                if data["open"]:

                    assets.append(asset)

            # DIGITAL
            if "digital" in all_assets:

                for asset,data in all_assets["digital"].items():

                    if data["open"]:

                        assets.append(asset)

        except Exception as e:

            self.log(f"Error obteniendo activos: {e}")

        self.log(f"{len(assets)} activos encontrados")

        return assets


    # -----------------------------
    # OBTENER VELAS
    # -----------------------------
    def get_candles(self,asset):

        try:

            candles=self.API.get_candles(asset,60,120,time.time())

            df=pd.DataFrame(candles)

            return df

        except:

            return None


    # -----------------------------
    # ANALISIS DE TENDENCIA
    # -----------------------------
    def analyze(self,asset):

        df=self.get_candles(asset)

        if df is None:

            return None

        if len(df)<50:

            return None


        # medias
        df["ema20"]=df["close"].ewm(span=20).mean()
        df["ema50"]=df["close"].ewm(span=50).mean()


        last=df.iloc[-1]


        # tendencia
        if last["ema20"]>last["ema50"]:

            signal="CALL"

        elif last["ema20"]<last["ema50"]:

            signal="PUT"

        else:

            return None


        # tiempo actual
        now=datetime.now()

        # entrada en 2 minutos
        entry=now+timedelta(minutes=2)

        detected=now


        return {

            "asset":asset,
            "signal":signal,
            "entry":entry,
            "detected":detected

        }

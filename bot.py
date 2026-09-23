import yfinance as yf
import time
import pandas as pd
import threading
from flask import Flask

# ----------------- 1. RENDER WEB SERVER -----------------
app = Flask(__name__)

@app.route('/')
def home():
    return "XAUUSD Gold 4H-15M Algo Bot is running perfectly!"

def start_web_server():
    app.run(host='0.0.0.0', port=10000)

# ----------------- 2. CONFIGURATION -----------------
# GC=F शिकागो मर्केंटाइल एक्सचेंज (COMEX) का गोल्ड फ्यूचर्स है (पूरी दुनिया में स्टैंडर्ड गोल्ड भाव)
SYMBOL = 'GC=F'
RR_RATIO = 5.0          # 1:5 Risk to Reward
QTY_OUNCES = 1.0        # 1 औंस (पेपर लॉट)
SL_BUFFER = 1.5         # गोल्ड के लिए $1.5 का स्टॉप लॉस बफ़र

# ----------------- 3. DATA FUNCTIONS -----------------
def get_candles(interval, period):
    ticker = yf.Ticker(SYMBOL)
    df = ticker.history(period=period, interval=interval)
    df = df.rename(columns={
        'Open': 'open',
        'High': 'high',
        'Low': 'low',
        'Close': 'close',
        'Volume': 'volume'
    })
    return df

def get_4h_key_levels():
    # 4 घंटे के लिए 1 घंटे की कैंडल्स से रेंज निकालना (Yahoo 1h कैंडल्स स्मूथ देता है)
    df_1h = get_candles(interval='1h', period='10d')
    # पिछले 40 कैंडल्स (लगभग 10 x 4H कैंडल्स)
    key_low = df_1h['low'].iloc[-41:-1].min()
    key_high = df_1h['high'].iloc[-41:-1].max()
    return key_low, key_high

# ----------------- 4. MAIN TRADING BOT -----------------
def run_trading_bot():
    print(f"गोल्ड बॉट सक्रिय है... सिंबल: XAU/USD ({SYMBOL}), टारगेट: 1:{int(RR_RATIO)} RR", flush=True)
    
    buy_sweep_active = False
    buy_sweep_lowest = 0.0
    
    sell_sweep_active = False
    sell_sweep_highest = 0.0
    
    while True:
        try:
            key_low_4h, key_high_4h = get_4h_key_levels()
            
            # 15 मिनट की पिछली क्लोज्ड कैंडल
            df_15m = get_candles(interval='15m', period='2d')
            last_closed = df_15m.iloc[-2]
            
            c_open = last_closed['open']
            c_high = last_closed['high']
            c_low = last_closed['low']
            c_close = last_closed['close']
            
            # हर 30 सेकंड में गोल्ड का लाइव भाव और रेंज प्रिंट होगी
            print(f"[STATUS] XAU/USD: ${c_close:.2f} | 4H Range: [${key_low_4h:.2f} - ${key_high_4h:.2f}] | Scan OK", flush=True)
            
            # --- BUY (LONG) LOGIC ---
            if c_low < key_low_4h and not buy_sweep_active:
                buy_sweep_active = True
                buy_sweep_lowest = c_low
                print(f"⚠️ [ALERT] सोने में नीचे की लिक्विडिटी स्विप! लो: ${buy_sweep_lowest:.2f}", flush=True)

            if buy_sweep_active:
                if c_low < buy_sweep_lowest:
                    buy_sweep_lowest = c_low

                # 15M कैंडल ग्रीन क्लोज होने पर एंट्री
                if c_close > c_open:
                    entry_price = c_close
                    stop_loss = buy_sweep_lowest - SL_BUFFER
                    risk = entry_price - stop_loss
                    
                    if risk > 0:
                        take_profit = entry_price + (risk * RR_RATIO)
                        print(f"\n🚀 [GOLD BUY SIGNAL] Entry: ${entry_price:.2f} | SL: ${stop_loss:.2f} | TP: ${take_profit:.2f} | Size: {QTY_OUNCES} oz", flush=True)
                        buy_sweep_active = False
                        time.sleep(1800)  # ट्रेड के बाद 30 मिनट कूलडाउन
            
            # --- SELL (SHORT) LOGIC ---
            if c_high > key_high_4h and not sell_sweep_active:
                sell_sweep_active = True
                sell_sweep_highest = c_high
                print(f"⚠️ [ALERT] सोने में ऊपर की लिक्विडिटी स्विप! हाई: ${sell_sweep_highest:.2f}", flush=True)

            if sell_sweep_active:
                if c_high > sell_sweep_highest:
                    sell_sweep_highest = c_high

                # 15M कैंडल रेड क्लोज होने पर एंट्री
                if c_close < c_open:
                    entry_price = c_close
                    stop_loss = sell_sweep_highest + SL_BUFFER
                    risk = stop_loss - entry_price
                    
                    if risk > 0:
                        take_profit = entry_price - (risk * RR_RATIO)
                        print(f"\n🔻 [GOLD SELL SIGNAL] Entry: ${entry_price:.2f} | SL: ${stop_loss:.2f} | TP: ${take_profit:.2f} | Size: {QTY_OUNCES} oz", flush=True)
                        sell_sweep_active = False
                        time.sleep(1800)  # ट्रेड के बाद 30 मिनट कूलडाउन
            
            time.sleep(30)
            
        except Exception as e:
            print(f"गोल्ड लूप त्रुटि: {e}", flush=True)
            time.sleep(15)

if __name__ == '__main__':
    t = threading.Thread(target=start_web_server)
    t.daemon = True
    t.start()
    run_trading_bot()
  

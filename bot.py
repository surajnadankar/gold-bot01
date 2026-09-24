import yfinance as yf
import time
import pandas as pd
import threading
import requests
from flask import Flask

# ----------------- TELEGRAM CONFIG -----------------
TELEGRAM_BOT_TOKEN = "8895341894:AAEE-p0_Ylj6RFmqr06nx5xNT7vzyBaBTqI"
TELEGRAM_CHAT_ID = "998154896"

def send_telegram_msg(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown"
        }
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Telegram bhejne mein error: {e}", flush=True)

# ----------------- 1. RENDER WEB SERVER -----------------
app = Flask(__name__)

@app.route('/')
def home():
    return "XAUUSD Gold 4H-15M Telegram Bot is running perfectly!"

def start_web_server():
    app.run(host='0.0.0.0', port=10000)

# ----------------- 2. CONFIGURATION -----------------
SYMBOL = 'GC=F'         # Gold Futures (XAU/USD)
RR_RATIO = 5.0          # 1:5 Risk to Reward
QTY_OUNCES = 1.0
SL_BUFFER = 1.5         # $1.5 buffer for Gold

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
    df_1h = get_candles(interval='1h', period='10d')
    key_low = df_1h['low'].iloc[-41:-1].min()
    key_high = df_1h['high'].iloc[-41:-1].max()
    return key_low, key_high

# ----------------- 4. MAIN TRADING BOT -----------------
def run_trading_bot():
    print(f"Gold Bot active hai... Target: 1:{int(RR_RATIO)} RR", flush=True)
    send_telegram_msg("🟡 *GOLD (XAU/USD) Trading Bot Online!*\nStrategy: 4H/15M Liquidity Sweep (1:5 RR)\nMonitoring started successfully.")
    
    buy_sweep_active = False
    buy_sweep_lowest = 0.0
    
    sell_sweep_active = False
    sell_sweep_highest = 0.0
    
    while True:
        try:
            key_low_4h, key_high_4h = get_4h_key_levels()
            
            df_15m = get_candles(interval='15m', period='2d')
            last_closed = df_15m.iloc[-2]
            
            c_open = last_closed['open']
            c_high = last_closed['high']
            c_low = last_closed['low']
            c_close = last_closed['close']
            
            print(f"[STATUS] XAU/USD: ${c_close:.2f} | 4H Range: [${key_low_4h:.2f} - ${key_high_4h:.2f}] | Scan OK", flush=True)
            
            # --- BUY (LONG) LOGIC ---
            if c_low < key_low_4h and not buy_sweep_active:
                buy_sweep_active = True
                buy_sweep_lowest = c_low
                msg = f"⚠️ *GOLD LIQUIDITY SWEEP (LOW)*\nPrice ne 4H Low (${key_low_4h:.2f}) sweep kiya!\nLowest Low: ${buy_sweep_lowest:.2f}\nReversal confirmation ka wait kar rahe hain..."
                print(msg, flush=True)
                send_telegram_msg(msg)

            if buy_sweep_active:
                if c_low < buy_sweep_lowest:
                    buy_sweep_lowest = c_low

                if c_close > c_open:
                    entry_price = c_close
                    stop_loss = buy_sweep_lowest - SL_BUFFER
                    risk = entry_price - stop_loss
                    
                    if risk > 0:
                        take_profit = entry_price + (risk * RR_RATIO)
                        alert = (
                            f"🚀 *GOLD BUY ENTRY SIGNAL (1:5 RR)*\n"
                            f"-----------------------------\n"
                            f"📈 *Entry:* ${entry_price:.2f}\n"
                            f"🛑 *Stop Loss:* ${stop_loss:.2f}\n"
                            f"🎯 *Take Profit:* ${take_profit:.2f}\n"
                            f"📦 *Risk/Reward:* 1:{int(RR_RATIO)}\n"
                            f"-----------------------------"
                        )
                        print(alert, flush=True)
                        send_telegram_msg(alert)
                        buy_sweep_active = False
                        time.sleep(1800)  # 30 min cooldown
            
            # --- SELL (SHORT) LOGIC ---
            if c_high > key_high_4h and not sell_sweep_active:
                sell_sweep_active = True
                sell_sweep_highest = c_high
                msg = f"⚠️ *GOLD LIQUIDITY SWEEP (HIGH)*\nPrice ne 4H High (${key_high_4h:.2f}) sweep kiya!\nHighest High: ${sell_sweep_highest:.2f}\nReversal confirmation ka wait kar rahe hain..."
                print(msg, flush=True)
                send_telegram_msg(msg)

            if sell_sweep_active:
                if c_high > sell_sweep_highest:
                    sell_sweep_highest = c_high

                if c_close < c_open:
                    entry_price = c_close
                    stop_loss = sell_sweep_highest + SL_BUFFER
                    risk = stop_loss - entry_price
                    
                    if risk > 0:
                        take_profit = entry_price - (risk * RR_RATIO)
                        alert = (
                            f"🔻 *GOLD SELL ENTRY SIGNAL (1:5 RR)*\n"
                            f"-----------------------------\n"
                            f"📉 *Entry:* ${entry_price:.2f}\n"
                            f"🛑 *Stop Loss:* ${stop_loss:.2f}\n"
                            f"🎯 *Take Profit:* ${take_profit:.2f}\n"
                            f"📦 *Risk/Reward:* 1:{int(RR_RATIO)}\n"
                            f"-----------------------------"
                        )
                        print(alert, flush=True)
                        send_telegram_msg(alert)
                        sell_sweep_active = False
                        time.sleep(1800)  # 30 min cooldown
            
            time.sleep(30)
            
        except Exception as e:
            print(f"Gold loop error: {e}", flush=True)
            time.sleep(15)

if __name__ == '__main__':
    t = threading.Thread(target=start_web_server)
    t.daemon = True
    t.start()
    run_trading_bot()
    

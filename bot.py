import ccxt
import time
import pandas as pd
import threading
import requests
from datetime import datetime, timezone, timedelta
from flask import Flask

TELEGRAM_BOT_TOKEN = "8895341894:AAEE-p0_Ylj6RFmqr06nx5xNT7vzyBaBTqI"
TELEGRAM_CHAT_ID = "998154896"

def send_telegram_msg(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Telegram error: {e}", flush=True)

app = Flask(__name__)
@app.route('/')
def home():
    return "XAUUSD Gold Rate-Limited Safe Bot Active!"

def start_web_server():
    app.run(host='0.0.0.0', port=10000)

# Kraken with rate limit safety
exchange = ccxt.kraken({'enableRateLimit': True, 'rateLimit': 2000})
SYMBOL = 'PAXG/USD'
RR_RATIO = 5.0
SL_BUFFER = 1.5

KEY_LEVELS = [4264.0, 4280.0, 4300.0, 4305.6, 4311.0, 4325.0, 4338.0, 4344.0]
level_alert_cooldown = {lvl: 0 for lvl in KEY_LEVELS}

stats = {'total_trades': 0, 'wins': 0, 'losses': 0, 'total_r': 0.0}
active_trade = None
last_report_date = ""

cached_pdh = None
cached_pdl = None
cached_atr = None
last_daily_fetch_date = ""

def get_candles(timeframe, limit=50):
    try:
        time.sleep(1.5)  # Rate limit safety delay
        ohlcv = exchange.fetch_ohlcv(SYMBOL, timeframe=timeframe, limit=limit)
        return pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    except Exception as e:
        print(f"Kraken fetch error ({timeframe}): {e}", flush=True)
        return None

def update_daily_levels():
    global cached_pdh, cached_pdl, cached_atr, last_daily_fetch_date
    now_ist = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
    today_str = now_ist.strftime("%Y-%m-%d")
    
    # दिन में केवल एक बार डेली डेटा फेच करेंगे ताकि API ब्लॉक न हो
    if last_daily_fetch_date != today_str or cached_pdh is None:
        df_daily = get_candles('1d', limit=20)
        if df_daily is not None and len(df_daily) >= 16:
            prev_day = df_daily.iloc[-2]
            cached_pdh = prev_day['high']
            cached_pdl = prev_day['low']
            high_low = df_daily['high'] - df_daily['low']
            high_close = (df_daily['high'] - df_daily['close'].shift()).abs()
            low_close = (df_daily['low'] - df_daily['close'].shift()).abs()
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            cached_atr = tr.iloc[-15:-1].mean()
            last_daily_fetch_date = today_str
            print(f"[DAILY CACHED] PDH: {cached_pdh} | PDL: {cached_pdl} | ATR: {cached_atr}", flush=True)

def run_trading_bot():
    global active_trade, stats, last_report_date
    print("Gold Bot running with safe rate-limits...", flush=True)
    send_telegram_msg("🟡 *GOLD Safe-Mode Bot Online!*\n• Kraken Rate-Limits Fixed.\n• 3:00 PM ATR & Retests Active.")

    last_candle_time = None

    while True:
        try:
            update_daily_levels()

            now_ist = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
            today_str = now_ist.strftime("%Y-%m-%d")

            # 15M कैंडल डेटा
            df_15m = get_candles('15m', limit=25)
            if df_15m is None or len(df_15m) < 5:
                time.sleep(20)
                continue

            last_closed = df_15m.iloc[-2]
            current_price = df_15m.iloc[-1]['close']
            candle_time = last_closed['timestamp']

            # 3:00 PM IST ATR रिपोर्ट (दोपहर 3 बजे के बाद दिन में 1 बार तुरंत)
            if now_ist.hour >= 15 and last_report_date != today_str and cached_atr is not None:
                recent_bars = df_15m.iloc[-20:]
                cdh = recent_bars['high'].max()
                cdl = recent_bars['low'].min()
                expected = max(10.0, cached_atr - 30.0)
                moved = cdh - cdl
                rem = max(0.0, expected - moved)
                send_telegram_msg(
                    f"🕒 *[GOLD 3:00 PM ATR REPORT]*\n"
                    f"-----------------------------------\n"
                    f"📊 *14-Day ATR:* ${cached_atr:.2f}\n"
                    f"🎯 *Expected Range (ATR-30):* ${expected:.2f}\n"
                    f"📍 *CDH:* ${cdh:.2f} | *CDL:* ${cdl:.2f}\n"
                    f"📏 *Moved So Far:* ${moved:.2f}\n"
                    f"⚡ *Remaining Move:* *${rem:.2f}*\n"
                    f"-----------------------------------\n"
                    f"📈 High Target: ${cdh + rem:.2f}\n"
                    f"📉 Low Target: ${cdl - rem:.2f}\n"
                    f"-----------------------------------"
                )
                last_report_date = today_str

            # LIVE SL / TP CHECK
            if active_trade is not None:
                side, entry, sl, tp = active_trade['side'], active_trade['entry'], active_trade['sl'], active_trade['tp']
                if side == 'BUY':
                    if current_price >= tp:
                        stats['wins'] += 1; stats['total_trades'] += 1
                        send_telegram_msg(f"🎯 *[GOLD TP HIT]* 🏆 +500% ROI (+5R)\nExit: ${current_price:.2f}")
                        active_trade = None
                    elif current_price <= sl:
                        stats['losses'] += 1; stats['total_trades'] += 1
                        send_telegram_msg(f"🛑 *[GOLD SL HIT]* ❌ -100% ROI (-1R)\nExit: ${current_price:.2f}")
                        active_trade = None
                elif side == 'SELL':
                    if current_price <= tp:
                        stats['wins'] += 1; stats['total_trades'] += 1
                        send_telegram_msg(f"🎯 *[GOLD TP HIT]* 🏆 +500% ROI (+5R)\nExit: ${current_price:.2f}")
                        active_trade = None
                    elif current_price <= sl:
                        stats['losses'] += 1; stats['total_trades'] += 1
                        send_telegram_msg(f"🛑 *[GOLD SL HIT]* ❌ -100% ROI (-1R)\nExit: ${current_price:.2f}")
                        active_trade = None

            # 15M CANDLE CLOSE EXECUTION
            if candle_time != last_candle_time:
                last_candle_time = candle_time
                c_open, c_high, c_low, c_close = last_closed['open'], last_closed['high'], last_closed['low'], last_closed['close']
                now_ts = time.time()

                for lvl in KEY_LEVELS:
                    if (now_ts - level_alert_cooldown[lvl]) > 1800:
                        if c_low <= (lvl + 1.2) and c_close > lvl and c_close > c_open and (c_close - lvl) <= 4.0:
                            send_telegram_msg(f"🛡️ *[GOLD DIRECT SUPPORT RETEST]*\nLevel: ${lvl:.2f}\nPrice ने लेवल रीटेस्ट करके तुरंत बुलिश क्लोज़ दी!\nEntry: ${c_close:.2f}")
                            level_alert_cooldown[lvl] = now_ts
                        elif c_high >= (lvl - 1.2) and c_close < lvl and c_close < c_open and (lvl - c_close) <= 4.0:
                            send_telegram_msg(f"🧱 *[GOLD DIRECT RESISTANCE RETEST]*\nLevel: ${lvl:.2f}\nPrice ने लेवल रीटेस्ट करके तुरंत बेयरिश क्लोज़ दी!\nEntry: ${c_close:.2f}")
                            level_alert_cooldown[lvl] = now_ts

                if cached_pdh and cached_pdl and active_trade is None:
                    if c_high > cached_pdh and c_close < cached_pdh and c_close < c_open:
                        sl = c_high + SL_BUFFER
                        risk = sl - c_close
                        if risk > 0:
                            tp = c_close - (risk * RR_RATIO)
                            active_trade = {'side': 'SELL', 'entry': c_close, 'sl': sl, 'tp': tp}
                            send_telegram_msg(f"🔻 *[GOLD PDH SWEEP SELL (1:5 RR)]*\nEntry: ${c_close:.2f} | SL: ${sl:.2f} | TP: ${tp:.2f}")
                    elif c_low < cached_pdl and c_close > cached_pdl and c_close > c_open:
                        sl = c_low - SL_BUFFER
                        risk = c_close - sl
                        if risk > 0:
                            tp = c_close + (risk * RR_RATIO)
                            active_trade = {'side': 'BUY', 'entry': c_close, 'sl': sl, 'tp': tp}
                            send_telegram_msg(f"🚀 *[GOLD PDL SWEEP BUY (1:5 RR)]*\nEntry: ${c_close:.2f} | SL: ${sl:.2f} | TP: ${tp:.2f}")

            time.sleep(30)

        except Exception as e:
            print(f"Gold loop error: {e}", flush=True)
            time.sleep(20)

if __name__ == '__main__':
    t = threading.Thread(target=start_web_server)
    t.daemon = True
    t.start()
    run_trading_bot()

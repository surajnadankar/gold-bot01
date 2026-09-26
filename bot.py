import ccxt
import time
import pandas as pd
import threading
import requests
from datetime import datetime, timezone, timedelta
from flask import Flask

# ----------------- 1. TELEGRAM CONFIG -----------------
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
        print(f"Telegram error: {e}", flush=True)

# ----------------- 2. WEB SERVER -----------------
app = Flask(__name__)

@app.route('/')
def home():
    return "XAUUSD Gold PDH/PDL Sweep & ATR Bot is running!"

def start_web_server():
    app.run(host='0.0.0.0', port=10000)

# ----------------- 3. EXCHANGE & CONFIG -----------------
exchange = ccxt.kraken({'enableRateLimit': True})
SYMBOL = 'PAXG/USD'     # Spot Gold (XAU/USD)
RR_RATIO = 5.0
SL_BUFFER = 1.5

stats = {'total_trades': 0, 'wins': 0, 'losses': 0, 'total_r': 0.0}
active_trade = None

# State variables
atr_reported_today = False
pdh_break_tracker = {'broken_above': False, 'bars': 0}
pdl_break_tracker = {'broken_below': False, 'bars': 0}

# ----------------- 4. DATA FUNCTIONS -----------------
def get_candles(timeframe, limit=50):
    try:
        ohlcv = exchange.fetch_ohlcv(SYMBOL, timeframe=timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        return df
    except Exception as e:
        print(f"Fetch error: {e}", flush=True)
        return None

def get_pdh_pdl_and_atr():
    df_daily = get_candles('1d', limit=20)
    if df_daily is None or len(df_daily) < 16:
        return None, None, None
    
    # Previous Day (कल की क्लोज्ड कैंडल)
    prev_day = df_daily.iloc[-2]
    pdh = prev_day['high']
    pdl = prev_day['low']
    
    # 14-day Daily ATR
    high_low = df_daily['high'] - df_daily['low']
    high_close = (df_daily['high'] - df_daily['close'].shift()).abs()
    low_close = (df_daily['low'] - df_daily['close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr_14 = tr.iloc[-15:-1].mean()
    
    return pdh, pdl, atr_14

def get_current_day_range():
    # आज (UTC 00:00 से) का 15m डेटा
    df_15m = get_candles('15m', limit=96)
    if df_15m is None:
        return None, None
    now_utc = datetime.now(timezone.utc)
    today_start = datetime(now_utc.year, now_utc.month, now_utc.day, tzinfo=timezone.utc)
    today_ts = int(today_start.timestamp() * 1000)
    
    today_candles = df_15m[df_15m['timestamp'] >= today_ts]
    if len(today_candles) == 0:
        return None, None
    cdh = today_candles['high'].max()
    cdl = today_candles['low'].min()
    return cdh, cdl

# ----------------- 5. MAIN TRADING LOOP -----------------
def run_trading_bot():
    global active_trade, stats, atr_reported_today
    print("Gold Bot active...", flush=True)
    send_telegram_msg("🟡 *GOLD (XAU/USD) Bot Online!*\n• Levels: PDH/PDL Sweeps & Retests (1:5 RR)\n• 3:00 PM CDH/CDL & Daily ATR Alerts Active.")

    last_candle_time = None

    while True:
        try:
            now_ist = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
            
            # --- 3:00 PM IST ATR & CDH/CDL REPORT (NO ENTRY, ALERT ONLY) ---
            if now_ist.hour == 15 and now_ist.minute <= 5 and not atr_reported_today:
                pdh, pdl, atr_14 = get_pdh_pdl_and_atr()
                cdh, cdl = get_current_day_range()
                if atr_14 and cdh and cdl:
                    expected_range = max(10.0, atr_14 - 30.0) # $30 माइनस करके टारगेट रेंज
                    moved = cdh - cdl
                    remaining = max(0.0, expected_range - moved)
                    
                    report = (
                        f"🕒 *[GOLD 3:00 PM CDH/CDL & ATR REPORT]*\n"
                        f"-----------------------------------\n"
                        f"📊 *14-Day ATR:* ${atr_14:.2f}\n"
                        f"🎯 *Expected Range (ATR-30):* ${expected_range:.2f}\n"
                        f"📍 *CDH (Day High at 3 PM):* ${cdh:.2f}\n"
                        f"📍 *CDL (Day Low at 3 PM):* ${cdl:.2f}\n"
                        f"📏 *Moved So Far:* ${moved:.2f}\n"
                        f"⚡ *Remaining Rally/Fall:* *${remaining:.2f}*\n"
                        f"-----------------------------------\n"
                        f"📈 High Expansion Target: ${cdh + remaining:.2f}\n"
                        f"📉 Low Expansion Target: ${cdl - remaining:.2f}\n"
                        f"-----------------------------------"
                    )
                    send_telegram_msg(report)
                    atr_reported_today = True

            # 3:00 PM अलर्ट को अगले दिन के लिए रीसेट करना
            if now_ist.hour == 16:
                atr_reported_today = False

            # --- LIVE MARKET DATA ---
            df_15m = get_candles('15m', limit=20)
            if df_15m is None or len(df_15m) < 5:
                time.sleep(15)
                continue

            last_closed = df_15m.iloc[-2]
            current_price = df_15m.iloc[-1]['close']
            candle_time = last_closed['timestamp']

            # --- LIVE SL / TP CHECK ---
            if active_trade is not None:
                side = active_trade['side']
                entry = active_trade['entry']
                sl = active_trade['sl']
                tp = active_trade['tp']

                if side == 'BUY':
                    if current_price >= tp:
                        stats['wins'] += 1
                        stats['total_trades'] += 1
                        win_rate = (stats['wins'] / stats['total_trades']) * 100
                        send_telegram_msg(f"🎯 *[GOLD TP HIT]* 🏆\nBUY Exit: ${current_price:.2f} | +500% ROI (+5R)\nWin Rate: {win_rate:.1f}%")
                        active_trade = None
                    elif current_price <= sl:
                        stats['losses'] += 1
                        stats['total_trades'] += 1
                        win_rate = (stats['wins'] / stats['total_trades']) * 100
                        send_telegram_msg(f"🛑 *[GOLD SL HIT]* ❌\nBUY Exit: ${current_price:.2f} | -100% ROI (-1R)\nWin Rate: {win_rate:.1f}%")
                        active_trade = None

                elif side == 'SELL':
                    if current_price <= tp:
                        stats['wins'] += 1
                        stats['total_trades'] += 1
                        win_rate = (stats['wins'] / stats['total_trades']) * 100
                        send_telegram_msg(f"🎯 *[GOLD TP HIT]* 🏆\nSELL Exit: ${current_price:.2f} | +500% ROI (+5R)\nWin Rate: {win_rate:.1f}%")
                        active_trade = None
                    elif current_price >= sl:
                        stats['losses'] += 1
                        stats['total_trades'] += 1
                        win_rate = (stats['wins'] / stats['total_trades']) * 100
                        send_telegram_msg(f"🛑 *[GOLD SL HIT]* ❌\nSELL Exit: ${current_price:.2f} | -100% ROI (-1R)\nWin Rate: {win_rate:.1f}%")
                        active_trade = None

            # --- 15M CANDLE CLOSE EXECUTION (PDH / PDL RULES) ---
            if candle_time != last_candle_time:
                last_candle_time = candle_time
                c_open = last_closed['open']
                c_high = last_closed['high']
                c_low = last_closed['low']
                c_close = last_closed['close']

                pdh, pdl, _ = get_pdh_pdl_and_atr()
                if pdh and pdl:
                    # 1. PDH Sweep Reversal (Short)
                    if c_high > pdh and c_close < pdh and c_close < c_open:
                        sl = c_high + SL_BUFFER
                        risk = sl - c_close
                        if risk > 0 and active_trade is None:
                            tp = c_close - (risk * RR_RATIO)
                            active_trade = {'side': 'SELL', 'entry': c_close, 'sl': sl, 'tp': tp}
                            send_telegram_msg(f"🔻 *[GOLD PDH SWEEP SELL ENTRY (1:5 RR)]*\nPrice ने PDH (${pdh:.2f}) स्वीप करके नीचे रिजेक्शन क्लोज़ दी!\nEntry: ${c_close:.2f} | SL: ${sl:.2f} | TP: ${tp:.2f}")

                    # 2. PDL Sweep Reversal (Long)
                    elif c_low < pdl and c_close > pdl and c_close > c_open:
                        sl = c_low - SL_BUFFER
                        risk = c_close - sl
                        if risk > 0 and active_trade is None:
                            tp = c_close + (risk * RR_RATIO)
                            active_trade = {'side': 'BUY', 'entry': c_close, 'sl': sl, 'tp': tp}
                            send_telegram_msg(f"🚀 *[GOLD PDL SWEEP BUY ENTRY (1:5 RR)]*\nPrice ने PDL (${pdl:.2f}) स्वीप करके ऊपर बाउंस क्लोज़ दी!\nEntry: ${c_close:.2f} | SL: ${sl:.2f} | TP: ${tp:.2f}")

                    # 3. PDH Breakout & Retest (Long)
                    if c_close > (pdh + 1.0):
                        pdh_break_tracker['broken_above'] = True
                        pdh_break_tracker['bars'] += 1
                    elif pdh_break_tracker['broken_above']:
                        pdh_break_tracker['bars'] += 1
                        if pdh_break_tracker['bars'] >= 3 and c_low <= (pdh + 0.5) and c_close > pdh and c_close > c_open:
                            sl = c_low - SL_BUFFER
                            risk = c_close - sl
                            if risk > 0 and active_trade is None:
                                tp = c_close + (risk * RR_RATIO)
                                active_trade = {'side': 'BUY', 'entry': c_close, 'sl': sl, 'tp': tp}
                                send_telegram_msg(f"🚀 *[GOLD PDH RETEST BUY ENTRY (1:5 RR)]*\nPDH टूटकर सपोर्ट बना, रीटेस्ट कन्फर्म!\nEntry: ${c_close:.2f} | SL: ${sl:.2f} | TP: ${tp:.2f}")
                                pdh_break_tracker['broken_above'] = False

                    # 4. PDL Breakdown & Retest (Short)
                    if c_close < (pdl - 1.0):
                        pdl_break_tracker['broken_below'] = True
                        pdl_break_tracker['bars'] += 1
                    elif pdl_break_tracker['broken_below']:
                        pdl_break_tracker['bars'] += 1
                        if pdl_break_tracker['bars'] >= 3 and c_high >= (pdl - 0.5) and c_close < pdl and c_close < c_open:
                            sl = c_high + SL_BUFFER
                            risk = sl - c_close
                            if risk > 0 and active_trade is None:
                                tp = c_close - (risk * RR_RATIO)
                                active_trade = {'side': 'SELL', 'entry': c_close, 'sl': sl, 'tp': tp}
                                send_telegram_msg(f"🔻 *[GOLD PDL RETEST SELL ENTRY (1:5 RR)]*\nPDL टूटकर रेजिस्टेंस बना, रीटेस्ट कन्फर्म!\nEntry: ${c_close:.2f} | SL: ${sl:.2f} | TP: ${tp:.2f}")
                                pdl_break_tracker['broken_below'] = False

            time.sleep(25)

        except Exception as e:
            print(f"Gold loop error: {e}", flush=True)
            time.sleep(15)

if __name__ == '__main__':
    t = threading.Thread(target=start_web_server)
    t.daemon = True
    t.start()
    run_trading_bot()
                    

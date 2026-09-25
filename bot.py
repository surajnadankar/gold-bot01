import ccxt
import time
import pandas as pd
import threading
import requests
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
    return "XAUUSD Clean Retest & Swing Bot is Running!"

def start_web_server():
    app.run(host='0.0.0.0', port=10000)

# ----------------- 3. EXCHANGE & CONFIG -----------------
exchange = ccxt.kraken({'enableRateLimit': True})
SYMBOL = 'PAXG/USD'
RR_RATIO = 5.0
SL_BUFFER = 1.5

KEY_LEVELS = [4264.0, 4280.0, 4300.0, 4305.6, 4311.0, 4325.0, 4338.0, 4344.0]

stats = {'total_trades': 0, 'wins': 0, 'losses': 0, 'total_r': 0.0}
active_trade = None

# Track level states: {'broken_above': bool, 'bars_since_break': int, 'last_alert_time': timestamp}
level_tracking = {lvl: {'broken_above': None, 'bars': 0, 'last_alert': 0} for lvl in KEY_LEVELS}

# ----------------- 4. DATA FUNCTIONS -----------------
def get_candles(timeframe, limit=50):
    try:
        ohlcv = exchange.fetch_ohlcv(SYMBOL, timeframe=timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        return df
    except Exception as e:
        print(f"Kraken fetch error: {e}", flush=True)
        return None

def get_4h_key_levels():
    df_4h = get_candles('4h', limit=25)
    if df_4h is None or len(df_4h) < 15:
        return None, None
    key_low = df_4h['low'].iloc[-11:-1].min()
    key_high = df_4h['high'].iloc[-11:-1].max()
    return key_low, key_high

# ----------------- 5. MAIN TRADING & TRACKING LOOP -----------------
def run_trading_bot():
    global active_trade, stats
    print("Gold Retest Bot Active...", flush=True)
    send_telegram_msg("🟡 *GOLD (XAU/USD) Clean Alert Bot Online!*\n• Spams Removed: Alerts only on confirmed 15M Retests.\n• Strategy: 4H/15M Liquidity Sweep (1:5 RR).")

    last_candle_time = None
    buy_sweep_active = False
    buy_sweep_lowest = 0.0
    sell_sweep_active = False
    sell_sweep_highest = 0.0

    while True:
        try:
            df_15m = get_candles('15m', limit=20)
            if df_15m is None or len(df_15m) < 5:
                time.sleep(10)
                continue

            last_closed = df_15m.iloc[-2]
            current_bar = df_15m.iloc[-1]
            current_price = current_bar['close']
            candle_time = last_closed['timestamp']

            # === A. ACTIVE TRADE SL/TP CHECK (हर 20 सेकंड में लाइव) ===
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

            # === B. CANDLE-CLOSE BASED LOGIC (सिर्फ हर 15 मिनट की कैंडल बंद होने पर) ===
            if candle_time != last_candle_time:
                last_candle_time = candle_time
                c_open = last_closed['open']
                c_high = last_closed['high']
                c_low = last_closed['low']
                c_close = last_closed['close']
                now_ts = time.time()

                # --- 1. CLEAN KEY LEVEL RETEST CONFIRMATION ---
                for lvl in KEY_LEVELS:
                    tracker = level_tracking[lvl]

                    # Breakout detect (at least $1.50 clear close)
                    if c_close > (lvl + 1.0) and tracker['broken_above'] is not True:
                        tracker['broken_above'] = True
                        tracker['bars'] = 0
                    elif c_close < (lvl - 1.0) and tracker['broken_above'] is not False:
                        tracker['broken_above'] = False
                        tracker['bars'] = 0
                    else:
                        tracker['bars'] += 1

                    # Retest check: सिर्फ तब जब ब्रेकआउट के बाद 3 से 12 कैंडल (45min से 3 घंटे) बीत चुके हों
                    if tracker['bars'] >= 3 and (now_ts - tracker['last_alert']) > 3600:
                        # Case 1: नीचे से ऊपर तोड़ा था, अब नीचे आकर सपोर्ट लिया और Green Candle बनी
                        if tracker['broken_above'] is True and c_low <= (lvl + 0.8) and c_close > lvl and c_close > c_open:
                            msg = (
                                f"🛡️ *[GOLD CONFIRMED SUPPORT RETEST]*\n"
                                f"-----------------------------------\n"
                                f"Level: ${lvl:.2f}\n"
                                f"Action: Price ने लेवल तोड़ा, 45+ मिनट होल्ड किया और अब सपोर्ट टेस्ट करके Bullish क्लोज़ दी है!\n"
                                f"Candle Close: ${c_close:.2f}\n"
                                f"-----------------------------------"
                            )
                            send_telegram_msg(msg)
                            tracker['last_alert'] = now_ts

                        # Case 2: ऊपर से नीचे तोड़ा था, अब ऊपर जाकर रिजेक्ट हुआ और Red Candle बनी
                        elif tracker['broken_above'] is False and c_high >= (lvl - 0.8) and c_close < lvl and c_close < c_open:
                            msg = (
                                f"🧱 *[GOLD CONFIRMED RESISTANCE RETEST]*\n"
                                f"---------------------------------------\n"
                                f"Level: ${lvl:.2f}\n"
                                f"Action: Price नीचे टूटा था, अब वापस जाकर लेवल टेस्ट किया और Bearish रिजेक्शन क्लोज़ दी है!\n"
                                f"Candle Close: ${c_close:.2f}\n"
                                f"---------------------------------------"
                            )
                            send_telegram_msg(msg)
                            tracker['last_alert'] = now_ts

                # --- 2. 4H/15M LIQUIDITY SWEEP ENTRY STRATEGY ---
                key_low_4h, key_high_4h = get_4h_key_levels()
                if key_low_4h is not None:
                    if c_low < key_low_4h and not buy_sweep_active:
                        buy_sweep_active = True
                        buy_sweep_lowest = c_low
                        send_telegram_msg(f"⚠️ *GOLD LIQUIDITY SWEEP (LOW)*\n4H Low (${key_low_4h:.2f}) sweep हुआ!\nLowest: ${buy_sweep_lowest:.2f}")

                    if buy_sweep_active:
                        if c_low < buy_sweep_lowest:
                            buy_sweep_lowest = c_low
                        if c_close > c_open:
                            entry = c_close
                            sl = buy_sweep_lowest - SL_BUFFER
                            risk = entry - sl
                            if risk > 0 and active_trade is None:
                                tp = entry + (risk * RR_RATIO)
                                active_trade = {'side': 'BUY', 'entry': entry, 'sl': sl, 'tp': tp, 'risk': risk}
                                send_telegram_msg(f"🚀 *GOLD BUY ENTRY (1:5 RR)*\nEntry: ${entry:.2f}\nSL: ${sl:.2f}\nTP: ${tp:.2f}")
                                buy_sweep_active = False

                    if c_high > key_high_4h and not sell_sweep_active:
                        sell_sweep_active = True
                        sell_sweep_highest = c_high
                        send_telegram_msg(f"⚠️ *GOLD LIQUIDITY SWEEP (HIGH)*\n4H High (${key_high_4h:.2f}) sweep हुआ!\nHighest: ${sell_sweep_highest:.2f}")

                    if sell_sweep_active:
                        if c_high > sell_sweep_highest:
                            sell_sweep_highest = c_high
                        if c_close < c_open:
                            entry = c_close
                            sl = sell_sweep_highest + SL_BUFFER
                            risk = sl - entry
                            if risk > 0 and active_trade is None:
                                tp = entry - (risk * RR_RATIO)
                                active_trade = {'side': 'SELL', 'entry': entry, 'sl': sl, 'tp': tp, 'risk': risk}
                                send_telegram_msg(f"🔻 *GOLD SELL ENTRY (1:5 RR)*\nEntry: ${entry:.2f}\nSL: ${sl:.2f}\nTP: ${tp:.2f}")
                                sell_sweep_active = False

            time.sleep(20)

        except Exception as e:
            print(f"Gold loop error: {e}", flush=True)
            time.sleep(15)

if __name__ == '__main__':
    t = threading.Thread(target=start_web_server)
    t.daemon = True
    t.start()
    run_trading_bot()
    

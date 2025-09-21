# /main.py
import machine
import network
import time
import ujson
import urequests
import os
import socket

# Import the corrected library class and button helper
from lib.epd2in66b import EPD_2in9_B # Note: Class name is EPD_2in9_B in the file
from lib.button import Button

# --- Pin Definitions ---
# These are fixed by the library and our wiring plan
# E-Paper Display Pins (SPI1)
# EPD_CS_PIN = 9
# EPD_DC_PIN = 8
# EPD_RST_PIN = 12
# EPD_BUSY_PIN = 13
# EPD_CLK_PIN = 10
# EPD_DIN_PIN = 11

# Button Pins
BUTTON_A_PIN = 14 # Cycle Coin
BUTTON_B_PIN = 15 # Sleep/Wake / Reset

# Wi-Fi Power Control Pin
WIFI_POWER_PIN = 23

# --- Global Variables ---
settings = {}
current_coin_index = 0
epd = None
state = "INIT" # Possible states: INIT, CONFIG, RUN, SLEEP, ERROR

# --- CoinGecko API Configuration ---
API_URL = "https://api.coingecko.com/api/v3/simple/price"
COIN_LIST = {
    "Bitcoin": "bitcoin", "Ethereum": "ethereum", "Cardano": "cardano",
    "BNB": "binancecoin", "XRP": "ripple", "Solana": "solana",
    "Dogecoin": "dogecoin", "Tron": "tron", "Sui": "sui",
    "Chainlink": "chainlink", "Avalanche": "avalanche-2", "Monero": "monero",
    "Litecoin": "litecoin", "Polkadot": "polkadot", "Shiba Inu": "shiba-inu",
    "Cronos": "crypto-com-chain", "Toncoin": "the-open-network", "Bitcoin Cash": "bitcoin-cash"
}
COIN_FRIENDLY_NAMES = list(COIN_LIST.keys())

# --- Helper Functions ---
def init_display():
    global epd
    epd = EPD_2in9_B()

def display_message(line1, line2="", line3=""):
    epd.Clear(0xff, 0xff) # Clear both buffers to white
    # Draw black text on the black framebuffer. 0x00 is the color to draw.
    epd.imageblack.text(line1, 5, 10, 0x00)
    epd.imageblack.text(line2, 5, 40, 0x00)
    epd.imageblack.text(line3, 5, 70, 0x00)
    epd.display()

def power_wifi(is_on):
    wifi_power = machine.Pin(WIFI_POWER_PIN, machine.Pin.OUT)
    wifi_power.value(1 if is_on else 0)
    time.sleep_ms(200)

def load_settings():
    try:
        with open('settings.json', 'r') as f:
            return ujson.load(f)
    except (OSError, ValueError):
        return None

def save_settings(data):
    with open('settings.json', 'w') as f:
        ujson.dump(data, f)

def connect_wifi(ssid, password):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(ssid, password)
    
    max_wait = 15
    while max_wait > 0:
        if wlan.status() < 0 or wlan.status() >= 3:
            break
        max_wait -= 1
        display_message("Connecting to WiFi...", f"SSID: {ssid}", f"Retries left: {max_wait}")
        time.sleep(1)
        
    if wlan.status()!= 3:
        display_message("WiFi Connection Failed", "Check credentials.", "Resetting to re-enter.")
        time.sleep(5)
        reset_device_callback(None) # Call reset function
        return None
    
    display_message("WiFi Connected!", f"IP: {wlan.ifconfig()}")
    time.sleep(2)
    return wlan

def fetch_crypto_prices(coin_ids):
    ids_param = ",".join(coin_ids)
    url = f"{API_URL}?ids={ids_param}&vs_currencies=usd&include_24hr_change=true"
    try:
        response = urequests.get(url, timeout=10)
        data = response.json()
        response.close()
        return data
    except Exception as e:
        print(f"API Error: {e}")
        return None

def display_price_data(data, coin_id):
    coin_data = data.get(coin_id)
    if not coin_data:
        display_message(f"No data for {coin_id}")
        return

    price = coin_data.get('usd', 'N/A')
    change_24h = coin_data.get('usd_24h_change', 0)
    
    friendly_name = "Unknown Coin"
    for name, id_val in COIN_LIST.items():
        if id_val == coin_id:
            friendly_name = name
            break
    
    price_str = f"${price:,.2f}" if isinstance(price, (int, float)) else "N/A"
    change_str = f"{change_24h:+.2f}%" if isinstance(change_24h, (int, float)) else "N/A"
    
    epd.Clear(0xff, 0xff)

    epd.imageblack.text(friendly_name, 10, 10, 0x00)
    epd.imageblack.text(price_str, 10, 50, 0x00)

    if isinstance(change_24h, (int, float)) and change_24h < 0:
        epd.imagered.text(change_str, 10, 100, 0x00)
    else:
        epd.imageblack.text(change_str, 10, 100, 0x00)
            
    epd.display()

def go_to_sleep():
    global state
    state = "SLEEP"
    display_message("Entering sleep mode...", f"Waking in {settings['refresh']} min")
    epd.sleep()
    time.sleep(2)
    power_wifi(False)
    sleep_duration_ms = int(settings['refresh']) * 60 * 1000
    machine.deepsleep(sleep_duration_ms)

# --- Button Callbacks ---
def cycle_coin_callback(pin):
    global current_coin_index, state
    if state == "RUN":
        current_coin_index = (current_coin_index + 1) % len(settings['coins'])
        main_loop()

def sleep_wake_callback(pin):
    go_to_sleep()

def reset_device_callback(pin):
    display_message("Resetting device...", "Deleting settings.")
    time.sleep(2)
    try:
        os.remove('settings.json')
    except OSError:
        pass
    machine.reset()

# --- Configuration Web Server ---
def run_config_server():
    global state
    state = "CONFIG"
    power_wifi(True)
    ap = network.WLAN(network.AP_IF)
    ap.config(essid="PicoCryptoTicker", password="password")
    ap.active(True)

    while not ap.isconnected():
        pass

    display_message("Config Mode", "Connect to 'PicoCryptoTicker'", f"Go to {ap.ifconfig()}")

    addr = socket.getaddrinfo('0.0.0.0', 80)[-1]
    s = socket.socket()
    s.bind(addr)
    s.listen(1)

    while True:
        cl, addr = s.accept()
        request = cl.recv(1024).decode('utf-8')
        
        if 'POST /submit' in request:
            form_data_raw = request.split('\r\n\r\n')[-1]
            form_data = {}
            for item in form_data_raw.split('&'):
                key, value = item.split('=')
                value = value.replace('+', ' ').replace('%40', '@').replace('%2F', '/')
                form_data[key] = value

            new_settings = {
                'ssid': form_data.get('ssid'),
                'password': form_data.get('password'),
                'refresh': form_data.get('refresh'),
                'coins': for i in range(1, 6) if form_data.get(f'coin{i}') and form_data.get(f'coin{i}')!= '---']
            }
            save_settings(new_settings)
            
            cl.send('HTTP/1.0 200 OK\r\nContent-type: text/html\r\n\r\n')
            cl.send('<html><body><h1>Settings Saved!</h1><p>Device will now reboot.</p></body></html>')
            cl.close()
            
            display_message("Settings Saved!", "Rebooting...")
            time.sleep(3)
            machine.reset()
            break

        html_options = "".join()
        html = f"""
        <!DOCTYPE html><html><head><title>Pico Ticker Setup</title></head>
        <body><h1>Pico Crypto Ticker Setup</h1>
        <form action="/submit" method="post">
            <h2>Wi-Fi Settings</h2>
            <label for="ssid">SSID:</label><br><input type="text" id="ssid" name="ssid"><br>
            <label for="password">Password:</label><br><input type="password" id="password" name="password"><br>
            <h2>Crypto Coins (up to 5)</h2>
            {''.join([f'<select name="coin{i}"><option>---</option>{html_options}</select><br>' for i in range(1, 6)])}
            <h2>Refresh Interval</h2>
            <select name="refresh">
                <option value="15">15 minutes</option>
                <option value="30">30 minutes</option>
                <option value="60">1 hour</option>
            </select><br><br>
            <input type="submit" value="Save Settings">
        </form></body></html>
        """
        cl.send('HTTP/1.0 200 OK\r\nContent-type: text/html\r\n\r\n')
        cl.send(html)
        cl.close()

# --- Main Application Logic ---
def main_loop():
    global state, settings, current_coin_index
    state = "RUN"
    
    power_wifi(True)
    wlan = connect_wifi(settings['ssid'], settings['password'])
    if not wlan:
        return

    coin_ids_to_fetch = settings['coins']
    price_data = fetch_crypto_prices(coin_ids_to_fetch)
    
    if price_data:
        display_price_data(price_data, settings['coins'][current_coin_index])
    else:
        display_message("API Error", "Could not fetch prices.")
        time.sleep(10)

    wlan.disconnect()
    wlan.active(False)
    go_to_sleep()

# --- Entry Point ---
if __name__ == "__main__":
    init_display()
    
    button_a = Button(BUTTON_A_PIN, callback=cycle_coin_callback)
    button_b = Button(BUTTON_B_PIN, callback=sleep_wake_callback, long_press_callback=reset_device_callback)

    settings = load_settings()
    
    if settings and settings.get('coins'):
        main_loop()
    else:
        run_config_server()

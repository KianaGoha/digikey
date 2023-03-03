# modules
import sys
from csv import reader
import webbrowser
import requests
import urllib.parse
import binascii
import os
import time
import json

from operator import itemgetter
from requests.api import request
import config


# taken from https://stackoverflow.com/questions/39858027/oauth-and-redirect-uri-in-offline-python-script
class Communicator:

    def __init__(self):
        self.client_id = config.client_id
        self.client_secret = config.client_secret
        self.server, self.port = 'localhost', 8139
        self._redirect_uri = f'https://{self.server}:{self.port}'
        self._last_request_time = 0

    def auth(self):

        params = {
            'response_type': 'code',
            'client_id': self.client_id,
            'redirect_uri': self._redirect_uri,
            'state': state
        }

        request = requests.Request('GET', AUTH, params).prepare()
        request.prepare_url(AUTH, params)
        webbrowser.open(request.url)

        token_url = input("Please ALLOW access and copy and paste the resulting URL here: ")
        query = urllib.parse.parse_qs(urllib.parse.urlparse(token_url).query)
        if not query['state'] or query['state'][0] != state:
            raise RuntimeError("State argument missing or invalid")
        code = query['code']

        params = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'grant_type': 'authorization_code',
            'code': code[0],
            'redirect_uri': self._redirect_uri
        }

        self._get_token(params)

    def _get_token(self, params):
        r = requests.post(TOKEN, params).json()
        self.token = r['access_token']
        self.refresh_token = r['refresh_token']

    def _refresh_token(self):
        params = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'grant_type': 'refresh_token',
            'refresh_token': self.refresh_token
        }

        self._get_token(params)

    def _request(self, func, url, params, sleep=5, cooldown=600):
        t = time.time()
        if t - self._last_request_time < sleep:
            time.sleep(sleep - t + self._last_request_time)

        self._last_request_time = t
        max_sleep = 16 * sleep
        params['access_token'] = self.token

        while True:
            try:
                r = func(url, params).json()
                if 'error_code' in r and r['error_code'] == 429:
                    sleep *= 2
                    time.sleep(sleep)
                    if sleep > max_sleep:
                        raise ConnectionError("Request timed out - server is busy.")
                elif 'error' in r and r['error'] == 'user_api_threshold':
                    raise ConnectionError("Too many requests")
                elif 'error' in r and r['error'] == 'invalid_token':
                    print("Refreshing token.")
                    self._refresh_token()
                    params['access_token'] = self.token
                else:
                    return r
            except ConnectionError:
                print(f"Request limit reached - waiting {cooldown // 60} minutes before retrying...")
                time.sleep(cooldown)

    def get(self, url, params):
        return self._request(requests.get, url, params)

    def post(self, url, params):
        return self._request(requests.post, url, params)


class Component:
    def __init__(self, quantity, quantity_available, stock_code, price, error_message):
        self.quantity = int(quantity)
        self.quantity_available = int(quantity_available)
        self.stock_code = stock_code
        self.price = float(price)
        self.error_message = error_message
    
    def comp_str(self):
        return f'''—————————————————————————————————————————————————
Quantity Required: \t{self.quantity}
Stock Code: \t\t{self.stock_code}
Price: \t\t\t{self.price}
—————————————————————————————————————————————————\n
'''

    def error_str(self):
        return f'''—————————————————————————————————————————————————
Quantity required: \t{self.quantity}
Stock Code: \t\t{self.stock_code}
Error: \t\t\t{self.error_message}
—————————————————————————————————————————————————\n
'''


def view_components(file):
    for comp in component_list:
        file.write(comp.comp_str())
    

def view_errors(file):
    for error in error_list:
        file.write(error.error_str())


def get_price(quantity, product_dict):
    null_price = {'BreakQuantity': 0, 'UnitPrice': 0.0, 'TotalPrice': 0.0}
    unsorted_price_list = []

    for element in product_dict['Products'][1]['StandardPricing']:
        unsorted_price_list.append(element)

    for element in product_dict['Products'][0]['StandardPricing']:
        unsorted_price_list.append(element)

    price_list = sorted(unsorted_price_list, key=itemgetter('BreakQuantity'))

    if quantity>0:
        counter = 0
        while quantity > price_list[counter]['BreakQuantity']:
            counter += 1
            if counter >= len(price_list):
                break
        return price_list[counter - 1]
    else:
        return null_price
    

def get_qty_available(product_dict):
    return max(product_dict['Products'][0]['QuantityAvailable'],product_dict['Products'][1]['QuantityAvailable'])


def get_dk_part_number(product_dict):
    return product_dict['Products'][0]['DigiKeyPartNumber']


if __name__ == '__main__':
    AUTH = 'https://sandbox-api.digikey.com/v1/oauth2/authorize'
    TOKEN = 'https://sandbox-api.digikey.com/v1/oauth2/token'

    code = ''
    component_list = []
    error_list = []
    # open file to read into as the first argument in the command line
    f = open(sys.argv[1], "r")
    bom = f.readlines()[1:]
    f.close()

    # make the number of parts you want to check for the second argument in command line
    num_parts = int(sys.argv[2])

    state = binascii.hexlify(os.urandom(20)).decode('utf-8')
    com = Communicator()
    com.auth()
    Host = 'https://sandbox-api.digikey.com/PackageTypeByQuantity/v3/Products/'
    HEADERS = {
        'X-DIGIKEY-Client-Id': com.client_id,
        'Authorization': 'Bearer '+com.token,
        'X-DIGIKEY-Locale-Site': 'UK',
        'X-DIGIKEY-Locale-Language': 'en',
        'X-DIGIKEY-Locale-Currency': 'GBP',
        'X-DIGIKEY-Locale-ShipToCountry': 'uk',
        'X-DIGIKEY-Customer-Id': '0'
    }

    # file = open("testProduct.txt", 'w')

    for line in reader(bom):
        component_info = line
        quantity = int(component_info[1]) * int(num_parts)
        stock_code = component_info[4]
        Host_URL = Host + stock_code
        PARAMS = {
            'RequestedQuantity' : str(quantity),
            'Includes' : 'Products(DigiKeyPartNumber,QuantityAvailable,StandardPricing)'
        }
        response = request(method="GET", url=Host_URL, headers=HEADERS, params=PARAMS)
        if response.status_code == 200:
            error_message = ""
            product_dict = json.loads(str(response.content)[2:-1])
            quantity_in_stock = get_qty_available(product_dict)
            DigiKeyPartNumber = get_dk_part_number(product_dict)
            unit_price = get_price(quantity, product_dict)['UnitPrice']
            total_price = get_price(quantity, product_dict)['UnitPrice'] * quantity
            component = Component(quantity, quantity_in_stock, stock_code, round(total_price, 2), "")
            component_list.append(component)

        else:
            error_message = f"Error: {response.text}"
            component = Component(quantity, 0, stock_code, 0, error_message)
            error_list.append(component)
       
    # open a file to write the prices into including all that do not match then close
    f = open("DigikeyPricing.txt", "w")
    f.write("Available Components:\n")
    view_components(f)
    f.write("\nData That Does Not Match:\n")
    view_errors(f)
    f.close()

    # open the same file to read into and store the contents of the file then print on the console
    f = open("DigikeyPricing.txt", "r")
    dk_pricing = f.read()
    f.close()
    print(dk_pricing)

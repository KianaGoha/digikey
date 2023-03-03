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
# class created for communicating with the digikey api via oauth 2 protocol
#   initialise variables for the following
#   the client id created when registering the sandbox app and stored in the config file,
#   client secret key created when registering the sandbox app and stored in config file
#   server and port variables corresponding to the callback url at time of registering with sandbox
#   redirect_uri to store the whole callback uri with the server and the port
#   last_request_time to store the last time a request was made to this url through this class and initialise to 0
class Communicator:

    def __init__(self):
        self.client_id = config.client_id
        self.client_secret = config.client_secret
        self.server, self.port = 'localhost', 8139
        self._redirect_uri = f'https://{self.server}:{self.port}'
        self._last_request_time = 0

    # method to get the digikey authorisation code via the endpoint for authentication of user through their browser
    def auth(self):
        # parameters required to send url encoded in the browser
        params = {
            'response_type': 'code',
            'client_id': self.client_id,
            'redirect_uri': self._redirect_uri,
            'state': state
        }

        # prepare a request to be sent to the web browser with the authorisation url
        # invoke the webpage to come up on the user's screen to enable user to allow or deny permission to proceed
        request = requests.Request('GET', AUTH, params).prepare()
        request.prepare_url(AUTH, params)
        webbrowser.open(request.url)

        # ask the user copy and paste the url containing the access code and state variables after clicking allow
        # parse and check the state variable from the url
        #   if no fraud according to the state variable comparison then extract the code from the url
        token_url = input("Please ALLOW access and copy and paste the resulting URL here: ")
        query = urllib.parse.parse_qs(urllib.parse.urlparse(token_url).query)
        if not query['state'] or query['state'][0] != state:
            raise RuntimeError("State argument missing or invalid")
        code = query['code']

        # parameters required to request the access token and refresh token for access to digikey api
        params = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'grant_type': 'authorization_code',
            'code': code[0],
            'redirect_uri': self._redirect_uri
        }
        # get the token
        self._get_token(params)

    # method to get the token passing the parameters
    #   get the access token and the refresh token from the specified digikey token endpoint url
    def _get_token(self, params):
        r = requests.post(TOKEN, params).json()
        self.token = r['access_token']
        self.refresh_token = r['refresh_token']

    # method to refresh the access token and extend access to another 30 mins
    def _refresh_token(self):
        params = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'grant_type': 'refresh_token',
            'refresh_token': self.refresh_token
        }

        self._get_token(params)

    # method used in get and post methods below
    # regulates the get and post requests in the class
    # taken from https://stackoverflow.com/questions/39858027/oauth-and-redirect-uri-in-offline-python-script
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

    # method to send a get request to the api using the request method above
    def get(self, url, params):
        return self._request(requests.get, url, params)

    # method to send a post request
    def post(self, url, params):
        return self._request(requests.post, url, params)


# class to store the information about each component
#   initialise variables in the class for
#   the quantity stored as an integer
#   the quantity available for the component stored as an integer
#   the stock code of the component
#   the component price stored as a float
#   an error message if there is an error
class Component:
    def __init__(self, quantity, quantity_available, stock_code, price, error_message):
        self.quantity = int(quantity)
        self.quantity_available = int(quantity_available)
        self.stock_code = stock_code
        self.price = float(price)
        self.error_message = error_message

    # method to format the output for each component
    def comp_str(self):
        return f'''—————————————————————————————————————————————————
Quantity Required: \t{self.quantity}
Stock Code: \t\t{self.stock_code}
Price: \t\t\t{self.price}
—————————————————————————————————————————————————\n
'''

    # method to format the output for each component that has an error
    def error_str(self):
        return f'''—————————————————————————————————————————————————
Quantity required: \t{self.quantity}
Stock Code: \t\t{self.stock_code}
Error: \t\t\t{self.error_message}
—————————————————————————————————————————————————\n
'''


# function to organise and view all the components using the proper formatting
def view_components(file):
    for comp in component_list:
        file.write(comp.comp_str())


# function to organise and view all the components with errors using the proper formatting
def view_errors(file):
    for error in error_list:
        file.write(error.error_str())


# function that gets the best price for the quantity of components required
def get_price(quantity, product_dict):
    null_price = {'BreakQuantity': 0, 'UnitPrice': 0.0, 'TotalPrice': 0.0}
    unsorted_price_list = []

    for element in product_dict['Products'][1]['StandardPricing']:
        unsorted_price_list.append(element)

    for element in product_dict['Products'][0]['StandardPricing']:
        unsorted_price_list.append(element)

    price_list = sorted(unsorted_price_list, key=itemgetter('BreakQuantity'))

    if quantity > 0:
        counter = 0
        while quantity > price_list[counter]['BreakQuantity']:
            counter += 1
            if counter >= len(price_list):
                break
        return price_list[counter - 1]
    else:
        return null_price
    

# function to return the quantity of components available
def get_qty_available(product_dict):
    return max(product_dict['Products'][0]['QuantityAvailable'],product_dict['Products'][1]['QuantityAvailable'])


# function to return the digikey part number for the component
def get_dk_part_number(product_dict):
    return product_dict['Products'][0]['DigiKeyPartNumber']


# main program
if __name__ == '__main__':
    # sandbox authorisation endpoint url
    AUTH = 'https://sandbox-api.digikey.com/v1/oauth2/authorize'
    # sandbox url to get the access token
    TOKEN = 'https://sandbox-api.digikey.com/v1/oauth2/token'

    # initialise variable that will store the authorisation code
    code = ''

    # create two empty lists
    # one will store the component objects that do not show errors
    # the other will store the component objects that do show errors
    component_list = []
    error_list = []

    # open file to read into from the first argument in the command line
    # in this case this is the bill of materials csv file
    # store it as a list excluding the first line of the file
    # close the file
    f = open(sys.argv[1], "r")
    bom = f.readlines()[1:]
    f.close()

    # store the number of sets of parts wanted to check the pricing for which will be given as the second
    # command line argument
    num_parts = int(sys.argv[2])

    # declare the state variable by generating random characters to compare with return url state variable
    state = binascii.hexlify(os.urandom(20)).decode('utf-8')

    # initiate communicator class variable
    com = Communicator()

    # call the auth method to present the user with the authorisation page
    com.auth()

    # digikey api endpoint to use to obtain product information
    host = 'https://sandbox-api.digikey.com/PackageTypeByQuantity/v3/Products/'

    # initiate headers in line with digikey documentation configured for UK use
    HEADERS = {
        'X-DIGIKEY-Client-Id': com.client_id,
        'Authorization': 'Bearer '+com.token,
        'X-DIGIKEY-Locale-Site': 'UK',
        'X-DIGIKEY-Locale-Language': 'en',
        'X-DIGIKEY-Locale-Currency': 'GBP',
        'X-DIGIKEY-Locale-ShipToCountry': 'uk',
        'X-DIGIKEY-Customer-Id': '0'
    }

    # for each line of the bill of materials file
    #   find the quantity of the component in the file and multiply by the number of sets of parts required specified as
    #   the second argument in the command line and store it
    #   find the stock code for the component in the file and store it
    #   use the quantity and stock code to query the api
    #   store the response to the query including the required variables
    for line in reader(bom):
        component_info = line
        quantity = int(component_info[1]) * int(num_parts)
        stock_code = component_info[4]
        host_URL = host + stock_code
        PARAMS = {
            'RequestedQuantity': str(quantity),
            'Includes': 'Products(DigiKeyPartNumber,QuantityAvailable,StandardPricing)'
        }
        response = request(method="GET", url=host_URL, headers=HEADERS, params=PARAMS)

        # if the response is successful
        #   the error message is empty
        #   store the contents of the json file created as a dictionary
        #   use the dictionary to extract the applicable best price for the quantity required
        #   extract the digikey part number for the component
        #   extract the unit price for the component
        #   extract the appropriate total price for the component
        #   store this information as a component object using Component class
        #   append this object to the component list
        if response.status_code == 200:
            error_message = ""
            product_dict = json.loads(str(response.content)[2:-1])
            quantity_in_stock = get_qty_available(product_dict)
            DigiKeyPartNumber = get_dk_part_number(product_dict)
            unit_price = get_price(quantity, product_dict)['UnitPrice']
            total_price = get_price(quantity, product_dict)['UnitPrice'] * quantity
            component = Component(quantity, quantity_in_stock, stock_code, round(total_price, 2), "")
            component_list.append(component)

        # if there is an error
        #   store the error message from the response
        #   store this information as a component object using Component class
        #   set the quantity available parameter and the price parameter to 0
        #   append to the error list
        else:
            error_message = f"Error: {response.text}"
            component = Component(quantity, 0, stock_code, 0, error_message)
            error_list.append(component)
       
    # open a file to write the components from both lists into
    # to show the prices for each component and instances where an error has occured
    # close the file
    f = open("DigikeyPricing.txt", "w")
    f.write("Available Components:\n")
    view_components(f)
    f.write("\nData That Does Not Match:\n")
    view_errors(f)
    f.close()

    # open the same file to read into and store the contents of the file
    # then print the file to the console
    f = open("DigikeyPricing.txt", "r")
    dk_pricing = f.read()
    f.close()
    print(dk_pricing)

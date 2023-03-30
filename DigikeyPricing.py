# modules
import sys
from csv import reader

import os
import json

from operator import itemgetter
from requests.api import request
import config

import digikey
from digikey.v3.productinformation import ManufacturerProductDetailsRequest


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
Quantity Required: \t\t{self.quantity}
Quantity Available: \t{self.quantity_available}
Stock Code: \t\t\t{self.stock_code}
Cut Tape Price: \t\t{self.price}
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

    for element in product_dict['Products']:
        for item in element['StandardPricing']:
            unsorted_price_list.append(item)

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
    max_num = 0

    for i in product_dict['Products']:
        max_num = max(max_num, i['QuantityAvailable'])

    return max_num


# # function to return the digikey part_dict number for the component
# def get_dk_part_number(product_dict):
#     return product_dict['Products'][0]['DigiKeyPartNumber']


def find_keys(node, kv):
    if isinstance(node, list):
        for i in node:
            for x in find_keys(i, kv):
               yield x
    elif isinstance(node, dict):
        if kv in node:
            yield node[kv]
        for j in node.values():
            for x in find_keys(j, kv):
                yield x


def my_function(x):
    return list(dict.fromkeys(x))


# main program
if __name__ == '__main__':

    # define the environment variables from the digikey docs
    # https://pypi.org/project/digikey-api/
    # for security purposes these are defined in a separate config file
    # set the client sandbox variable to true for testing purposes using sandbox api
    # can be changed to false later to use as a production app
    os.environ['DIGIKEY_CLIENT_ID'] = config.client_id
    os.environ['DIGIKEY_CLIENT_SECRET'] = config.client_secret
    os.environ['DIGIKEY_CLIENT_SANDBOX'] = 'False'
    os.environ['DIGIKEY_STORAGE_PATH'] = config.cache_dir

    # call the digikey product details method with a valid stock code
    # NOTE: The purpose for this call is to bypass oauth2
    part = digikey.product_details('TMK105BJ104KV-F')

    # create two empty lists
    # one will store the component objects that do not show errors
    # the other will store the component objects that do show errors
    component_list = []
    error_list = []

    # open file to read into from the first argument in the command line
    # in this case this is the bill of materials csv file
    # store it as a list excluding the first line of the file
    # close the file
    f = open('Bill Of Materials PowerPortMax-v5.csv', "r")
    bom = f.readlines()[1:]
    f.close()

    # store the number of sets of parts wanted to check the pricing for which will be given as the second
    # command line argument
    num_parts = 50

    # digikey api endpoint to use to obtain product information
    host = 'https://api.digikey.com/PackageTypeByQuantity/v3/Products/'

    f = open('token_storage.json', 'r')
    token_file = f.read()
    token_dict = json.loads(token_file)
    f.close()

    # initiate headers in line with digikey documentation configured for UK use
    HEADERS = {
        'X-DIGIKEY-Client-Id': config.client_id,
        'Authorization': 'Bearer ' + token_dict['access_token'],
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

        # Search for parts
        search_request = ManufacturerProductDetailsRequest(stock_code, record_count=10)
        result = digikey.manufacturer_product_details(body=search_request)

        result_dict = result.to_dict()

        dkpn_list = list(find_keys(result_dict, 'digi_key_part_number'))

        if len(dkpn_list) > 0:
            dk_part_nums = my_function(dkpn_list)

            host_URL = host + dk_part_nums[0]
            PARAMS = {
                'RequestedQuantity': str(quantity),
                'Includes': 'Products(DigiKeyPartNumber,QuantityAvailable,StandardPricing)'
            }
            response = request(method="GET", url=host_URL, headers=HEADERS, params=PARAMS)

            # if the response is successful
            #   the error message is empty
            #   store the contents of the json file created as a dictionary
            #   use the dictionary to extract the applicable best price for the quantity required
            #   extract the digikey part_dict number for the component
            #   extract the unit price for the component
            #   extract the appropriate total price for the component
            #   store this information as a component object using Component class
            #   append this object to the component list
            if response.status_code == 200:
                error_message = ""
                product_dict = json.loads(str(response.content)[2:-1])
                quantity_in_stock = get_qty_available(product_dict)
                # DigiKeyPartNumber = get_dk_part_number(product_dict)
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
        else:
            error_message = 'Error: This Manufacturer Code cannot be found'
            component = Component(quantity, 0, stock_code, 0, error_message)
            error_list.append(component)

    # open a file to write the components from both lists into
    # to show the prices for each component and instances where an error has occured
    # close the file
    f = open("DigikeyPricing_1.txt", "w")
    f.write("Available Components:\n")
    view_components(f)
    f.write("\nData That Does Not Match:\n")
    view_errors(f)
    f.close()

    # open the same file to read into and store the contents of the file
    # then print the file to the console
    f = open("DigikeyPricing_1.txt", "r")
    dk_pricing = f.read()
    f.close()
    print(dk_pricing)

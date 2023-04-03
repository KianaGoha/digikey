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


# class that will store the following product information for each component
#   the quantity that is required
#   the quantity available in stock on the digi-key website
#   the stock code for the component
#   the price
#   an error message should there be an issue
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
Cut Tape Price: \t\t£{self.price}
—————————————————————————————————————————————————\n
'''

    # method to format the output for each component that has an error
    def error_str(self):
        return f'''—————————————————————————————————————————————————
Quantity required: \t{self.quantity}
Stock Code: \t\t{self.stock_code}
Error: \t\t\t\t{self.error_message}
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


# get product information for tape and reel packaging including break quantities and pricing
def get_tr_info(quant, prod_dict):
    tr_list = []

    # if the quantity required for the component is greater than the standard package amount
    #   go to the tape and reel pricing in the product dictionary
    #   append that to a dictionary
    for element in prod_dict['Products'][0]['StandardPricing']:
        tr_list.append(element)

    counter = 0
    while quant >= tr_list[counter]['BreakQuantity']:
        counter += 1
        if counter >= len(tr_list):
            break
    return tr_list[counter - 1]


# get product information for cut tape packaging including pricing
def get_ct_price(quant, prod_dict):
    ct_list = []

    for element in prod_dict['Products'][1]['StandardPricing']:
        ct_list.append(element)

    counter = 0
    while quant >= ct_list[counter]['BreakQuantity']:
        counter += 1
        if counter >= len(ct_list):
            break
    return ct_list[counter - 1]


# get the best price for the quantity of components required
def get_price(quant, prod_dict):
    null_price = {'BreakQuantity': 0, 'UnitPrice': 0.0, 'TotalPrice': 0.0}
    unsorted_price_list = []

    for element in prod_dict['Products']:
        for item in element['StandardPricing']:
            unsorted_price_list.append(item)

    price_list = sorted(unsorted_price_list, key=itemgetter('BreakQuantity'))

    if quant > 0:
        counter = 0
        while quant >= price_list[counter]['BreakQuantity']:
            counter += 1
            if counter >= len(price_list):
                break
        return price_list[counter - 1]
    else:
        return null_price


# function to return the quantity of components available
def get_qty_available(prod_dict):
    max_num = 0

    for i in prod_dict['Products']:
        max_num = max(max_num, i['QuantityAvailable']) 
        # if there is no stock it still put a price

    return max_num


# function to find the digi-key part number
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


# function to eliminate repeating digi-key part numbers
def eliminate_duplicates(x):
    return list(dict.fromkeys(x))


# main program
if __name__ == '__main__':

    # define the environment variables from the digi-key docs
    # https://pypi.org/project/digikey-api/
    # for security purposes these are defined in a separate config file
    # set the client sandbox variable to true for testing purposes using sandbox api
    # can be changed to false later to use as a production app
    os.environ['DIGIKEY_CLIENT_ID'] = config.client_id
    os.environ['DIGIKEY_CLIENT_SECRET'] = config.client_secret
    os.environ['DIGIKEY_CLIENT_SANDBOX'] = 'False'
    os.environ['DIGIKEY_STORAGE_PATH'] = config.cache_dir

    # call the digi-key product details method with a valid stock code
    # NOTE: The purpose for this call is to bypass oauth2
    part = digikey.product_details('TMK105BJ104KV-F')

    # create two empty lists to store the component objects that do not show errors
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

    # digi-key api endpoint to use to obtain product information
    host = 'https://api.digikey.com/PackageTypeByQuantity/v3/Products/'

    f = open('token_storage.json', 'r')
    token_file = f.read()
    token_dict = json.loads(token_file)
    f.close()

    # initiate headers in line with digi-key documentation configured for UK use
    HEADERS = {
        'X-DIGIKEY-Client-Id': config.client_id,
        'Authorization': 'Bearer ' + token_dict['access_token'],
        'X-DIGIKEY-Locale-Site': 'UK',
        'X-DIGIKEY-Locale-Language': 'en',
        'X-DIGIKEY-Locale-Currency': 'GBP',
        'X-DIGIKEY-Locale-ShipToCountry': 'uk',
        'X-DIGIKEY-Customer-Id': '0'
    }

    # for each line of the csv file
    #   find the quantity of the component in the file and multiply by the number of sets of parts required specified as
    #   the second argument in the command line and store it
    #   find the stock code for the component in the file and store it
    for line in reader(bom):
        component_info = line
        quantity = int(component_info[1]) * int(num_parts)
        stock_code = component_info[4]

        # Search for parts
        # https://pypi.org/project/digikey-api/
        search_request = ManufacturerProductDetailsRequest(stock_code, record_count=10)
        result = digikey.manufacturer_product_details(body=search_request)

        # convert the result to a dictionary
        result_dict = result.to_dict()

        # find the quantity of the components that come with digi-key's standard packaging
        standard_package = list(find_keys(result_dict, 'standard_package'))

        # if the standard package quantity list is not empty
        #   get the standard package quantity from the list
        if standard_package != []:
            standard_package = standard_package[0]

            # find the digi-key part numbers from the dictionary and store in a list
            dkpn_list = list(find_keys(result_dict, 'digi_key_part_number'))

            # eliminate repeating part numbers
            if len(dkpn_list) > 0:
                dk_part_nums = eliminate_duplicates(dkpn_list)

                # query the information for the requested quantity for the digi-key part number
                host_URL = host + dk_part_nums[0]
                PARAMS = {
                    'RequestedQuantity': str(quantity),
                    'Includes': 'Products(DigiKeyPartNumber,QuantityAvailable,StandardPricing)'
                }
                response = request(method="GET", url=host_URL, headers=HEADERS, params=PARAMS)

                # if the response is successful
                #   store the error message as an empty string
                #   store the contents of the json file as a dictionary which has the product pricing information
                #   from this dictionary find the quantity of the component that digi-key has in stock
                if response.status_code == 200:
                    error_message = ""
                    product_dict = json.loads(str(response.content)[2:-1])
                    quantity_in_stock = get_qty_available(product_dict)

                    # if digi-key does not have the component in stock
                    #   print the relevant error message
                    #   create a component object with the Component class and store the relevant information
                    #   add the object to the error list
                    if quantity_in_stock == 0:
                        error_message = 'This component is out of stock'
                        component = Component(quantity, quantity_in_stock, stock_code, 0, error_message)
                        error_list.append(component)

                    # if the product is not in stock
                    #   print the relevant error message
                    #   create a component object with the Component class and store the relevant information
                    #   add the object to the error list
                    elif quantity_in_stock < quantity:
                        error_message = 'Digi-key does not have the quantity required of this component in stock'
                        component = Component(quantity, quantity_in_stock, stock_code, 0, error_message)
                        error_list.append(component)

                    # if the quantity in stock is greater than the quantity required
                    #   and if the quantity require is greater than the quantity of the standard package
                    #       find the modulus of the quantity required and the standard package quantity
                    elif quantity_in_stock >= quantity:
                        if quantity > standard_package:
                            quantity_mod = quantity % standard_package

                            # if the modulus is not 0
                            #   subtract the modulus from the quantity required to find how many component prices will
                            #   be determined by the tape and reel pricing
                            #   find the price of the tape and reel components
                            #   find the price of the cut tape components i.e. the modulus
                            #   add the two prices together to get the total price
                            #   store this information using the Component class
                            #   append this to the component list
                            if quantity_mod != 0:
                                tr_quant = quantity - quantity_mod
                                tr_price = round(get_tr_info(quantity, product_dict)['UnitPrice'] * tr_quant, 2)
                                ct_price = get_ct_price(quantity_mod, product_dict)['UnitPrice'] * quantity_mod
                                total_price = round(tr_price + ct_price, 2)
                                component = Component(quantity, quantity_in_stock, stock_code, total_price, error_message)
                                component_list.append(component)

                            # if the modulus equals 0
                            #   only get the price for the tape and reel packaging
                            #   store this information with the Component class and append this to the list
                            else:
                                total_price = round(get_tr_info(quantity, product_dict)['UnitPrice'] * quantity, 2)
                                component = Component(quantity, quantity_in_stock, stock_code, total_price, error_message)
                                component_list.append(component)

                        # if the standard package quantity is greater than the quantity required
                        #   find the total price of the components for the quantity required
                        #   store this info using the Component class and append to the component list
                        elif standard_package > quantity:
                            total_price = get_price(quantity, product_dict)['UnitPrice'] * quantity
                            component = Component(quantity, quantity_in_stock, stock_code, round(total_price, 2), "")
                            component_list.append(component)

                # if the query is not successful
                #   get the error message
                #   store this information as a component object using Component class
                #   append to the error list
                else:
                    error = json.loads(response.text)
                    error_message = error['ErrorMessage']
                    component = Component(quantity, 0, stock_code, 0, error_message)
                    error_list.append(component)

        # if the manufacturers stock code is not recognised then
        #   display the relevant message
        #   create a component object using the Component class and add the relevant information
        #   append to the error list
        else:
            error_message = 'This Stock Code cannot be found'
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
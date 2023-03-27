# modules
import json
import sys
import os
import digikey
from digikey.v3.productinformation import KeywordSearchRequest
from csv import reader
from operator import itemgetter
import config


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
Stock Code: \t\t{self.stock_code}
Quantity Required: \t{self.quantity}
Quantity Available: {self.quantity_available}
Price: \t\t\t{self.price}
—————————————————————————————————————————————————\n
'''

    # method to format the output for each component that has an error
    def error_str(self):
        return f'''—————————————————————————————————————————————————
Stock Code: \t\t{self.stock_code}
Quantity required: \t{self.quantity}
Quantity Available: \t{self.quantity_available}
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
# taking the quantity of the parts that are required and the dictionary in which the product details are stored
def get_price(quantity, product_dict):
    # create null price dictionary in case there is an error with the quantity available or the stock code with
    # values initialised to 0
    null_price = {'break_quantity': 0, 'total_price': 0.0, 'unit_price': 0.0}

    # create an empty list that will be used to store all the prices
    price_list = []

    # for each element in the standard pricing section of the dictionary where the product details are stored
    #   append that element to the price list
    for element in product_dict.standard_pricing:
        price_list.append(element)

    # if the quantity is greater than 0
    #   create a counter and initialise to 0
    if quantity > 0:
        counter = 0

        # while the quantity is greater than the break quantity of the item in the price list
        #   increment the counter by 1
        #   if the counter becomes greater than or equal to the length of the price list
        #       break the loop
        # return the item in the price list at the index position of the counter - 1
        while quantity > price_list[counter].break_quantity:
            counter += 1
            if counter >= len(price_list):
                break
        return price_list[counter - 1]

    # if the quantity is 0
    #   return the null price dictionary
    else:
        return null_price


# main program
if __name__ == '__main__':

    # create two empty lists
    # one will store the component objects that do not show errors
    # the other will store the component objects that do show errors
    component_list = []
    error_list = []

    # define the environment variables from the digikey docs
    # https://pypi.org/project/digikey-api/
    # for security purposes these are defined in a separate config file
    # set the client sandbox variable to true for testing purposes using sandbox api
    # can be changed to false later to use as a production app
    os.environ['DIGIKEY_CLIENT_ID'] = config.client_id
    os.environ['DIGIKEY_CLIENT_SECRET'] = config.client_secret
    os.environ['DIGIKEY_CLIENT_SANDBOX'] = 'True'
    os.environ['DIGIKEY_STORAGE_PATH'] = config.cache_dir

    # open file to read into from the first argument in the command line
    # in this case this is the bill of materials csv file
    # store it as a list excluding the first line of the file
    # close the file
    f = open(sys.argv[1], "r")
    bom = f.readlines()[1:]
    f.close()
    # f = open('Bill Of Materials PowerPortMax-v5.csv', "r")
    # bom = f.readlines()[1:]
    # bom = reader(bom)
    # f.close()

    # store the number of sets of parts wanted to check the pricing for which will be given as the second
    # command line argument
    num_parts = int(sys.argv[2])

    # for each line of the bill of materials file
    #   find the quantity of the component in the file and multiply by the number of sets of parts required specified as
    #   the second argument in the command line and store it
    #   find the stock code for the component in the file and store it
    #   store these in a dictionary
    #   use the quantity and stock code to query the api
    #   store the response to the query including the required variables
    for line in reader(bom):
        quantity = int(line[1]) * int(num_parts)
        stock_code = line[4]
        part_dict = digikey.product_details(stock_code)

        # if the quantity of the part_dict that is available is less that the quantity that is required
        #   create the relevant error message
        #   store that component as an object using the Component class
        #   make sure the price shows there is an error and store the error message in the object
        #   append object to the error list
        if part_dict.quantity_available < quantity:
            error_message = 'Quantity required not available'
            component = Component(quantity, part_dict.quantity_available, stock_code, "Error", error_message)
            error_list.append(component)

        # if the quantity available is not less that the quantity of the part_dict that is required
        #   find the total price for the quantity that is required
        #   create a component object using the component class created earlier with the relevant attributes
        #   append this to the component list
        else:
            total_price = get_price(quantity, part_dict).unit_price * quantity
            component = Component(quantity, part_dict.quantity_available, stock_code, round(total_price, 2), "")
            component_list.append(component)

    # NOTE: further check needed to validate the stock codes and check whether they exist

    # open a file to write the components from both lists into
    # to show the prices for each component and instances where an error has occured
    # close the file
    f = open("DKPricingTest.txt", "w")
    f.write("Available Components:\n")
    view_components(f)
    f.write("\nData That Does Not Match:\n")
    view_errors(f)
    f.close()

    # open the same file to read into and store the contents of the file
    # then print the file to the console
    f = open("DKPricingTest.txt", "r")
    dk_pricing = f.read()
    f.close()
    print(dk_pricing)

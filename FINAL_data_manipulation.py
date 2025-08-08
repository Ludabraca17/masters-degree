#this file contains the functions for data manipulation


def sort_operations_by_queue_position(order_data):
    '''
    This function takes the entire order and extracts the operations from it. By this point the operations are 
    not sorted and are in the state that the were created by the TB Virtual device widget. 

    After that the function sorts the operations based on the "queuePosition". The queuePosition is 
    set by the digital twin of the factory. The function returns a list of lists, where each sublist 
    contains operations with the same queuePosition. It also means that within a certain list there can be multiple
    operations that have the same queuePosition. This is because the digital twin can assign the same 
    queuePosition to multiple operations. That way the digital twin can order multiple modules to work
    at the same time.
    '''

    new_operations = []
    result = []

    try:
        several_orders = order_data["productData"][0]["products"]
        
        for i in range(0, len(several_orders), 1):
            for j in several_orders[i]["assembly"]:
                new_operations.append(several_orders[i]["assembly"][j])

        sorted_operations = sorted(new_operations, key=lambda x: x["data"]["queuePosition"])
        
        current_group = []
        current_number = None

        for operation in sorted_operations:
            number = operation["data"]["queuePosition"]
            if number != current_number:
                if current_group:
                    result.append(current_group)
                current_group = [operation]
                current_number = number
            else:
                current_group.append(operation)

        if current_group:
            result.append(current_group)

        # Determine the maximum length of groups
        if result:
            max_length = max(len(group) for group in result)
            # Zero-pad each group to the maximum length
            padded_result = []
            for group in result:
                padded_group = group.copy()
                while len(padded_group) < max_length:
                    padded_group.append(None)  # Placeholder for padding
                padded_result.append(padded_group)
            result = padded_result

    except KeyError:
        pass

    return result

def collect_data():
    """
    This function reads the returned data from NR and returns it to the TB. It should also append the next
    data and then overwrite the data on TB. 
    """
    #end_of_order.append() bla bla bla

def send_number_of_parts():
    """
    We are going to see how many parts of each color we have on table and then limit what a customer
    can select in the UI on TB. 
    """
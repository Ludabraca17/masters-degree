import logging
import requests
import time
import json

# Configure logging
logging.basicConfig(level=logging.INFO)

# Configuration variables
THINGSBOARD_URL = "http://192.168.9.108:8080"
USERNAME = "th@thingsboard.si"
PASSWORD = "123456"

# Device details
VIRTUAL_DEVICE_ID = "9d934650-0fb4-11f0-87c9-25f8db756ccd"
NODE_RED_1_DEVICE_ID = "371f6060-f039-11ef-b7cd-2d9d98e4919e"
NODE_RED_2_DEVICE_ID = "f84ef880-fa99-11ef-a077-cbfaee2c37bd"
AGV_ID = "1e735a00-1a99-11f0-87c9-25f8db756ccd"

def read_attribute(username, password, device_id, thingsboard_url, attribute_key):
    """
    This function reads the TB attribute from TB. The data read in this file is production order
    from "Virtual device" and signals from modules and AGVs (NodeRed1, NodeRed2, AGV).
    """

    # Client attributes to be read
    attributes_to_read = [attribute_key]  # Replace with the attributes you want to read

    def read_client_attributes(jwt_token):
        url = f"{thingsboard_url}/api/plugins/telemetry/DEVICE/{device_id}/values/attributes"
        headers = {
            "X-Authorization": f"Bearer {jwt_token}"
        }
        # Request parameters
        params = {
            "keys": ",".join(attributes_to_read)
        }

        response = requests.get(url, headers=headers, params=params)

        if response.status_code == 200:
            #print(f"Attribute {attribute_key} read successfully.")
            return response.json()
        else:
            print(f"Failed to read attributes. Status Code: {response.status_code}, Response: {response.text}")

    # Main logic
    jwt_token = get_jwt_token()
    if jwt_token:
        local_variable = read_client_attributes(jwt_token)[0]["value"]
        return local_variable

def update_attribute(username, password, device_id, thingsboard_url, attribute_key, attribute_value):
    """
    This function updates the TB attribute on TB. It can be used for updating current state of the order (times,
    positions, etc.) as well as current states of modules and AGVs ("idle", "callibrating", "processing", "error")
    and their command messages.
    """

    def update_shared_attributes(jwt_token):
        url = f"{thingsboard_url}/api/plugins/telemetry/DEVICE/{device_id}/attributes/SHARED_SCOPE"
        headers = {
            "Content-Type": "application/json",
            "X-Authorization": f"Bearer {jwt_token}"
        }
        payload = {
            attribute_key: attribute_value
        }

        #print(f"Updating attributes with payload: {payload}")
        response = requests.post(url, json=payload, headers=headers)

        if response.status_code == 200:
            #print("Attributes updated successfully.")
            pass
        else:
            print(f"Failed to update attributes. Status Code: {response.status_code}, Response: {response.text}")

    # Main logic
    jwt_token = get_jwt_token()
    if jwt_token:
        update_shared_attributes(jwt_token)

def get_jwt_token():
    """
    This function is used for fetching a jwt token from TB. It is used for authentication of the user.
    """
    url = f"{THINGSBOARD_URL}/api/auth/login"
    payload = {
        "username": USERNAME,
        "password": PASSWORD
    }
    headers = {
        "Content-Type": "application/json"
    }

    response = requests.post(url, json=payload, headers=headers)

    if response.status_code == 200:
        token = response.json().get("token")
        #print(f"JWT Token obtained: {token}")
        return token
    else:
        print(f"Failed to authenticate. Status Code: {response.status_code}, Response: {response.text}")
        return None

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

    except KeyError:
        pass

    return result
        

    

def main_transport_operation(current_operation, operation_count):
    """
    This function represents the logic of a transport operation. It updates the attributes of the conveyor and AGV devices to start the transport.
    In this phase it is hardcoded for module1 and module2, but the upgrade will include the dynamic selection of the modules. Current two input variables
    (current_operation and operation_count) are trivial since they are both global variables. In the future we will add variables for whichever module is
    selected for transport by the digital twin.
    """

    print("ZAČETEK TRANSPORTA")
    #priprava za oddajanje kosa AGVju
    update_attribute(USERNAME, PASSWORD, NODE_RED_1_DEVICE_ID, THINGSBOARD_URL, "conveyorMessage", "Start")
    update_attribute(USERNAME, PASSWORD, AGV_ID, THINGSBOARD_URL, "commandAGV", "Prepare")
    transport_condition = True
    updated = False #internal logic variable for next while loop
    try:
        while transport_condition:
            condition = None
            condition = read_attribute(USERNAME, PASSWORD, NODE_RED_1_DEVICE_ID, THINGSBOARD_URL, "conveyorResponse")
            print("Glavna zanka za transport")
            try:
                while condition == "Waiting":
                    
                    if read_attribute(USERNAME, PASSWORD, AGV_ID, THINGSBOARD_URL, "status") == "Waiting" and updated == False:
                        update_attribute(USERNAME, PASSWORD, NODE_RED_1_DEVICE_ID, THINGSBOARD_URL, "conveyorMessage", "AGV ready")
                        updated = True
                        print("Poslal kos na AGV")
                    if read_attribute(USERNAME, PASSWORD, NODE_RED_1_DEVICE_ID, THINGSBOARD_URL, "conveyorResponse") == "Sent":
                        updated = False
                        print("Pošiljam ukaz za transport na drugi modul")
                        update_attribute(USERNAME, PASSWORD, AGV_ID, THINGSBOARD_URL, "commandAGV", "Go")
                        #update_attribute(USERNAME, PASSWORD, NODE_RED_1_DEVICE_ID, THINGSBOARD_URL, "conveyorResponse", "Idle")
                        break

            except KeyboardInterrupt:
                pass

            if read_attribute(USERNAME, PASSWORD, NODE_RED_1_DEVICE_ID, THINGSBOARD_URL, "conveyorResponse") == "Sent" and read_attribute(USERNAME, PASSWORD, AGV_ID, THINGSBOARD_URL, "status") == "Delivered":
                #read_attribute(USERNAME, PASSWORD, AGV_ID, THINGSBOARD_URL, "status") == "Finished"
                update_attribute(USERNAME, PASSWORD, NODE_RED_1_DEVICE_ID, THINGSBOARD_URL, "conveyorResponse", "Idle")
                update_attribute(USERNAME, PASSWORD, NODE_RED_2_DEVICE_ID, THINGSBOARD_URL, "conveyorMessage", "Prepare for assembly")
                update_attribute(USERNAME, PASSWORD, AGV_ID, THINGSBOARD_URL, "status", "Idle") #to bo verjetno treba dat stran - to določi agv sam

                print("Čakam da trak odpelje kos na montažno mesto")
                try:
                    while True:
                        if read_attribute(USERNAME, PASSWORD, NODE_RED_2_DEVICE_ID, THINGSBOARD_URL, "conveyorResponse") == "Prepared":
                            update_attribute(USERNAME, PASSWORD, NODE_RED_2_DEVICE_ID, THINGSBOARD_URL, "currentOperation", current_operation)
                            operation_count += 1
                            print("Operation count: ", operation_count)
                            print("Current subpart: ", current_operation["data"]["part"])
                            break
                        
                except KeyboardInterrupt:
                    pass

            if read_attribute(USERNAME, PASSWORD, NODE_RED_2_DEVICE_ID, THINGSBOARD_URL, "conveyorResponse") == "Prepared":
                update_attribute(USERNAME, PASSWORD, NODE_RED_2_DEVICE_ID, THINGSBOARD_URL, "conveyorResponse", "Idle")
                transport_condition = False

    except KeyboardInterrupt:
        pass

    return operation_count

def assembly_logic(current_operation):
    """
    This is an assembly function that is used for sending the current operation to the appropriate assembly module. 
    It also checks the status of the previous operation and the current state of the assembly module in order to
    send the messages to the modules at the right time. 

    For now the function is hardcoded and only works for module1 and module2. It also only supports the flow of order 
    from module1 to module2. In the future it will have to be made more general as is the situation with the function
    for transport. 

    The function should also be able to check wether the the operation was finished and then send the data back to Virtual device
    for the user, to see the progres of the production order. It should be done in a way that it appends the current operation, 
    returned by the NodeRed with times and status changed to the header  or replace the operation in the read production order
    and then returns the whole order back to TB. It should do so every time the operation is finished. This is NOT yet implemented.
    """
    global operation_count, previousOperation_NR1, previousOperation_NR2, current_state_NR1, current_state_NR2, current_operation_group

    if (previousOperation_NR1["metrics"]["status"] == "Finished" and current_state_NR1 == "Idle") or (operation_count == 0):
    #change status of the previous operation to "finished" for uploading to TB
    #prepared_order[0]["assembly"][current_operation["data"]["machineID"]]["metrics"]["status"] = "Finished"

        #operacije modul1
        if (current_operation["data"]["machineID"] == "module1"):
            update_attribute(USERNAME, PASSWORD, NODE_RED_1_DEVICE_ID, THINGSBOARD_URL, "currentOperation", current_operation)
            #end_of_order.append(return_data(current_operation))#poskus branja podatkov iz modulov
            operation_count += 1
            print("Operation count: ", operation_count)
            print("Current subpart: ", current_operation["data"]["part"])

        #transport
        elif (current_operation["data"]["AGVstartPos"] and current_operation["data"]["AGVendPos"]) != None:
            operation_count = main_transport_operation(current_operation, operation_count)

        #operacije modul2
        elif (previousOperation_NR2["metrics"]["status"] == "Finished") and (current_state_NR2 == "Idle"):
            if current_operation["data"]["machineID"] == "module2":
                update_attribute(USERNAME, PASSWORD, NODE_RED_2_DEVICE_ID, THINGSBOARD_URL, "currentOperation", current_operation)
                #end_of_order.append(return_data(current_operation))#poskus branja podatkov iz modulov
                operation_count += 1
                print("Operation count: ", operation_count)
                print("Current subpart: ", current_operation["data"]["part"])
                
                #end transport 
                if (current_operation["data"]["AGVstartPos"] =="module2") and (current_operation["data"]["AGVendPos"] == None):
                    #transporting after finished assembly
                    #to je potrebno še preveriti in prilagoditi splošno funkcijo tudi za ta način delovanja
                    try:
                        while True:
                            print("zadnja transportna zanka")
                            if read_attribute(USERNAME, PASSWORD, NODE_RED_2_DEVICE_ID, THINGSBOARD_URL, "currentOperation")["metrics"]["status"] == "Finished":
                                update_attribute(USERNAME, PASSWORD, NODE_RED_2_DEVICE_ID, THINGSBOARD_URL, "conveyorMessage", "Start")
                                break
                    except KeyboardInterrupt:
                        pass
    
    return operation_count

def transport_after_assembly(current_operation_group, i):
    """
    Function reads whether the AGV end and start positions indicate that this is the last operation for the product.
    If so, it starts the conveyor programme with IR sensor. (for now we remove it by hand)
    """

    print("Transport after assembly function")
    #tole spodaj je en velik vprašaj... mogoče ne bi bilo slabo razviti standardne operacije (transport sestava itn in jih potem klicati v if stavkih)        
    if (current_operation_group[i]["data"]["AGVstartPos"] != None) and (current_operation_group[i]["data"]["AGVendPos"] == None):
            
        print("Start transport after assembly")
        #transporting after finished assembly
        #update_attribute(USERNAME, PASSWORD, NODE_RED_2_DEVICE_ID, THINGSBOARD_URL, "currentOperation", current_operation)
        #operation_count += 1
        try:
            while True:
                print("zadnja transportna zanka")
                if read_attribute(USERNAME, PASSWORD, NODE_RED_2_DEVICE_ID, THINGSBOARD_URL, "currentOperation")["metrics"]["status"] == "Finished":
                    update_attribute(USERNAME, PASSWORD, NODE_RED_2_DEVICE_ID, THINGSBOARD_URL, "conveyorMessage", "Start")
                    break
        except KeyboardInterrupt:
            pass 
    
    else:
        pass


def multiple_modules_logic(current_operation_group):
    """
    Function takes the current operation group that has two operations and runs them both. That way we can operate on 
    both production modules at the same time if the digital twin decides to do so. 
    """
    global operation_count,previousOperation_NR1, previousOperation_NR2, current_state_NR1, current_state_NR2

    try:
        while True:
            previousOperation_NR1 = read_attribute(USERNAME, PASSWORD, NODE_RED_1_DEVICE_ID, THINGSBOARD_URL, "currentOperation")
            previousOperation_NR2 = read_attribute(USERNAME, PASSWORD, NODE_RED_2_DEVICE_ID, THINGSBOARD_URL, "currentOperation")
            current_state_NR1 = read_attribute(USERNAME, PASSWORD, NODE_RED_1_DEVICE_ID, THINGSBOARD_URL, "currentState")
            current_state_NR2 = read_attribute(USERNAME, PASSWORD, NODE_RED_2_DEVICE_ID, THINGSBOARD_URL, "currentState")
            print("Znotraj WHILE zanke")
            #print(previousOperation_NR1["metrics"]["status"], current_state_NR1)
            #print(previousOperation_NR2["metrics"]["status"], current_state_NR2)

            if (previousOperation_NR1["metrics"]["status"] == "Finished" and current_state_NR1 == "Idle") and (previousOperation_NR2["metrics"]["status"] == "Finished" and current_state_NR2 == "Idle"):
                for i in range(0, len(current_operation_group), 1):
                    print("Znotraj FOR zanke")
                    #print("prva operacija: ", current_operation_group[0])
                    #print("druga operacija: ", current_operation_group[1])
                    if current_operation_group[i]["data"]["machineID"] == "module1":
                        update_attribute(USERNAME, PASSWORD, NODE_RED_1_DEVICE_ID, THINGSBOARD_URL, "currentOperation", current_operation_group[i])
                        print("Začel modul1")
                    
                    elif current_operation_group[i]["data"]["machineID"] == "module2":
                        update_attribute(USERNAME, PASSWORD, NODE_RED_2_DEVICE_ID, THINGSBOARD_URL, "currentOperation", current_operation_group[i])
                        print("Začel modul2")
                        transport_after_assembly(current_operation_group=current_operation_group, i=i)
                        
                    else:
                        pass
                end_of_order.append(return_data(current_operation_group))#poskus branja podatkov iz modulov
                operation_count += 1
                print("Operation count: ", operation_count)
                print("ZAKLJUČENA WHILE ZANKA!")
                break
            else:
                pass
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass

    return 


def return_data(current_operation_group: list):
    """
    This function returns the data of the current operation to the JSON structure of the order which is displayed when 
    the order is finished. In the future it will also return data to TB virtual device so we can see the progress of the 
    order in the dashboard.
    """

    return_order = []

    for i in current_operation_group:
        if i["data"]["machineID"] == "module1":
            var = read_attribute(USERNAME, PASSWORD, NODE_RED_1_DEVICE_ID, THINGSBOARD_URL, "currentOperation")
            return_order.append(var)

        elif i["data"]["machineID"] == "module2":
            var = read_attribute(USERNAME, PASSWORD, NODE_RED_2_DEVICE_ID, THINGSBOARD_URL, "currentOperation")
            return_order.append(var)
    
    return return_order

#START of logic
#These are commands that upon startup of the script are sent to the devices to reset them to the initial state.
operation_count = 0
update_attribute(USERNAME, PASSWORD, NODE_RED_1_DEVICE_ID, THINGSBOARD_URL, "conveyorMessage", "Idle")
update_attribute(USERNAME, PASSWORD, NODE_RED_1_DEVICE_ID, THINGSBOARD_URL, "conveyorResponse", "Idle")

update_attribute(USERNAME, PASSWORD, NODE_RED_2_DEVICE_ID, THINGSBOARD_URL, "conveyorMessage", "Idle")
update_attribute(USERNAME, PASSWORD, NODE_RED_2_DEVICE_ID, THINGSBOARD_URL, "conveyorResponse", "Idle")

update_attribute(USERNAME, PASSWORD, AGV_ID, THINGSBOARD_URL, "commandAGV", "Idle")

end_of_order = []

try:
    while True:
        print("New while cycle")
        

        order_data = read_attribute(USERNAME, PASSWORD, VIRTUAL_DEVICE_ID, THINGSBOARD_URL, "productionOrder")

        previousOperation_NR1 = read_attribute(USERNAME, PASSWORD, NODE_RED_1_DEVICE_ID, THINGSBOARD_URL, "currentOperation")
        previousOperation_NR2 = read_attribute(USERNAME, PASSWORD, NODE_RED_2_DEVICE_ID, THINGSBOARD_URL, "currentOperation")

        current_state_NR1 = read_attribute(USERNAME, PASSWORD, NODE_RED_1_DEVICE_ID, THINGSBOARD_URL, "currentState")
        current_state_NR2 = read_attribute(USERNAME, PASSWORD, NODE_RED_2_DEVICE_ID, THINGSBOARD_URL, "currentState")

        #print("Previous operation from NR1 :", previousOperation_NR1)

        sorted_operations = sort_operations_by_queue_position(order_data=order_data) #sorted operations by queue position from digital twin
        #waiting_operations = sorted_operations
        #prepared_order = several_orders #prepared variable which will be appended to the header and sent to the virtual device
        #print("Printing sorted operations",sorted_operations)

        #print("Sorted operations: ", sorted_operations)

        try:
            current_operation_group = sorted_operations[operation_count]
            current_operation = current_operation_group[operation_count % len(current_operation_group)]
            print("Number of current operations: ", len(current_operation_group))
            #print("Current operation", current_operation)

            if len(current_operation_group) == 1:
                print("Prvi IF")
                operation_count = assembly_logic(current_operation=current_operation)

            elif len(current_operation_group) > 1:
                print("Drugi IF")
                #print("Operation count: ", operation_count) 
                #print("Current operation group: ", current_operation_group)
                multiple_modules_logic(current_operation_group=current_operation_group)

        except:
            pass

        if (operation_count == len(sorted_operations)) and (operation_count != 0):
            update_attribute(USERNAME, PASSWORD, VIRTUAL_DEVICE_ID, THINGSBOARD_URL, "productionOrder", {})
            operation_count = 0
            print("Production order finished")
            print(end_of_order)
            end_of_order = []

        time.sleep(1)
except KeyboardInterrupt:
    pass

#treba bo narediti datoteko bolj odporno

#Set-ExecutionPolicy -ExecutionPolicy Unrestricted -Scope CurrentUser




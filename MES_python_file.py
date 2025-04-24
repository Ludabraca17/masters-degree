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
    This function reads the TB attribute from the virtual device. This data is set on the main dashboard.
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
    This function updates the TB attribute on the virtual device. This data is set on the main dashboard.
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

def sort_operations_by_queue_position(operations):
    '''
    This function sorts the operations based on the queuePosition attribute. The queuePosition is set by the digital twin of the factory.
    '''
    return sorted(operations, key=lambda x: x["data"]["queuePosition"])
    
def transport_operation(current_operation, operation_count):
    """
    This function represents the logic of a transport operation. It updates the attributes of the conveyor and AGV devices to start the transport.
    In this phase it is hardcoded for module1 and module2, but the upgrade will include the dynamic selection of the modules. Current two input variables
    (current_operation adn operation_count) are trivial since they are both global variables. In the future we will add variables for whichever module is 
    selected for transport by the digital twin.
    """

    print("ZAČETEK TRANSPORTA")
    #priprava za oddajanje kosa AGVju
    update_attribute(USERNAME, PASSWORD, NODE_RED_1_DEVICE_ID, THINGSBOARD_URL, "conveyorMessage", "Start")
    update_attribute(USERNAME, PASSWORD, AGV_ID, THINGSBOARD_URL, "commandAGV", "Prepare to receive part")
    transport_condition = True
    updated = False #internal logic variable for next while loop
    try:
        while transport_condition:
            condition = None
            condition = read_attribute(USERNAME, PASSWORD, NODE_RED_1_DEVICE_ID, THINGSBOARD_URL, "conveyorResponse")
            print("Glavna zanka za transport")
            try:
                while condition == "Waiting":
                    print("USPEŠNO V PRVI WHILE ZANKI")
                    
                    #AGV povratni signal - AGV na modulu1 - to še moram dobiti (berem stanje AGV device)
                    if read_attribute(USERNAME, PASSWORD, AGV_ID, THINGSBOARD_URL, "status") == "Waiting" and updated == False:
                        update_attribute(USERNAME, PASSWORD, NODE_RED_1_DEVICE_ID, THINGSBOARD_URL, "conveyorMessage", "AGV ready")
                        updated = True
                    if read_attribute(USERNAME, PASSWORD, NODE_RED_1_DEVICE_ID, THINGSBOARD_URL, "conveyorResponse") == "Sent":
                        updated = False
                        print("USPEŠNO ZAKLJUČIL 1. WHILE ZANKO")
                        update_attribute(USERNAME, PASSWORD, AGV_ID, THINGSBOARD_URL, "commandAGV", "Go")
                        #update_attribute(USERNAME, PASSWORD, NODE_RED_1_DEVICE_ID, THINGSBOARD_URL, "conveyorResponse", "Idle")
                        break
                        
            except KeyboardInterrupt:
                pass
            
            if read_attribute(USERNAME, PASSWORD, NODE_RED_1_DEVICE_ID, THINGSBOARD_URL, "conveyorResponse") == "Sent" and input("Enter 'y' to continue: ").strip().lower() == 'y':
                #for now y means that the AGV has transported the part to the second assembly station
                #read_attribute(USERNAME, PASSWORD, AGV_ID, THINGSBOARD_URL, "status") == "Finished"
                update_attribute(USERNAME, PASSWORD, NODE_RED_1_DEVICE_ID, THINGSBOARD_URL, "conveyorResponse", "Idle")
                update_attribute(USERNAME, PASSWORD, NODE_RED_2_DEVICE_ID, THINGSBOARD_URL, "conveyorMessage", "Prepare for assembly")
                update_attribute(USERNAME, PASSWORD, AGV_ID, THINGSBOARD_URL, "status", "Idle")

                try:
                    while True:
                        print("Čakam da trak odpelje kos na montažno mesto")
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
                
                #if read_attribute(USERNAME, PASSWORD, AGV_ID, THINGSBOARD_URL, "") == "":

    except KeyboardInterrupt:
        pass

    return operation_count


#START of logic

operation_count = 0
update_attribute(USERNAME, PASSWORD, NODE_RED_1_DEVICE_ID, THINGSBOARD_URL, "conveyorMessage", "Idle")
update_attribute(USERNAME, PASSWORD, NODE_RED_1_DEVICE_ID, THINGSBOARD_URL, "conveyorResponse", "Idle")

update_attribute(USERNAME, PASSWORD, NODE_RED_2_DEVICE_ID, THINGSBOARD_URL, "conveyorMessage", "Idle")
update_attribute(USERNAME, PASSWORD, NODE_RED_2_DEVICE_ID, THINGSBOARD_URL, "conveyorResponse", "Idle")

#update_attribute(USERNAME, PASSWORD, AGV_ID, THINGSBOARD_URL, "status", "Idle")
update_attribute(USERNAME, PASSWORD, AGV_ID, THINGSBOARD_URL, "commandAGV", "Idle")

try:
    while True:
        print("New while cycle")
        new_operations = []
        try:

            order_data = read_attribute(USERNAME, PASSWORD, VIRTUAL_DEVICE_ID, THINGSBOARD_URL, "productionOrder")
            several_orders = order_data["productData"][0]["products"]

            for i in range(0, len(several_orders), 1):
                for j in several_orders[i]["assembly"]:
                    new_operations.append(several_orders[i]["assembly"][j])

            previousOperation_NR1 = read_attribute(USERNAME, PASSWORD, NODE_RED_1_DEVICE_ID, THINGSBOARD_URL, "currentOperation")
            previousOperation_NR2 = read_attribute(USERNAME, PASSWORD, NODE_RED_2_DEVICE_ID, THINGSBOARD_URL, "currentOperation")

            current_state_NR1 = read_attribute(USERNAME, PASSWORD, NODE_RED_1_DEVICE_ID, THINGSBOARD_URL, "currentState")
            current_state_NR2 = read_attribute(USERNAME, PASSWORD, NODE_RED_2_DEVICE_ID, THINGSBOARD_URL, "currentState")

            #print("Previous operation from NR1 :", previousOperation_NR1)

            sorted_operations = sort_operations_by_queue_position(new_operations) #sorted operations by queue position from digital twin
            #waiting_operations = sorted_operations
            prepared_order = several_orders #prepared variable which will be appended to the header and sent to the virtual device
            #print("Printing sorted operations",sorted_operations)

            #print("Sorted operations: ", sorted_operations)

            current_operation = sorted_operations[operation_count]

            

            if (previousOperation_NR1["metrics"]["status"] == "Finished" and current_state_NR1 == "Idle") or (operation_count == 0):
                #change status of the previous operation to "finished" for uploading to TB
                #prepared_order[0]["assembly"][current_operation["data"]["machineID"]]["metrics"]["status"] = "Finished" 
                
                #operacije modul1
                if (current_operation["data"]["machineID"] == "module1"):
                    update_attribute(USERNAME, PASSWORD, NODE_RED_1_DEVICE_ID, THINGSBOARD_URL, "currentOperation", current_operation)
                    operation_count += 1
                    print("Operation count: ", operation_count)
                    print("Current subpart: ", current_operation["data"]["part"])



                #transport
                elif (current_operation["data"]["AGVstartPos"] and current_operation["data"]["AGVendPos"]) != None:
                    operation_count = transport_operation(current_operation, operation_count)
  
                    
                #operacije modul2
                elif (previousOperation_NR2["metrics"]["status"] == "Finished") and (current_state_NR2 == "Idle"):
                    
                    if current_operation["data"]["machineID"] == "module2":
                        update_attribute(USERNAME, PASSWORD, NODE_RED_2_DEVICE_ID, THINGSBOARD_URL, "currentOperation", current_operation)
                        operation_count += 1
                        print("Operation count: ", operation_count)
                        print("Current subpart: ", current_operation["data"]["part"])





        except KeyError:
            pass

        except IndexError:
            update_attribute(USERNAME, PASSWORD, VIRTUAL_DEVICE_ID, THINGSBOARD_URL, "productionOrder", {})
            operation_count = 0
            print("Production order finished")

        time.sleep(3)
except KeyboardInterrupt:
    pass




#treba bo narediti datoteko bolj odporno

#Set-ExecutionPolicy -ExecutionPolicy Unrestricted -Scope CurrentUser
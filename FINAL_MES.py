#this is a new MES python file which is created on foundation of the previous MES file which is too much hardcoded

import logging
import requests
import time
import json
from datetime import datetime
import traceback
import threading

import FINAL_read_attribute as read
import FINAL_update_attribute as update
import FINAL_data_manipulation as manipulation
import FINAL_assembly_operations as assembly
import FINAL_transport_operations as transport

def reading_values():
    """
    This is a threading function for reading the values from TB.
    """
    global done, USERNAME, PASSWORD, credentials, THINGSBOARD_URL, order_data
    while not done:
        print("New reading loop")
        new_order_data = read.read_attribute(USERNAME, PASSWORD, credentials["misc_details"]["virtual_device"]["device_id"], THINGSBOARD_URL, "productionOrder")  # Placeholder for actual read operation
        with data_lock:
            order_data = new_order_data
            data_condition.notify()  # Notify that new data has been read
        time.sleep(3)
    return order_data

def assembly_function():#main assembly function
    """
    This is a threading function that sends assembly and transport operations to modules. 
    """
    global done, module_keys, USERNAME, PASSWORD, credentials, THINGSBOARD_URL, VIRTUAL_DEVICE_ID, operation_count, order_data
    while not done:
        print("New assembly loop")
        
        previous_operations_status = {}
        current_module_states = {}
        for i in module_keys:
            current_module_states.setdefault(i, []).append(read.read_attribute(USERNAME, PASSWORD, credentials["module_details"][i]["device_id"], THINGSBOARD_URL, "currentState"))
            previous_operations_status.setdefault(i, []).append(read.read_attribute(USERNAME, PASSWORD, credentials["module_details"][i]["device_id"], THINGSBOARD_URL, "currentOperation")["metrics"]["status"])
        #print(f"Current module states: {current_module_states}")
        #print(f"Previous operations states: {previous_operations_status}")

        with data_lock:
            # Wait for new data to be available
            while order_data is None and not done:
                data_condition.wait()  # Wait for notification
            if done:
                break
            local_order_data = order_data  # Capture current data


        try:
            sorted_operations = manipulation.sort_operations_by_queue_position(local_order_data)
            #print(sorted_operations)

            if operation_count > 0:
                previous_operation_group = sorted_operations[operation_count - 1]
            else:
                previous_operation_group = [None]

            
            current_operation_group = sorted_operations[operation_count]
            
            #zgoraj mora biti na tak način...
            #print(previous_operation_group)
            #print(current_operation_group)
            
            for i, j in zip(current_operation_group, previous_operation_group):
                
                current_module = i["data"]["machineID"] if i else None
                previous_module = j["data"]["machineID"] if j else None
                print(f"Current module {current_module}")
                print(f"Previous module {previous_module}")

            
                #try:#ko sem dodal to, mi več ne zažene transporta
                    # Determine if a transport operation is needed for the current operation
                needs_transport = (i["data"]["AGVstartPos"] is not None and i["data"]["AGVendPos"] is not None)
                #except:
                    #pass
                
                # Check if the previous operation is finished and the current module is idle
                if (previous_operations_status.get(current_module, [''])[0] == "Finished" and current_module_states.get(current_module, [''])[0] == "Idle") or operation_count == 0:
                    print(f"Prišel skozi prvi loop")
                    
                    # Perform transport operation if needed and after operation 2 is finished
                    print(f"previous_operations_status.get(previous_module, [''])[0] {previous_operations_status.get(previous_module, [''])[0]}")#WATAFAK JE TO?
                    if needs_transport and previous_operations_status.get(previous_module, [''])[0] == "Finished":
                        print(f"Needs transport {needs_transport}")
                        transport.main_transport_operation(i, j, operation_count, credentials)
                        assembly.basic_assembly_operation(i, operation_count, credentials)
                        operation_count += 1

                    if (i["data"]["AGVstartPos"] is None and i["data"]["AGVendPos"] is not None):
                        #transport at the beggining
                        transport.start_transport_operation(i, j, operation_count, credentials)
                    elif (i["data"]["AGVstartPos"] is not None and i["data"]["AGVendPos"] is None):
                        #transport at the end
                        assembly.basic_assembly_operation(i, operation_count, credentials)
                        transport.end_transport_operation(i, operation_count, credentials)
                        operation_count += 1
                        
                        
                    elif current_module == previous_module: #tole je zelooooo vprašljivo - kako bo delovalo ko bodo 3je moduli ali pa več izdelkov
                        # Increment operation count only after confirming the current operation is complete
                        assembly.basic_assembly_operation(i, operation_count, credentials)
                        operation_count += 1

                    elif operation_count == 0 and i != [None]: #TEST ZAKAJ MI TO POŽENE KO SE ZAKLJUČI OPERACIJA
                        print("napačna operacija")
                        print(f"TO MORA BITI PRAZNO: {sorted_operations}")
                        #print(i)
                        assembly.basic_assembly_operation(i, operation_count, credentials)
                        operation_count += 1

        #operation_count += 1 #increase the operation count only at the end of all operation in the thread in one loop
        #we will have to delete all other operation increases
        except IndexError:
            print("Ni nobenega naročila!")

        except Exception as e:
            print(f"An error occurred: {e}")
            traceback.print_exc()
            #the row above is used to debug the function

        except KeyboardInterrupt:
            print("Keyboard interrupt detected. Exiting...")
                    
        time.sleep(1)
        if (operation_count == len(sorted_operations)) and (operation_count != 0):
            update.update_attribute(USERNAME, PASSWORD, VIRTUAL_DEVICE_ID, THINGSBOARD_URL, "productionOrder", {})
            sorted_operations = []
            order_data = None #TO JE REŠILO PROBLEM ZAGONA PRVE OPERACIJE OB KONCU NALOGA
            operation_count = 0
            print(f"sorted operations: {sorted_operations}")
            print("Production order finished")
            

    return operation_count

#SETUP
#dodaj current operation status Finished. drugače ne bo zaštartala skripta! Zelo pomembno kadar razširimo proizvodnjo na nove module.
# Shared data
order_data = None
# Lock to protect access to order_data
data_lock = threading.Lock()
# Condition variable to signal changes in order_data
data_condition = threading.Condition(data_lock)

with open('FINAL_credentials.json', 'r') as cred:
    credentials = json.load(cred)["credentials"]

module_keys = credentials["module_details"].keys()
agv_keys = credentials["AGV_details"].keys()
print(module_keys, agv_keys)

#static credentials - they are always the same for all modules
USERNAME = credentials["thingsboard_data"]["username"]
PASSWORD = credentials["thingsboard_data"]["password"]
VIRTUAL_DEVICE_ID = credentials["misc_details"]["virtual_device"]["device_id"]
THINGSBOARD_URL = credentials["thingsboard_data"]["tb_url"]

operation_count = 0
for i in module_keys:
    update.update_attribute(USERNAME, PASSWORD, credentials["module_details"][i]["device_id"], THINGSBOARD_URL, "conveyorMessage", "Idle")
    update.update_attribute(USERNAME, PASSWORD, credentials["module_details"][i]["device_id"], THINGSBOARD_URL, "conveyorResponse", "Idle")

for i in agv_keys:
    #dodaj spremembo statusa tako da bo status == Finished
    update.update_attribute(USERNAME, PASSWORD, credentials["AGV_details"][i]["device_id"], THINGSBOARD_URL, "commandAGV", "Idle")

done = False #thread stopping variable


#MAIN LOOP 2

try:
    #start threads
    reading_thread = threading.Thread(target=reading_values)
    assembly_thread = threading.Thread(target=assembly_function)

    reading_thread.start()
    assembly_thread.start()

    while True:
        time.sleep(0.5) #keeping the main thread alive

except KeyboardInterrupt:
    print("\nStopping the script!")
    done = True
    
    reading_thread.join()
    assembly_thread.join()

    print("Script finished")
















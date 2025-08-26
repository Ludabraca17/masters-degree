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
        #print(new_order_data)
    return order_data

def assembly_function():  # main assembly function
    """
    This is a threading function that sends assembly and transport operations to modules. 
    """
    global done, module_keys, USERNAME, PASSWORD, credentials, THINGSBOARD_URL, VIRTUAL_DEVICE_ID, operation_count, order_data

    while not done:
        print("New assembly loop")
        
        previous_operations_status = {}
        current_module_states = {}
        for i in module_keys:
            current_module_states.setdefault(i, []).append(
                read.read_attribute(USERNAME, PASSWORD, credentials["module_details"][i]["device_id"], THINGSBOARD_URL, "currentState")
            )
            previous_operations_status.setdefault(i, []).append(
                read.read_attribute(USERNAME, PASSWORD, credentials["module_details"][i]["device_id"], THINGSBOARD_URL, "currentOperation")["metrics"]["status"]
            )
        #Check if we have finished the operation and update it to TB.
        
        with data_lock:
            while order_data is None and not done:
                data_condition.wait()
            if done:
                break
            local_order_data = order_data

        try:
            manipulation.update_order_data(order=local_order_data, credentials=credentials)
        except Exception as e:
            print(f"Napaka pri posodabljanju podatkov na TB: {e}")
            print(f"Podatki NISO posodobljeni na TB.")
            traceback.print_exc()

        #tukaj bomo namesto order_data uporabili local_order_data v funkcijah naprej

        try:
            sorted_operations = manipulation.sort_operations_by_queue_position(local_order_data)
            print(f"Sorted operations: {sorted_operations}")
            manipulation.get_next_operations(credentials=credentials, order_data=local_order_data, sorted_operations=sorted_operations)
            current_operation_group = sorted_operations[operation_count]

            # For previous operations, just check the last batch if operation_count > 0
            previous_operation_group = sorted_operations[operation_count - 1] if operation_count > 0 else []

            # Process each operation in the current batch
            for i, j in zip(current_operation_group, previous_operation_group + [None]*(len(current_operation_group) - len(previous_operation_group))):
                # No None padding expected now, so just extend previous_operation_group if shorter
                
                if i is None:
                    continue

                current_module = i["data"]["machineID"] if i else None
                previous_module = j["data"]["machineID"] if j else None
                print(f"Current module {current_module}")
                print(f"Previous module {previous_module}")

                try:
                    needs_transport = (i["data"]["AGVstartPos"] != "null" and i["data"]["AGVendPos"] != "null")
                    print("Transport needed!")
                except:
                    print("No transport needed")
                    needs_transport = False

                if (previous_operations_status.get(current_module, [''])[0] == "Finished" and current_module_states.get(current_module, [''])[0] == "Idle") or operation_count == 0:

                    if needs_transport and previous_operations_status.get(previous_module, [''])[0] == "Finished":
                        transport.main_transport_operation(i, j, operation_count, credentials)
                        assembly.basic_assembly_operation(i, operation_count, credentials)

                    elif (i["data"]["AGVstartPos"] == "null" and i["data"]["AGVendPos"] != "null"):
                        transport.start_transport_operation(i, j, operation_count, credentials)
                        assembly.basic_assembly_operation(i, operation_count, credentials)

                    elif (i["data"]["AGVstartPos"] != "null" and i["data"]["AGVendPos"] == "null"):
                        assembly.basic_assembly_operation(i, operation_count, credentials)
                        transport.end_transport_operation(i, operation_count, credentials)

                    elif current_module == previous_module:
                        assembly.basic_assembly_operation(i, operation_count, credentials)

                    elif operation_count == 0:
                        assembly.basic_assembly_operation(i, operation_count, credentials)

            # Wait until all ops in the batch are finished before incrementing
            try:
                while True:
                    # Refresh states
                    previous_operations_status = {}
                    current_module_states = {}
                    for m in module_keys:
                        current_module_states.setdefault(m, []).append(
                            read.read_attribute(USERNAME, PASSWORD, credentials["module_details"][m]["device_id"], THINGSBOARD_URL, "currentState")
                        )
                        previous_operations_status.setdefault(m, []).append(
                            read.read_attribute(USERNAME, PASSWORD, credentials["module_details"][m]["device_id"], THINGSBOARD_URL, "currentOperation")["metrics"]["status"]
                        )
                        
                    print(f"Previous operation states {previous_operations_status}")
                    #print(f"Current operation status {i}")
                    print(f"Current module states {current_module_states}")

                    all_finished = all(
                        op is None or (
                            previous_operations_status.get(op["data"]["machineID"], [''])[0] == "Finished" and
                            current_module_states.get(op["data"]["machineID"], [''])[0] == "Idle" and
                            read.read_attribute(USERNAME, PASSWORD, credentials["module_details"][op["data"]["machineID"]]["device_id"], THINGSBOARD_URL, "currentOperation")["metrics"]["status"] == "Finished"
                        )
                        for op in current_operation_group
                    )

                    if all_finished:
                        operation_count += 1
                        print(f"Batch {operation_count} completed")
                        break  # exit the waiting loop

                    time.sleep(1)  # Wait before checking again
            except KeyboardInterrupt:
                print("Keyboard interrupt detected. Exiting...")

        except IndexError:
            print("No production orders available!")

        except Exception as e:
            print(f"An error occurred: {e}")
            traceback.print_exc()

        except KeyboardInterrupt:
            print("Keyboard interrupt detected. Exiting...")
            return
                    
        time.sleep(1)

        if (operation_count == len(sorted_operations)) and (operation_count != 0):
            update.update_attribute(USERNAME, PASSWORD, VIRTUAL_DEVICE_ID, THINGSBOARD_URL, "finishedOrder", order_data)
            time.sleep(0.1)
            update.update_attribute(USERNAME, PASSWORD, VIRTUAL_DEVICE_ID, THINGSBOARD_URL, "productionOrder", {})
            sorted_operations = []
            order_data = None
            operation_count = 0
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
















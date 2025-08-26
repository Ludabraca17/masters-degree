#this is a new MES python file which is created on foundation of the previous MES file ("MES_python_file.py and FINAL_MES.py") which is too much hardcoded

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
import FINAL_setup as setup

# SETUP
with open('FINAL_credentials.json', 'r') as cred:
    credentials = json.load(cred)["credentials"]

module_keys = credentials["module_details"].keys()
agv_keys = credentials["AGV_details"].keys()
print(module_keys, agv_keys)

# static credentials - they are always the same for all modules
USERNAME = credentials["thingsboard_data"]["username"]
PASSWORD = credentials["thingsboard_data"]["password"]
VIRTUAL_DEVICE_ID = credentials["misc_details"]["virtual_device"]["device_id"]
THINGSBOARD_URL = credentials["thingsboard_data"]["tb_url"]

setup.setup()

done = False  # stopping variable
transport_operations = []

try:
    while not done:
        print("\n=== New main loop ===")

        # 1️⃣ Read latest order data from TB
        order_data = read.read_attribute(
            USERNAME,
            PASSWORD,
            credentials["misc_details"]["virtual_device"]["device_id"],
            THINGSBOARD_URL,
            "productionOrder"
        )
        print("Order data read from TB.")
        #print(f"Check order data: {order_data}")

        # 2️⃣ Read current states & operations from each module
        previous_operations_status = {}
        current_module_states = {}
        for i in module_keys:
            current_module_states.setdefault(i, []).append(
                read.read_attribute(USERNAME, 
                                    PASSWORD, 
                                    credentials["module_details"][i]["device_id"], 
                                    THINGSBOARD_URL, 
                                    "currentState")
            )
            previous_operations_status.setdefault(i, []).append(
                read.read_attribute(USERNAME, 
                                    PASSWORD, 
                                    credentials["module_details"][i]["device_id"], 
                                    THINGSBOARD_URL, 
                                    "currentOperation")["metrics"]["status"]
            )

        # 3️⃣ Sort and get next operations
        try:
            sorted_operations = manipulation.sort_operations_by_queue_position(order_data)

            operations_list = manipulation.get_next_operations(
                credentials=credentials,
                order_data=order_data,
                sorted_operations=sorted_operations
            )
            print(f"Operations to send: {operations_list}")

            # 4️⃣ Send next operations to modules
            for i in operations_list:
                if i is None:
                    continue

                current_module = i["data"]["machineID"] if i else None
                print(f"Current module {current_module}")

                needs_transport = (i["data"]["AGVstartPos"] != "null" and i["data"]["AGVendPos"] != "null")

                if needs_transport and i["metrics"]["status"] != "Transport done":
                    print("Transport needed!")
                    #TUKAJ NAŠTUDIRAJ KAKO DRUGAČE NAREDITI DA GRE ČE JE TRANSPORTING NAJ GA DA NAPREJ V SEZNAMU
                    # mark as processing when dispatched
                    #i["metrics"]["status"] = "Processing"
                    # push transport to front of queue (priority)
                    transport_operations.insert(0, i)
                    continue

                elif (i["data"]["AGVstartPos"] == "null" and i["data"]["AGVendPos"] != "null"):
                    print("ZACETNI TRANSPORT")
                    i["metrics"]["status"] = "Processing"
                    update.update_attribute(
                        USERNAME, PASSWORD,
                        credentials["module_details"][i["data"]["machineID"]]["device_id"],
                        THINGSBOARD_URL,
                        "currentOperation", i
                    )
                    time.sleep(2)

                elif (i["data"]["AGVstartPos"] != "null" and i["data"]["AGVendPos"] == "null"):
                    print("KONCNI TRANSPORT")
                    i["metrics"]["status"] = "Processing"
                    update.update_attribute(
                        USERNAME, PASSWORD,
                        credentials["module_details"][i["data"]["machineID"]]["device_id"],
                        THINGSBOARD_URL,
                        "currentOperation", i
                    )
                    time.sleep(2)

                else:
                    print("NAVADNA OPERACIJA")
                    i["metrics"]["status"] = "Processing"
                    update.update_attribute(
                        USERNAME, PASSWORD,
                        credentials["module_details"][i["data"]["machineID"]]["device_id"],
                        THINGSBOARD_URL,
                        "currentOperation", i
                    )
                    time.sleep(0.5)

            # 5️⃣ Run active transports
            if transport_operations:
                transport_operations, completed_operations, order_data = transport.transport_operation_between_modules(transport_operations, credentials, order_data)
                for completed_op in completed_operations:
                    # Find and update the operation in order_data
                    for product in order_data["productData"][0]["products"]:
                        for op_id, op_data in product["assembly"].items():
                            if op_data["data"]["uniqueOpID"] == completed_op["data"]["uniqueOpID"]:
                                # Update the operation in order_data
                                product["assembly"][op_id] = completed_op
                                print(f"Updated operation {completed_op['data']['uniqueOpID']} in order_data to status: {completed_op['metrics']['status']}")
                                break
                
                try:
                    #print(f"Check order data: {order_data}")
                    manipulation.update_order_data(order=order_data, credentials=credentials)
                except Exception as e:
                    print(f"Error updating TB order data: {e}")
                    traceback.print_exc()
        
            # 6️⃣ Update order data in TB if something finished
            try:
                # Refresh order_data to get the latest statuses from ThingsBoard
                order_data = read.read_attribute(
                    USERNAME,
                    PASSWORD,
                    VIRTUAL_DEVICE_ID,
                    THINGSBOARD_URL,
                    "productionOrder"
                )
                #print(f"Check order data: {order_data}")
                manipulation.update_order_data(order=order_data, credentials=credentials)
            except Exception as e:
                print(f"Error updating TB order data: {e}")
                traceback.print_exc()

        except Exception as e:
            print(f"Error in main loop: {e}")
            traceback.print_exc()

        # 7️⃣ Check if production is finished
        all_finished = True
        try:
            for product in order_data["productData"][0]["products"]:
                for op_id, op_data in product["assembly"].items():
                    if op_data["metrics"]["status"] != "Finished":
                        all_finished = False
                        break
                if not all_finished:
                    break
        except Exception as e:
            print(e)

        if all_finished:
            if order_data != {}:
                update.update_attribute(USERNAME, 
                                        PASSWORD, 
                                        VIRTUAL_DEVICE_ID, 
                                        THINGSBOARD_URL, 
                                        "finishedOrder", 
                                        order_data)
            time.sleep(0.1)
            
            update.update_attribute(USERNAME, 
                                    PASSWORD, 
                                    VIRTUAL_DEVICE_ID, 
                                    THINGSBOARD_URL, 
                                    "productionOrder", 
                                    {})
            sorted_operations = []
            order_data = None
            print("Production order finished")

        # 8️⃣ Wait before next cycle
        time.sleep(1) #TO SKRAJŠAJ KO ZAKLJUČIŠ IN STESTIRAJ NA KRAJŠE CIKLE LOOPA

except KeyboardInterrupt:
    print("\nStopping the script!")
    done = True

print("Script finished")

#Tole spodaj je dober način za filtriranje ali bomo transportiral ter kam in kako 
"""
start = i["data"].get("AGVstartPos")
end   = i["data"].get("AGVendPos")

if not start and end:
    # start transport
elif start and not end:
    # end transport

"""
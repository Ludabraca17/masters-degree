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


#SETUP
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



#MAIN LOOP
try:
    while True:
        print("New while loop")
        
        previous_operations_status = {}
        current_module_states = {}
        for i in module_keys:
            current_module_states.setdefault(i, []).append(read.read_attribute(USERNAME, PASSWORD, credentials["module_details"][i]["device_id"], THINGSBOARD_URL, "currentState"))
            previous_operations_status.setdefault(i, []).append(read.read_attribute(USERNAME, PASSWORD, credentials["module_details"][i]["device_id"], THINGSBOARD_URL, "currentOperation")["metrics"]["status"])
        print(f"Current module states: {current_module_states}")
        print(f"Previous operations states: {previous_operations_status}")

        try:
            order_data = read.read_attribute(USERNAME, PASSWORD, credentials["misc_details"]["virtual_device"]["device_id"], THINGSBOARD_URL, "productionOrder")
            sorted_operations = manipulation.sort_operations_by_queue_position(order_data)
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
                
                current_module = i["data"]["machineID"]
                previous_module = j["data"]["machineID"] if j else None
                print(f"Current module {current_module}")
                print(f"Previous module {previous_module}")

                for k in range(0, len(max([i, j], key=len)), 1):

                    if i or j == []:
                        print("Znotraj for zanke, eden izmez listov prazen")

                        
                    else:
                        pass



        except Exception as e:
            print(f"An error occurred: {e}")
                


        
        time.sleep(1)
        if (operation_count == len(sorted_operations)) and (operation_count != 0):
            update.update_attribute(USERNAME, PASSWORD, VIRTUAL_DEVICE_ID, THINGSBOARD_URL, "productionOrder", {})
            operation_count = 0
            print("Production order finished")
            break #to pozneje daj stran drugače se ti skripta ustavi

except KeyboardInterrupt:
    pass


#transport operations (start, between assembly, end)

#assembly operations 

#data operations (sorting, putting together for TB...)


"""
for i, j in zip(current_operation_group, previous_operation_group):

                if i or j == []:
                    print("Znotraj for zanke, eden izmez listov prazen")
                    current_module = i["data"]["machineID"]
                    previous_module = j["data"]["machineID"] if j else None
                    print(f"Current module {current_module}")
                    print(f"Previous module {previous_module}")

                    # Determine if a transport operation is needed for the current operation
                    needs_transport = (i["data"]["AGVstartPos"] is not None and i["data"]["AGVendPos"] is not None)
                    

                    # Check if the previous operation is finished and the current module is idle
                    if (previous_operations_status.get(current_module, [''])[0] == "Finished" and current_module_states.get(current_module, [''])[0] == "Idle") or operation_count == 0:
                        
                        
                        # Perform transport operation if needed and after operation 2 is finished
                        if needs_transport and previous_operations_status.get(previous_module, [''])[0] == "Finished":
                            print(f"Needs transport {needs_transport}")
                            operation_count = transport.main_transport_operation(i, j, operation_count, credentials)

                        if (i["data"]["AGVstartPos"] is None and i["data"]["AGVendPos"] is not None):
                            #transport at the beggining
                            transport.start_transport_operation(i, j, operation_count, credentials)
                        elif (i["data"]["AGVstartPos"] is not None and i["data"]["AGVendPos"] is None):
                            #transport at the end
                            transport.end_transport_operation(i, operation_count, credentials)
                            operation_count += 1
                        elif current_module == previous_module: #tole je zelooooo vprašljivo - kako bo delovalo ko bodo 3je moduli ali pa več izdelkov
                            # Increment operation count only after confirming the current operation is complete
                            operation_count = assembly.basic_assembly_operation(i, operation_count, credentials)

                        elif operation_count == 0:
                            operation_count = assembly.basic_assembly_operation(i, operation_count, credentials)

                else:
                    for k in range(0, len(max([i, j], key=len)), 1):
                        print("Znotraj for zanke, oba lista polna")

                        current_module = i[k]["data"]["machineID"]
                        previous_module = j[k]["data"]["machineID"] if j else None
                        print(f"Current module {current_module}")
                        print(f"Previous module {previous_module}")

                        # Determine if a transport operation is needed for the current operation
                        needs_transport = (i[k]["data"]["AGVstartPos"] is not None and i[k]["data"]["AGVendPos"] is not None)
                        

                        # Check if the previous operation is finished and the current module is idle
                        if (previous_operations_status.get(current_module, [''])[0] == "Finished" and current_module_states.get(current_module, [''])[0] == "Idle") or operation_count == 0:
                            
                            
                            # Perform transport operation if needed and after operation 2 is finished
                            if needs_transport and previous_operations_status.get(previous_module, [''])[0] == "Finished":
                                print(f"Needs transport {needs_transport}")
                                operation_count = transport.main_transport_operation(i[k], j[k], operation_count, credentials)

                            if (i[k]["data"]["AGVstartPos"] is None and i[k]["data"]["AGVendPos"] is not None):
                                transport.start_transport_operation(i[k], j[k], operation_count, credentials)
                                #transport at the beginning
                            elif (i[k]["data"]["AGVstartPos"] is not None and i[k]["data"]["AGVendPos"] is None):
                                operation_count = transport.end_transport_operation(i[k], operation_count, credentials)
                                #transport at the end
                            elif current_module == previous_module: #tole je zelooooo vprašljivo - kako bo delovalo ko bodo 3je moduli ali pa več izdelkov
                                # Increment operation count only after confirming the current operation is complete
                                operation_count = assembly.basic_assembly_operation(i[k], operation_count, credentials)

                            elif operation_count == 0:
                                operation_count = assembly.basic_assembly_operation(i[k], operation_count, credentials)
"""
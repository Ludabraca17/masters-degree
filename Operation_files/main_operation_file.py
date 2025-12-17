#this is a new MES python file which is created on foundation of the previous MES file ("MES_python_file.py and FINAL_MES.py") which are too much hardcoded

import logging
import requests
import time
import json
from datetime import datetime
import traceback
import os
from typing import Dict, Any
from pathlib import Path

import read_attribute as read
import update_attribute as update
import data_manipulation as manipulation
import assembly_operations as assembly
import transport_operations as transport
import setup as setup
import logging_functions as logging

# This is not necessary - easter egg
def print_creepy_ascii_art(file_path="image.txt"):
    with open(file_path, "r", encoding="utf-8") as file:
        print(file.read())

# What we think about possible assembly times
IDEAL_TIMES = {"101": 7.5, "102": 7.5, "103": 7.5, "104": 7.5, "105": 7.5,
                "module1:trainBase": 7.5, "module1:trainWheels": 7.5,
                "module2:trainEngine": 7.5, "module2:trainCabin": 7.5,
                "module3:trainChimney": 7.5}

def _transport_closed(op: dict) -> bool:
    """Checks if the end transport operation is finished, by looking at "finalTransport" flag, which we add 
    with _is_final_op() within the loop.

    Args:
        op (dict): Operation that is being evaluated.

    Returns:
        bool: True if the transport op is finished and False if it is not.
    """
    d, m = op.get("data", {}) or {}, op.get("metrics", {}) or {}
    if _is_final_op(op):
        return m.get("finalTransport") == "Done"
    # začetni/vmesni
    return bool(m.get("transportEndTs"))

def _is_true(v) -> bool:
    """Robustno pretvori TB/DN informacijo v bool."""
    if isinstance(v, bool):   return v
    if isinstance(v, (int,float)): return v == 1
    if isinstance(v, str):    return v.strip().lower() in ("true","1","yes","y")
    return False

def _is_final_op(op: dict) -> bool:
    """Checks if an operation is the final operation in a product and gives it an "endFlag" key with a flag "False".
    It is used so that we know when to initiate end transport.

    Args:
        op (dict): Operation that is being evaluated.

    Returns:
        bool: True if the op is final and False if it is not.
    """
    d = op.get("data", {}) or {}
    return _is_true(d.get("endFlag", False))  # privzeto False, če zastavice ni

# SETUP 
BASE_DIR = Path(__file__).resolve().parent
credentials_path = BASE_DIR / "credentials.json"

with open(credentials_path, 'r') as cred:
    credentials = json.load(cred)["credentials"]

module_keys = credentials["module_details"].keys()
agv_keys = credentials["AGV_details"].keys()
print(module_keys, agv_keys)

# static credentials - they are always the same for all modules
USERNAME = credentials["thingsboard_data"]["username"]
PASSWORD = credentials["thingsboard_data"]["password"]
VIRTUAL_DEVICE_ID = credentials["misc_details"]["virtual_device"]["device_id"]
THINGSBOARD_URL = credentials["thingsboard_data"]["tb_url"]

setup.setup(credentials)

done = False  # stopping variable
transport_operations = []
start_trans_operations = []
end_trans_operations = []

# START of the main loop
try:
    while not done:
        print("\n=== New main loop ===")

        # Read latest order data from TB
        order_data = read.read_attribute(
            USERNAME,
            PASSWORD,
            credentials["misc_details"]["virtual_device"]["device_id"],
            THINGSBOARD_URL,
            "productionOrder"
        )
        
        if order_data:
            print("Order data read from TB.")
            #
            logging.mark_order_start(order_data)
            #
            #print(f"Check order data: {order_data}")
            
            #order_data = manipulation.update_order_data(order=order_data, credentials=credentials)
            
            # Read current states & operations from each module
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

            # Sort and get next operations
            try:
                sorted_operations = manipulation.sort_operations_by_queue_position(order_data)
                
                order_data = manipulation.tag_final_ops_with_endflag(order_data)
                
                operations_list = manipulation.get_next_operations(
                    credentials=credentials,
                    sorted_operations=sorted_operations
                )
                print(f"Operations to send: {operations_list}")

                # 4️⃣ Send next operations to modules
                for i in operations_list:
                    if i is None:
                        continue

                    current_module = i["data"]["machineID"] if i else None
                    print(f"Current module {current_module}")
                    status_now = i["metrics"].get("status")

                    d = i.get("data", {}) or {}
                    start_pos = d.get("AGVstartPos", "null")
                    end_pos   = d.get("AGVendPos", "null")

                    is_final       = _is_final_op(i)  # varno, tudi če endFlag manjka
                    needs_transport = (start_pos != "null" and end_pos != "null" and status_now != "Finished")
                    start_trans     = (start_pos == "null" and end_pos != "null")
                    end_trans       = (is_final)  # semantika; fazo preveriš posebej z metrics
                    
                    m = i.get("metrics", {}) or {}
                    final_ready = is_final and (m.get("status") == "Finished" or m.get("finalTransport") == "InProgress")
                    
                    

                    if needs_transport and i["metrics"]["status"] != "Transport done" and not _transport_closed(i):
                        print("Transport needed!")
                        #TUKAJ NAŠTUDIRAJ KAKO DRUGAČE NAREDITI DA GRE ČE JE TRANSPORTING NAJ GA DA NAPREJ V SEZNAMU
                        # mark as processing when dispatched
                        #i["metrics"]["status"] = "Processing"
                        # push transport to front of queue (priority)
                        transport_operations.insert(0, i)
                        continue

                    elif start_trans and i["metrics"]["status"] != "Transport done" and not _transport_closed(i):
                        print("ZACETNI TRANSPORT")
                        start_trans_operations.insert(0, i)
                        time.sleep(0.5)
                        continue

                    elif final_ready and not _transport_closed(i):
                        print("skozi končni elif!!!")
                        
                        task = manipulation.build_final_transport_task(i, default_agv=i["data"]["AGV"])
                        task["metrics"]["status"] = "Finished"

                        print("KONČNI TRANSPORT JEBEM TI MATER")
                        end_trans_operations.insert(0, task)
                        time.sleep(0.5)
                        continue
                    
                    elif status_now in ("Waiting", "Transport done"):
                        print("NAVADNA OPERACIJA")
                        i["metrics"]["status"] = "Processing"
                        #
                        logging.stamp_operation_metrics(i["metrics"], new_status="Processing")
                        #
                        update.update_attribute(
                            USERNAME, PASSWORD,
                            credentials["module_details"][i["data"]["machineID"]]["device_id"],
                            THINGSBOARD_URL,
                            "currentOperation", i
                        )
                        time.sleep(0.5)

                # Run active transports
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

                #dodaj za začetni in končni transport?
                if start_trans_operations:
                    print("DEJANSKO IZVAJAMO TRANSPORT!!!!!!!!!!")
                    start_trans_operations, start_completed_operations, order_data = transport.start_transport(start_trans_operations, credentials, order_data)
                    for completed_op in start_completed_operations:
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
                        
                if end_trans_operations:
                    print("IZVAJAMO KONČNI TRANSPORT…")
                    end_trans_operations, end_completed_operations, order_data = transport.end_transport(end_trans_operations, credentials, order_data)
                    print(end_trans_operations)
                    for completed_op in end_completed_operations:
                        uid = completed_op["data"]["uniqueOpID"]
                        for product in order_data["productData"][0]["products"]:
                            for op_id, op_data in product["assembly"].items():
                                if op_data["data"]["uniqueOpID"] == uid:
                                    op_m = op_data.setdefault("metrics", {})
                                    # prepiši relevantne metrike
                                    op_m.update({
                                        "status": "End transport done",
                                        "finalTransport": "Done",
                                        # če želiš prenesti še vožnjo
                                        "transportStartTs": completed_op["metrics"].get("transportStartTs", op_m.get("transportStartTs")),
                                        "transportEndTs":   completed_op["metrics"].get("transportEndTs",   op_m.get("transportEndTs")),
                                    })
                                    print(f"Updated FINAL transport for {uid} to: {op_m['status']} (lock={op_m.get('finalTransport')})")
                                    break
                    try:
                        #print(f"Check order data: {order_data}")
                        manipulation.update_order_data(order=order_data, credentials=credentials)
                    except Exception as e:
                        print(f"Error updating TB order data: {e}")
                        traceback.print_exc()
                
                # Update order data in TB if something finished
                try:
                    # Refresh order_data to get the latest statuses from ThingsBoard
                    
                    #print(f"Check order data: {order_data}")
                    order_data = manipulation.update_order_data(order=order_data, credentials=credentials)
                except Exception as e:
                    print(f"Error updating TB order data: {e}")
                    traceback.print_exc()

            except Exception as e:
                print(f"Error in main loop: {e}")
                traceback.print_exc()

            # Check if production is finished – upošteva 'endFlag' + 'Transport done'
            # === Strict completion check across products ===
            try:
                ready, blockers = manipulation.is_order_ready_to_close(order_data)
            except Exception as e:
                print(f"[WARN] completion check failed: {e}")
                ready, blockers = False, [("n/a", "exception")]
                
            # minimal guard
            #any_endflags_left = any(
                #op.get("data", {}).get("endFlag") for p in order_data["productData"][0]["products"]
                #for op in p.get("assembly", {}).values()
            #)

            #buffers_busy = bool(transport_operations or start_trans_operations or end_trans_operations)
            buffers_busy = False

            if not ready or buffers_busy:
                if buffers_busy:
                    print("[INFO] Order not done; transport buffers not empty.")
                if blockers:
                    print("[INFO] Order not done; per-product blockers:")
                    for idx, why in blockers:
                        print(f"  - product#{idx}: {why}")
            else:
                # Pred zaprtjem DN: pretvori vse finalne op iz 'End transport done' -> 'Finished' + endTs
                for product in order_data["productData"][0]["products"]:
                    for _k, op in product["assembly"].items():
                        d, m = op.get("data", {}), op.get("metrics", {})
                        if d.get("endFlag") is True and m.get("status") == "End transport done":
                            logging.stamp_operation_metrics(m, new_status="Finished")
                            #m["status"] = "Finished"

                # standardni zaključni koraki
                logging.mark_order_end(order_data)
                if order_data != {}:
                    update.update_attribute(USERNAME, PASSWORD, VIRTUAL_DEVICE_ID, THINGSBOARD_URL, "finishedOrder", order_data)
                time.sleep(0.1)
                extra = logging.summarize_for_kpi(order_data, ideal_times=IDEAL_TIMES)
                logging.save_finished_order(order_data, out_dir="finished_orders", write_jsonl=True, extra_summary=extra)
                update.update_attribute(USERNAME, PASSWORD, VIRTUAL_DEVICE_ID, THINGSBOARD_URL, "productionOrder", {})
                sorted_operations = []
                order_data = None
                for i in module_keys:
                    last_op = read.read_attribute(USERNAME, PASSWORD, credentials["module_details"][i]["device_id"], THINGSBOARD_URL, "currentOperation")
                    setup_op = last_op
                    setup_op["metrics"]["status"] = "Setup"

                    update.update_attribute(USERNAME, PASSWORD, credentials["module_details"][i]["device_id"], THINGSBOARD_URL, "currentOperation", setup_op)
                    update.update_attribute(USERNAME, PASSWORD, credentials["module_details"][i]["device_id"], THINGSBOARD_URL, "conveyorMessage", "Idle")
                    update.update_attribute(USERNAME, PASSWORD, credentials["module_details"][i]["device_id"], THINGSBOARD_URL, "conveyorResponse", "Idle")
                #clear variables that overwrite orders
                transport_operations.clear()
                start_trans_operations.clear()
                end_trans_operations.clear()
                print_creepy_ascii_art() #zbriši pozneje :)
                print("Production order finished")
        else:
            print("No order submitted!")
        # Wait before next cycle
        time.sleep(1) #TO SKRAJŠAJ KO ZAKLJUČIŠ IN STESTIRAJ NA KRAJŠE CIKLE LOOPA

except KeyboardInterrupt:
    print("\nStopping the script!")
    done = True

print("Script finished")


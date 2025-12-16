# This file contains transport functions
# The functions currently handle transport with AMRs. They are set to automatic operation, which means AMR is functional and is actually moving the products.
# MANUAL mode means that in TB you manually set positions and signals of an AMR. You will have to uncoment some code parts which set state of AMR to IDLE.
import FINAL_update_attribute as update
import FINAL_read_attribute as read
import logging_functions as logging
import time

def start_transport(transport_operations: list, 
                    credentials: dict, 
                    order: dict) -> tuple:
    """
    Starts all possible START transport operations with the list of transport operations provided.
    
    The function utilizes the list of transport operations which are deemed for start transport. 
    It checks the status of each transport operation and triggers the start of transport if the conditions are met.
    It is expected that a single transport operation will will not be finished in a single loop so it enables a step-by-step
    progression of the transport operation from "Waiting" to "Transport done". It checks for status of modules and AMR with
    credentials and order data provided.

    Args:
        transport_operations (list): List of active transport operations.
        credentials (dict): Credentials for ThingsBoard access.
        order (dict): Dictionary of operations and a header in an order.

    Returns:
        tuple[list, list, dict]
        - transport_operations (list): List of active transport operations after processing.
        - completed_operations (list): List of completed transport operations.
        - order_data (dict): Product data with updated transport operation statuses.
    """
    USERNAME = credentials["thingsboard_data"]["username"]
    PASSWORD = credentials["thingsboard_data"]["password"]
    VIRTUAL_DEVICE_ID = credentials["misc_details"]["virtual_device"]["device_id"]
    THINGSBOARD_URL = credentials["thingsboard_data"]["tb_url"]
    
    order_data = order
    completed_operations = []
    
    for current_operation in transport_operations:
        start_pos = current_operation["data"].get("AGVstartPos", "null") # Currently warehouse or manual loading so we are expecting "null"
        end_pos = current_operation["data"].get("AGVendPos", "null") 
        agv = current_operation["data"].get("AGV", "null")
        status = current_operation["metrics"]["status"]
        
        machine = current_operation["data"]["machineID"]
        print(f"Transport from {start_pos} to {end_pos}")
        print(f"Status modula {machine}: {status}")
        
        if status == "Transport done":
            completed_operations.append(current_operation)
            continue
        
        agv_status = read.read_attribute(USERNAME, 
                                            PASSWORD, 
                                            credentials["AGV_details"][current_operation["data"]["AGV"]]["device_id"],
                                            THINGSBOARD_URL, 
                                            "status")
        
        target_module = read.read_attribute(USERNAME, 
                                            PASSWORD, 
                                            credentials["AGV_details"][current_operation["data"]["AGV"]]["device_id"],
                                            THINGSBOARD_URL, 
                                            "targetModule")
        
        # Leave for possible adition of storage module REALLY?
        #conveyor_response = read.read_attribute(USERNAME,
                                                #PASSWORD,
                                                #credentials["module_details"][start_pos]["device_id"],
                                                #THINGSBOARD_URL,
                                                #"conveyorResponse")
        print(f"Stanje AGV: {agv_status}")
        print(f"Target module: {target_module}")
        
        if status == "Waiting":
            print(f"[AGV] Starting {agv} transport {start_pos} → {end_pos}")
            #
            logging.stamp_operation_metrics(current_operation["metrics"], new_status="Transporting", transport_event="start")
            logging.mark_initial_transport(current_operation["metrics"], "start")
            #
            # Not necessary but prepared for logging if we add a palet storage module
            logging.mark_transport_go(current_operation["metrics"])
            #
            update.update_attribute(USERNAME,
                                    PASSWORD,
                                    credentials["AGV_details"][current_operation["data"]["AGV"]]["device_id"],
                                    THINGSBOARD_URL,
                                    "commandAGV",
                                    "Go")
            
            current_operation["metrics"]["status"] = "Transporting"
            for product in order_data["productData"][0]["products"]:
                for op_id, op_data in product["assembly"].items():
                    if op_data["data"]["uniqueOpID"] == current_operation["data"]["uniqueOpID"]:
                        product["assembly"][op_id] = current_operation
        
        elif status == "Transporting":
            if agv_status == "Delivered" : #and end_pos == target_module #UNCOMMENT target_module IF MULTIPLE AMR USED
                print("ko napišem delivered")
                #update.update_attribute(USERNAME,
                                        #PASSWORD,
                                        #credentials["module_details"][start_pos]["device_id"],
                                        #THINGSBOARD_URL,
                                        #"conveyorResponse",
                                        #"Idle")
                update.update_attribute(USERNAME,
                                        PASSWORD,
                                        credentials["module_details"][end_pos]["device_id"],
                                        THINGSBOARD_URL,
                                        "conveyorMessage",
                                        "Prepare for assembly")
                time.sleep(0.5)
                # AMR to Idle if MANUAL mode
                update.update_attribute(USERNAME,
                                        PASSWORD,
                                        credentials["AGV_details"][current_operation["data"]["AGV"]]["device_id"],
                                        THINGSBOARD_URL,
                                        "status",
                                        "Idle")
                update.update_attribute(USERNAME,
                                        PASSWORD,
                                        credentials["AGV_details"][current_operation["data"]["AGV"]]["device_id"],
                                        THINGSBOARD_URL,
                                        "targetModule",
                                        "Idle")
                #
                
                update.update_attribute(USERNAME,
                                    PASSWORD,
                                    credentials["AGV_details"][current_operation["data"]["AGV"]]["device_id"],
                                    THINGSBOARD_URL,
                                    "commandAGV",
                                    "Idle")
                print("Čakam da trak odpelje kos na montažno mesto")
                
            if read.read_attribute(USERNAME,
                                    PASSWORD,
                                    credentials["module_details"][end_pos]["device_id"],
                                    THINGSBOARD_URL,
                                    "conveyorResponse") == "Prepared":
                print("zadnji if, da zaključimo funkcijo")
                update.update_attribute(USERNAME,
                                        PASSWORD,
                                        credentials["module_details"][end_pos]["device_id"],
                                        THINGSBOARD_URL,
                                        "conveyorResponse",
                                        "Idle")
                print(f"[AGV] {agv} completed transport {start_pos} → {end_pos}")
                current_operation["metrics"]["status"] = "Transport done"
                current_operation["data"]["AGVstartPos"] = "null"
                current_operation["data"]["AGVendPos"] = "null"
                #
                logging.stamp_operation_metrics(current_operation["metrics"], new_status="Transport done", transport_event="end")
                logging.mark_initial_transport(current_operation["metrics"], "end") 
                #
            
        elif status in ("Finished", "Transport done"):
            completed_operations.append(current_operation)
            continue  # Skip the rest of the loop iteration
        
    # Remove completed transports from the active list
    for op in completed_operations:
        if op in transport_operations:
            transport_operations.remove(op)

    # Prioritize operations that are still "Transporting"
    transport_operations = sorted(
        transport_operations,
        key=lambda op: op["metrics"]["status"] != "Transporting"
    )
    return  transport_operations, completed_operations, order_data

def end_transport(transport_operations: list, 
                credentials: dict, 
                order: dict) -> tuple:
    """
    Starts all possible END transport operations with the list of transport operations provided.
    
    The function utilizes the list of transport operations which are deemed for end transport.
    It checks the status of each transport operation and triggers the end of transport if the conditions are met.
    It is expected that a single transport operation will not be finished in a single loop so it enables a step-by-step
    progression of the transport operation from "Finished" to "End transport done". It checks for status of modules and AMR with
    credentials and order data provided. At the end of the transport operation it marks the operation as "End transport done"
    which is necessary for ending of the entire order.

    Args:
        transport_operations (list): List of active transport operations.
        credentials (dict): Credentials for ThingsBoard access.
        order (dict): Dictionary of operations and a header in an order.

    Returns:
        tuple[list, list, dict]
        - transport_operations (list): List of active transport operations after processing.
        - completed_operations (list): List of completed transport operations.
        - order_data (dict): Product data with updated transport operation statuses.
    """
    USERNAME = credentials["thingsboard_data"]["username"]
    PASSWORD = credentials["thingsboard_data"]["password"]
    THINGSBOARD_URL = credentials["thingsboard_data"]["tb_url"]
    

    order_data = order
    completed_operations = []

    for current_operation in list(transport_operations):
        start_pos = current_operation["data"].get("AGVstartPos", "null")
        end_pos   = current_operation["data"].get("AGVendPos", "null")   # We are expecting "null"
        agv_id    = current_operation["data"].get("AGV", "AGV1")
        status    = current_operation["metrics"].get("status")
        if start_pos == "null" or agv_id == "null":
            continue 
        
        machine = current_operation["data"]["machineID"]

        agv_status = read.read_attribute(
            USERNAME, PASSWORD, credentials["AGV_details"][agv_id]["device_id"],
            THINGSBOARD_URL, "status"
        )
        conveyor_response = read.read_attribute(
            USERNAME, PASSWORD, credentials["module_details"][start_pos]["device_id"],
            THINGSBOARD_URL, "conveyorResponse"
        )
        
        target_module = read.read_attribute(USERNAME, 
                                            PASSWORD, 
                                            credentials["AGV_details"][current_operation["data"]["AGV"]]["device_id"],
                                            THINGSBOARD_URL, 
                                            "targetModule")

        # 1) Waiting -> prepare AMR in conveyor
        if status == "Finished":
            update.update_attribute(USERNAME, PASSWORD, credentials["module_details"][start_pos]["device_id"],
                                    THINGSBOARD_URL, "conveyorMessage", "Start")
            update.update_attribute(USERNAME, PASSWORD, credentials["AGV_details"][agv_id]["device_id"],
                                    THINGSBOARD_URL, "commandAGV", "Prepare")
            current_operation["metrics"]["status"] = "Waiting for transport"
            print(current_operation)
            # write back to order data
            for product in order_data["productData"][0]["products"]:
                for op_id, op_data in product["assembly"].items():
                    if op_data["data"]["uniqueOpID"] == current_operation["data"]["uniqueOpID"]:
                        product["assembly"][op_id] = current_operation
            continue

        # 2) Waiting for transport + AMR is actually waiting -> send to AMR
        elif status == "Waiting for transport" and agv_status == "Waiting" :#and start_pos == target_module #UNCOMMENT target_module IF MULTIPLE AMR USED
            update.update_attribute(USERNAME, 
                                    PASSWORD, 
                                    credentials["module_details"][start_pos]["device_id"],
                                    THINGSBOARD_URL, 
                                    "conveyorMessage", 
                                    "AGV ready")
            
            print("Pošiljam ukaz za transport na drugi modul") #ZA STRAN?
            update.update_attribute(USERNAME,
                                    PASSWORD,
                                    credentials["AGV_details"][current_operation["data"]["AGV"]]["device_id"],
                                    THINGSBOARD_URL,
                                    "commandAGV",
                                    "Go")
            time.sleep(0.5)
            update.update_attribute(USERNAME, PASSWORD, credentials["AGV_details"][agv_id]["device_id"],
                                    THINGSBOARD_URL, "status", "Idle")
            #
            logging.stamp_operation_metrics(current_operation["metrics"], new_status="Transporting", transport_event="start")
            logging.mark_final_transport(current_operation["metrics"], "start")
            #
            
            # AMR to Idle if MANUAL mode
            update.update_attribute(USERNAME, 
                                    PASSWORD, 
                                    credentials["AGV_details"][agv_id]["device_id"],
                                    THINGSBOARD_URL, 
                                    "status", 
                                    "Idle")
            update.update_attribute(USERNAME,
                                    PASSWORD,
                                    credentials["AGV_details"][current_operation["data"]["AGV"]]["device_id"],
                                    THINGSBOARD_URL,
                                    "targetModule",
                                    "Idle")
            #
            
            current_operation["metrics"]["status"] = "Transporting"
            for product in order_data["productData"][0]["products"]:
                for op_id, op_data in product["assembly"].items():
                    if op_data["data"]["uniqueOpID"] == current_operation["data"]["uniqueOpID"]:
                        product["assembly"][op_id] = current_operation
            continue

        # 3) Transporting -> when AMR returns Delivered we complete the transport
        elif status == "Transporting" : #and start_pos == target_module #UNCOMMENT target_module IF MULTIPLE AMR USED
            #if agv_status == "Delivered" and end_pos == target_module: #leave this for possibility of warehouse module
                #pass
            update.update_attribute(USERNAME, 
                                    PASSWORD, 
                                    credentials["module_details"][start_pos]["device_id"],
                                    THINGSBOARD_URL, 
                                    "conveyorResponse", 
                                    "Idle")
            time.sleep(0.5)
            #
            logging.stamp_operation_metrics(current_operation["metrics"], new_status="End transport done", transport_event="end")
            logging.mark_final_transport(current_operation["metrics"], "end")
            #
            current_operation["metrics"]["status"] = "End transport done"
            # AMR to Idle if MANUAL mode
            update.update_attribute(USERNAME, 
                                    PASSWORD, 
                                    credentials["AGV_details"][agv_id]["device_id"],
                                    THINGSBOARD_URL, 
                                    "status", 
                                    "Idle")
            update.update_attribute(USERNAME,
                                    PASSWORD,
                                    credentials["AGV_details"][current_operation["data"]["AGV"]]["device_id"],
                                    THINGSBOARD_URL,
                                    "targetModule",
                                    "Idle")
            
            uid = current_operation["data"].get("uniqueOpID")
            for product in order_data["productData"][0]["products"]:
                for _k, op in product.get("assembly", {}).items():
                    if op.get("data", {}).get("uniqueOpID") == uid:
                        op.setdefault("metrics", {})["finalTransport"] = "Done"
                        op["metrics"]["status"] = "End transport done"
                        break
            continue

        if status == "End transport done":
            completed_operations.append(current_operation)

    # Remove finished operations from the active list
    for op in completed_operations:
        if op in transport_operations:
            transport_operations.remove(op)

    # Prioritize operations that are still "Transporting" to the top of the list
    transport_operations.sort(key=lambda op: op["metrics"]["status"] != "Transporting")
    return transport_operations, completed_operations, order_data

def transport_operation_between_modules(transport_operations: list, 
                                        credentials: dict, 
                                        order: dict) -> tuple:
    """
    Starts all possible INTER-module transport operations with the list of transport operations provided.
    
    This function utilizes the list of transport operations which are active between modules. It checks the 
    status of each transport operation and manages their progression through various phases. It iterates through 
    all active transport operations and manages their actions based on module, AMR and operation status. If a transport
    is not yet started, it triggers it. If it is in progress, it checks where it currently is and initiates the next step
    or if there aren't any possible steps, it skips to the next operation. If the transport operation is finished, 
    it gives it a status of "Transport done" and removes it from the active list and adds it to the completed operations list.

    Args:
        transport_operations (list): List of active transport operations.
        credentials (dict): Credentials for ThingsBoard access.
        order (dict): Dictionary of operations and a header in an order.

    Returns:
        tuple[list, list, dict]
        - transport_operations (list): List of active transport operations after processing.
        - completed_operations (list): List of completed transport operations.
        - order_data (dict): Product data with updated transport operation statuses.
    """
    #PAZI KAJ DELAŠ Z ORDER DATA
    USERNAME = credentials["thingsboard_data"]["username"]
    PASSWORD = credentials["thingsboard_data"]["password"]
    VIRTUAL_DEVICE_ID = credentials["misc_details"]["virtual_device"]["device_id"]
    THINGSBOARD_URL = credentials["thingsboard_data"]["tb_url"]
    
    order_data = order
    
    print(f"Transport operations beggining of function: {transport_operations}")
    completed_operations = []
    print(f"Transport operations: {transport_operations}")
    for current_operation in transport_operations:
        start_pos = current_operation["data"].get("AGVstartPos", "null")
        end_pos = current_operation["data"].get("AGVendPos", "null")
        agv = current_operation["data"].get("AGV", "null")
        status = current_operation["metrics"]["status"]

        machine = current_operation["data"]["machineID"]
        print(f"Transport from {start_pos} to {end_pos}")
        print(f"Status modula {machine}: {status}")
        # Skip invalid states
        if agv == "null" or start_pos == "null" or end_pos == "null":
            continue
        
        if status == "Transport done":
            completed_operations.append(current_operation)
            continue
        
        agv_status = read.read_attribute(USERNAME, 
                                            PASSWORD, 
                                            credentials["AGV_details"][current_operation["data"]["AGV"]]["device_id"],
                                            THINGSBOARD_URL, 
                                            "status")
            
        conveyor_response = read.read_attribute(USERNAME,
                                                PASSWORD,
                                                credentials["module_details"][start_pos]["device_id"],
                                                THINGSBOARD_URL,
                                                "conveyorResponse")
        
        target_module = read.read_attribute(USERNAME, 
                                            PASSWORD, 
                                            credentials["AGV_details"][current_operation["data"]["AGV"]]["device_id"],
                                            THINGSBOARD_URL, 
                                            "targetModule")
        
        print(f"Stanje AGV: {agv_status}")
        print(f"Conveyor_response: {conveyor_response}")
        print(f"Target module: {target_module}")
        
        # Start transport if not started - THIS HAPPENS ONLY ONCE FOR ONE TRANSPORT OPERATION
        if status == "Waiting" and start_pos != "null" and end_pos != "null" and agv != "null":
            print(f"[AGV] Starting {agv} transport {start_pos} → {end_pos}")
            update.update_attribute(USERNAME,
                                    PASSWORD,
                                    credentials["module_details"][start_pos]["device_id"],
                                    THINGSBOARD_URL,
                                    "conveyorMessage",
                                    "Start")
            update.update_attribute(USERNAME,
                                    PASSWORD,
                                    credentials["AGV_details"][current_operation["data"]["AGV"]]["device_id"],
                                    THINGSBOARD_URL,
                                    "commandAGV",
                                    "Prepare")
            current_operation["metrics"]["status"] = "Waiting for transport" #TO SPREMENI V WAITING FOR TRANSPORT
            #
            logging.stamp_operation_metrics(current_operation["metrics"], new_status="Waiting for transport", transport_event="start")
            #
            for product in order_data["productData"][0]["products"]:
                for op_id, op_data in product["assembly"].items():
                    if op_data["data"]["uniqueOpID"] == current_operation["data"]["uniqueOpID"]:
                        product["assembly"][op_id] = current_operation
                        #print(order_data)
            continue  # Skip the rest of the loop iteration

        # Check if waiting for transport
        elif status == "Waiting for transport" and agv_status == "Waiting" : #and start_pos == target_module
            print("prižiganje traku nekaj s")
            update.update_attribute(USERNAME,
                                    PASSWORD,
                                    credentials["module_details"][start_pos]["device_id"],
                                    THINGSBOARD_URL,
                                    "conveyorMessage",
                                    "AGV ready")
            
            print("Pošiljam ukaz za transport na drugi modul")#tole smo dodali malo prej, zato da se trakova na modulu im amr-ju skupaj začneta
            update.update_attribute(USERNAME,
                                    PASSWORD,
                                    credentials["AGV_details"][current_operation["data"]["AGV"]]["device_id"],
                                    THINGSBOARD_URL,
                                    "commandAGV",
                                    "Go")
            time.sleep(0.5)
            #AMR to Idle if MANUAL mode
            update.update_attribute(USERNAME,
                                    PASSWORD,
                                    credentials["AGV_details"][current_operation["data"]["AGV"]]["device_id"],
                                    THINGSBOARD_URL,
                                    "status",
                                    "Idle")
            update.update_attribute(USERNAME,
                                    PASSWORD,
                                    credentials["AGV_details"][current_operation["data"]["AGV"]]["device_id"],
                                    THINGSBOARD_URL,
                                    "targetModule",
                                    "Idle")
            #
            
            print("Poslal kos na AGV")
            current_operation["metrics"]["status"] = "Transporting"
            for product in order_data["productData"][0]["products"]:
                for op_id, op_data in product["assembly"].items():
                    if op_data["data"]["uniqueOpID"] == current_operation["data"]["uniqueOpID"]:
                        product["assembly"][op_id] = current_operation
                        #print(order_data)
                        
            continue  # Skip the rest of the loop iteration
        #check if already transporting
        elif status == "Transporting":
            if conveyor_response == "Sent":
                
                #
                logging.mark_transport_go(current_operation["metrics"])
                #
                time.sleep(0.5)
                update.update_attribute(USERNAME,
                                        PASSWORD,
                                        credentials["module_details"][start_pos]["device_id"],
                                        THINGSBOARD_URL,
                                        "conveyorMessage",
                                        "Idle")
                update.update_attribute(USERNAME,
                                        PASSWORD,
                                        credentials["module_details"][start_pos]["device_id"],
                                        THINGSBOARD_URL,
                                        "conveyorResponse",
                                        "Idle")
                
                continue  # Skip the rest of the loop iteration

            if agv_status == "Delivered" : #and end_pos == target_module #UNCOMMENT target_module IF MULTIPLE AMR USED
                print("ko napišem delivered")
                update.update_attribute(USERNAME,
                                        PASSWORD,
                                        credentials["module_details"][start_pos]["device_id"],
                                        THINGSBOARD_URL,
                                        "conveyorResponse",
                                        "Idle")
                update.update_attribute(USERNAME,
                                        PASSWORD,
                                        credentials["module_details"][end_pos]["device_id"],
                                        THINGSBOARD_URL,
                                        "conveyorMessage",
                                        "Prepare for assembly")
                time.sleep(0.5)
                #AMR to Idle if MANUAL mode
                update.update_attribute(USERNAME,
                                        PASSWORD,
                                        credentials["AGV_details"][current_operation["data"]["AGV"]]["device_id"],
                                        THINGSBOARD_URL,
                                        "status",
                                        "Idle")
                update.update_attribute(USERNAME,
                                        PASSWORD,
                                        credentials["AGV_details"][current_operation["data"]["AGV"]]["device_id"],
                                        THINGSBOARD_URL,
                                        "targetModule",
                                        "Idle")
                print("Čakam da trak odpelje kos na montažno mesto")
                continue  # Skip the rest of the loop iteration

            if read.read_attribute(USERNAME,
                                    PASSWORD,
                                    credentials["module_details"][end_pos]["device_id"],
                                    THINGSBOARD_URL,
                                    "conveyorResponse") == "Prepared":
                print("zadnji if, da zaključimo funkcijo")
                update.update_attribute(USERNAME,
                                        PASSWORD,
                                        credentials["module_details"][end_pos]["device_id"],
                                        THINGSBOARD_URL,
                                        "conveyorResponse",
                                        "Idle")
                print(f"[AGV] {agv} completed transport {start_pos} → {end_pos}")
                current_operation["metrics"]["status"] = "Transport done" #TOLE MORA OSTAT TAKO!!!!
                #
                logging.stamp_operation_metrics(current_operation["metrics"], new_status="Transport done", transport_event="end")
                #             
                
                #updates to order data but NOT NECESSARY
                #for product in order_data["productData"][0]["products"]:
                    #for op_id, op_data in product["assembly"].items():
                        #if op_data["data"]["uniqueOpID"] == current_operation["data"]["uniqueOpID"]:
                            #product["assembly"][op_id] = current_operation
                            #print(order_data)
                            #break
            
                completed_operations.append(current_operation)
                continue  # Skip the rest of the loop iteration
            
        elif status in ("Finished", "Transport done"):
            completed_operations.append(current_operation)
            continue  # Skip the rest of the loop iteration

    # Remove completed transports from the active list
    for op in completed_operations:
        if op in transport_operations:
            transport_operations.remove(op)

    # Prioritize operations that are still "Transporting"
    transport_operations = sorted(
        transport_operations,
        key=lambda op: op["metrics"]["status"] != "Transporting"
    )
    return transport_operations, completed_operations, order_data

#this file contains transport functions
import FINAL_update_attribute as update
import FINAL_read_attribute as read
import logging_functions as logging
import time

def start_transport(transport_operations, credentials, order):
    """
    
    """
    USERNAME = credentials["thingsboard_data"]["username"]
    PASSWORD = credentials["thingsboard_data"]["password"]
    VIRTUAL_DEVICE_ID = credentials["misc_details"]["virtual_device"]["device_id"]
    THINGSBOARD_URL = credentials["thingsboard_data"]["tb_url"]
    
    order_data = order
    completed_operations = []
    
    for current_operation in transport_operations:
        start_pos = current_operation["data"].get("AGVstartPos", "null") #currently warehouse or manual loading pričakujemo null
        end_pos = current_operation["data"].get("AGVendPos", "null") 
        agv = current_operation["data"].get("AGV", "null")
        status = current_operation["metrics"]["status"]
        
        machine = current_operation["data"]["machineID"]
        print(f"Transport from {start_pos} to {end_pos}")
        print(f"Status modula {machine}: {status}")
        
        #RAZMISLI MALCE?
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
        
        #leave for possible adition of storage module
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
            #not necessary but prepared if we add a palet storage module
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
            if agv_status == "Delivered" and end_pos == target_module:
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
                logging.mark_initial_transport(current_operation["metrics"], "end") 
                #
                #for product in order_data["productData"][0]["products"]:
                    #for op_id, op_data in product["assembly"].items():
                        #if op_data["data"]["uniqueOpID"] == current_operation["data"]["uniqueOpID"]:
                            #product["assembly"][op_id] = current_operation
                            #print(order_data)
                            #break
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

def end_transport(transport_operations, credentials, order):
    """
    Končni transport: pickup izdelka z zadnjega modula (AGVstartPos = modul), brez ciljnega modula (AGVendPos = "null").
    Tok:
        Waiting  -> pošlji 'AGV Prepare' in 'Start' traku -> 'Waiting for transport'
        Waiting for transport & AGV Waiting -> sproži 'AGV ready' (trak) -> 'Transporting' (+žig start)
        Transporting:
            - ko AGV 'Delivered' -> ustavi trak, označi 'Transport done' (+žig end), AGV v 'Idle'
    """
    USERNAME = credentials["thingsboard_data"]["username"]
    PASSWORD = credentials["thingsboard_data"]["password"]
    THINGSBOARD_URL = credentials["thingsboard_data"]["tb_url"]
    

    order_data = order
    completed_operations = []

    for current_operation in list(transport_operations):
        start_pos = current_operation["data"].get("AGVstartPos", "null")
        end_pos   = current_operation["data"].get("AGVendPos", "null")   # pričakujemo "null"
        agv_id    = current_operation["data"].get("AGV", "AGV1")
        status    = current_operation["metrics"].get("status")
        if start_pos == "null" or agv_id == "null":
            continue  # neveljavno
        
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

        # 1) Waiting -> pripravi AMR in trak
        if status == "Finished":
            update.update_attribute(USERNAME, PASSWORD, credentials["module_details"][start_pos]["device_id"],
                                    THINGSBOARD_URL, "conveyorMessage", "Start")
            update.update_attribute(USERNAME, PASSWORD, credentials["AGV_details"][agv_id]["device_id"],
                                    THINGSBOARD_URL, "commandAGV", "Prepare")
            current_operation["metrics"]["status"] = "Waiting for transport"
            print(current_operation)
            # zapiši nazaj v DN (in TB)
            for product in order_data["productData"][0]["products"]:
                for op_id, op_data in product["assembly"].items():
                    if op_data["data"]["uniqueOpID"] == current_operation["data"]["uniqueOpID"]:
                        product["assembly"][op_id] = current_operation
            continue

        # 2) Waiting for transport + AMR je fizično pripravljen -> pošlji na AGV
        elif status == "Waiting for transport" and agv_status == "Waiting" and start_pos == target_module:
            update.update_attribute(USERNAME, PASSWORD, credentials["module_details"][start_pos]["device_id"],
                                    THINGSBOARD_URL, "conveyorMessage", "AGV ready")
            time.sleep(0.5)
            update.update_attribute(USERNAME, PASSWORD, credentials["AGV_details"][agv_id]["device_id"],
                                    THINGSBOARD_URL, "status", "Idle")
            # žig START (merimo tudi čakanje, če želiš, ga postavi že pri prehodu v Waiting for transport)
            #
            logging.stamp_operation_metrics(current_operation["metrics"], new_status="Transporting", transport_event="start")
            logging.mark_final_transport(current_operation["metrics"], "start")
            #
            
            update.update_attribute(USERNAME,
                                        PASSWORD,
                                        credentials["AGV_details"][current_operation["data"]["AGV"]]["device_id"],
                                        THINGSBOARD_URL,
                                        "targetModule",
                                        "Idle")
            
            current_operation["metrics"]["status"] = "Transporting"
            for product in order_data["productData"][0]["products"]:
                for op_id, op_data in product["assembly"].items():
                    if op_data["data"]["uniqueOpID"] == current_operation["data"]["uniqueOpID"]:
                        product["assembly"][op_id] = current_operation
            continue

        # 3) Transporting -> ko AMR javi Delivered, zaključimo (cilj ni modul)
        elif status == "Transporting":
            #if agv_status == "Delivered" and end_pos == target_module: #leave this for possibility of warehouse module
                # sprosti izhodni trak na start_pos
            update.update_attribute(USERNAME, PASSWORD, credentials["module_details"][start_pos]["device_id"],
                                    THINGSBOARD_URL, "conveyorResponse", "Idle")
            time.sleep(0.5)
            # končaj transport
            #
            logging.stamp_operation_metrics(current_operation["metrics"], new_status="End transport done", transport_event="end")
            logging.mark_final_transport(current_operation["metrics"], "end")
            #
            current_operation["metrics"]["status"] = "End transport done"
            # AMR pošlji v Idle (ali kamorkoli po potrebi)
            update.update_attribute(USERNAME, PASSWORD, credentials["AGV_details"][agv_id]["device_id"],
                                    THINGSBOARD_URL, "status", "Idle")
            
            uid = current_operation["data"].get("uniqueOpID")
            for product in order_data["productData"][0]["products"]:
                for _k, op in product.get("assembly", {}).items():
                    if op.get("data", {}).get("uniqueOpID") == uid:
                        # 1) Zakleni končni transport
                        op.setdefault("metrics", {})["finalTransport"] = "Done"
                        # 2) (po želji) zrcali status v DN – pomaga zaključnemu pogoju
                        op["metrics"]["status"] = "End transport done"
                        # 3) NE briši endFlag; naj ostane True do zaprtja DN
                        break
            continue

        # 4) Zaključen
        if status == "End transport done":
            completed_operations.append(current_operation)

    # odstrani končane iz aktivnega seznama
    for op in completed_operations:
        if op in transport_operations:
            transport_operations.remove(op)

    # prioritiziraj, da ostanejo transporti v teku na vrhu
    transport_operations.sort(key=lambda op: op["metrics"]["status"] != "Transporting")
    return transport_operations, completed_operations, order_data





def transport_operation_between_modules(transport_operations, credentials, order):
    """
    Iterates through all active transport operations.
    If a transport is not yet started, trigger it.
    If it's in progress, check if it's done.
    If finished, move on to the next operation.
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
        # Skip invalid ones
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
        elif status == "Waiting for transport" and agv_status == "Waiting" and start_pos == target_module:
            print("prižiganje traku nekaj s")
            update.update_attribute(USERNAME,
                                    PASSWORD,
                                    credentials["module_details"][start_pos]["device_id"],
                                    THINGSBOARD_URL,
                                    "conveyorMessage",
                                    "AGV ready")
            time.sleep(0.5)
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
                print("Pošiljam ukaz za transport na drugi modul")
                update.update_attribute(USERNAME,
                                        PASSWORD,
                                        credentials["AGV_details"][current_operation["data"]["AGV"]]["device_id"],
                                        THINGSBOARD_URL,
                                        "commandAGV",
                                        "Go")
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

            if agv_status == "Delivered" and end_pos == target_module:
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



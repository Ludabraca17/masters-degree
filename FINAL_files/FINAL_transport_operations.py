#this file contains transport functions
import FINAL_update_attribute as update
import FINAL_read_attribute as read
import time

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

        kumara = current_operation["data"]["machineID"]
        print(f"Transport from {start_pos} to {end_pos}")
        print(f"Status modula {kumara}: {status}")
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
        print(f"Stanje AGV: {agv_status}")
        print(f"Conveyor_response: {conveyor_response}")
        
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
            for product in order_data["productData"][0]["products"]:
                for op_id, op_data in product["assembly"].items():
                    if op_data["data"]["uniqueOpID"] == current_operation["data"]["uniqueOpID"]:
                        product["assembly"][op_id] = current_operation
                        #print(order_data)
            continue  # Skip the rest of the loop iteration

        # Check if waiting for transport
        elif status == "Waiting for transport" and agv_status == "Waiting":
            print("prižiganje traku 10s")
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

            if agv_status == "Delivered":
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
                
                
                for product in order_data["productData"][0]["products"]:
                    for op_id, op_data in product["assembly"].items():
                        if op_data["data"]["uniqueOpID"] == current_operation["data"]["uniqueOpID"]:
                            product["assembly"][op_id] = current_operation
                            #print(order_data)
                            break
            
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



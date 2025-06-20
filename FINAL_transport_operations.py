#this file contains transport functions
import FINAL_update_attribute as update
import FINAL_read_attribute as read

#start transport
def start_transport_operation(current_operation, previous_operation, operation_count, credentials):
    """
    
    """
    return

#mid assembly transport
def main_transport_operation(current_operation, previous_operation, operation_count, credentials):
    """
    This function represents the logic of a transport operation. It updates the attributes of the conveyor and AGV devices to start the transport.
    In this phase it is hardcoded for module1 and module2, but the upgrade will include the dynamic selection of the modules. Current two input variables
    (current_operation and operation_count) are trivial since they are both global variables. In the future we will add variables for whichever module is
    selected for transport by the digital twin. TO POSODOBI!!!!!
    """
    
    #static credentials - they are always the same for all modules
    USERNAME = credentials["thingsboard_data"]["username"]
    PASSWORD = credentials["thingsboard_data"]["password"]
    VIRTUAL_DEVICE_ID = credentials["misc_details"]["virtual_device"]["device_id"]
    THINGSBOARD_URL = credentials["thingsboard_data"]["tb_url"]

    #credentials["module_details"][previous_operation["data"]["machineID"]]["device_id"]

    print("ZAČETEK TRANSPORTA")
    #priprava za oddajanje kosa AGVju
    print(credentials["AGV_details"][current_operation["data"]["AGV"]])
    try:
        update.update_attribute(USERNAME, PASSWORD, credentials["module_details"][previous_operation["data"]["machineID"]]["device_id"], THINGSBOARD_URL, "conveyorMessage", "Start")
        update.update_attribute(USERNAME, PASSWORD, credentials["AGV_details"][current_operation["data"]["AGV"]], THINGSBOARD_URL, "commandAGV", "Prepare")
    except Exception as e:
        print(f"An error occurred: {e}")
    transport_condition = True
    updated = False #internal logic variable for next while loop
    print("before loop")
    try:
        while transport_condition:
            condition = None
            condition = read.read_attribute(USERNAME, PASSWORD, credentials["module_details"][previous_operation["data"]["machineID"]]["device_id"], THINGSBOARD_URL, "conveyorResponse")
            print("Glavna zanka za transport")
            try:
                while condition == "Waiting":
                    print("loopčič")
                    if read.read_attribute(USERNAME, PASSWORD, credentials["AGV_details"][current_operation["data"]["AGV"]]["device_id"], THINGSBOARD_URL, "status") == "Waiting" and updated == False:
                        print("prižiganje traku 10s")
                        update.update_attribute(USERNAME, PASSWORD, credentials["module_details"][previous_operation["data"]["machineID"]]["device_id"], THINGSBOARD_URL, "conveyorMessage", "AGV ready")
                        updated = True
                        print("Poslal kos na AGV")
                    if read.read_attribute(USERNAME, PASSWORD, credentials["module_details"][previous_operation["data"]["machineID"]]["device_id"], THINGSBOARD_URL, "conveyorResponse") == "Sent":
                        updated = False
                        print("Pošiljam ukaz za transport na drugi modul")
                        update.update_attribute(USERNAME, PASSWORD, credentials["AGV_details"][current_operation["data"]["AGV"]]["device_id"], THINGSBOARD_URL, "commandAGV", "Go")
                        #update_attribute(USERNAME, PASSWORD, NODE_RED_1_DEVICE_ID, THINGSBOARD_URL, "conveyorResponse", "Idle")
                        break

            except KeyboardInterrupt:
                pass

            if read.read_attribute(USERNAME, PASSWORD, credentials["module_details"][previous_operation["data"]["machineID"]]["device_id"], THINGSBOARD_URL, "conveyorResponse") == "Sent" and read.read_attribute(USERNAME, PASSWORD, credentials["AGV_details"][current_operation["data"]["AGV"]]["device_id"], THINGSBOARD_URL, "status") == "Delivered":
                print("ko napišem delivered")
                #read_attribute(USERNAME, PASSWORD, AGV_ID, THINGSBOARD_URL, "status") == "Finished"
                update.update_attribute(USERNAME, PASSWORD, credentials["module_details"][previous_operation["data"]["machineID"]]["device_id"], THINGSBOARD_URL, "conveyorResponse", "Idle")
                update.update_attribute(USERNAME, PASSWORD, credentials["module_details"][current_operation["data"]["machineID"]]["device_id"], THINGSBOARD_URL, "conveyorMessage", "Prepare for assembly")
                update.update_attribute(USERNAME, PASSWORD, credentials["AGV_details"][current_operation["data"]["AGV"]]["device_id"], THINGSBOARD_URL, "status", "Idle") #to bo verjetno treba dat stran - to določi agv sam???

                print("Čakam da trak odpelje kos na montažno mesto")
                try:
                    while True:
                        if read.read_attribute(USERNAME, PASSWORD, credentials["module_details"][current_operation["data"]["machineID"]]["device_id"], THINGSBOARD_URL, "conveyorResponse") == "Prepared":
                            update.update_attribute(USERNAME, PASSWORD, credentials["module_details"][current_operation["data"]["machineID"]]["device_id"], THINGSBOARD_URL, "currentOperation", current_operation)
                            operation_count += 1
                            print("Operation count: ", operation_count)
                            print("Current subpart: ", current_operation["data"]["part"])
                            break
                        
                except KeyboardInterrupt:
                    pass

            if read.read_attribute(USERNAME, PASSWORD, credentials["module_details"][current_operation["data"]["machineID"]]["device_id"], THINGSBOARD_URL, "conveyorResponse") == "Prepared":
                print("zadnji if, da zaključimo funkcijo")
                update.update_attribute(USERNAME, PASSWORD, credentials["module_details"][current_operation["data"]["machineID"]]["device_id"], THINGSBOARD_URL, "conveyorResponse", "Idle")
                transport_condition = False
                print(f"Transport condition {transport_condition}")

    except KeyboardInterrupt:
        pass

    return operation_count

#end transport
def end_transport_operation(current_operation, operation_count, credentials):
    """
    
    """
    USERNAME = credentials["thingsboard_data"]["username"]
    PASSWORD = credentials["thingsboard_data"]["password"]
    VIRTUAL_DEVICE_ID = credentials["misc_details"]["virtual_device"]["device_id"]
    THINGSBOARD_URL = credentials["thingsboard_data"]["tb_url"]

    print("Transport after assembly function")
    #tole spodaj je en velik vprašaj... mogoče ne bi bilo slabo razviti standardne operacije (transport sestava itn in jih potem klicati v if stavkih)        
    update.update_attribute(USERNAME, PASSWORD, credentials["module_details"][current_operation["data"]["machineID"]]["device_id"], THINGSBOARD_URL, "currentOperation", current_operation)
    
    print("Operation count: ", operation_count)
    print("Current subpart: ", current_operation["data"]["part"])
            
    print("Start transport after assembly")
    #transporting after finished assembly
    #update_attribute(USERNAME, PASSWORD, NODE_RED_2_DEVICE_ID, THINGSBOARD_URL, "currentOperation", current_operation)
    #operation_count += 1
    try:
        while True:
            print("zadnja transportna zanka")
            if read.read_attribute(USERNAME, PASSWORD, credentials["module_details"][current_operation["data"]["machineID"]]["device_id"], THINGSBOARD_URL, "currentOperation")["metrics"]["status"] == "Finished":
                update.update_attribute(USERNAME, PASSWORD, credentials["module_details"][current_operation["data"]["machineID"]]["device_id"], THINGSBOARD_URL, "conveyorMessage", "Start")
                #pošlji nek ukaz za agv da lahko gre odložit na končno pozicijo
                if read.read_attribute(USERNAME, PASSWORD, credentials["module_details"][current_operation["data"]["machineID"]]["device_id"], THINGSBOARD_URL, "conveyorMessage") == "Waiting":
                    update.update_attribute(USERNAME, PASSWORD, credentials["module_details"][current_operation["data"]["machineID"]]["device_id"], THINGSBOARD_URL, "conveyorMessage", "Idle")
                    #pošli signal na agv da odpelje izdelek na končno pozicijo
                    #dodaj še 10 s transport al koliko je že
                    break
    except KeyboardInterrupt:
        pass 
    
    return 
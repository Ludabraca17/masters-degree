#this file contains functions for assembly operations
import FINAL_update_attribute as update
#import FINAL_data_manipulation as manipulation

def basic_assembly_operation(current_operation_group, operation_count, credentials):
    """
    Hue hue hue.
    """

    #static credentials - they are always the same for all modules
    USERNAME = credentials["thingsboard_data"]["username"]
    PASSWORD = credentials["thingsboard_data"]["password"]
    VIRTUAL_DEVICE_ID = credentials["misc_details"]["virtual_device"]["device_id"]
    THINGSBOARD_URL = credentials["thingsboard_data"]["tb_url"]   

    try:
        print("Znotraj funkcije")
        print(current_operation_group)
        #print(credentials["module_details"][i["data"]["machineID"]]["device_id"])
        #dobimo poljubno operacijo
        print(credentials["module_details"][current_operation_group["data"]["machineID"]])
        update.update_attribute(USERNAME, PASSWORD, credentials["module_details"][current_operation_group["data"]["machineID"]]["device_id"], THINGSBOARD_URL, "currentOperation", current_operation_group)

        
        print("Operation count: ", operation_count)
        print("Current subpart: ", current_operation_group["data"]["part"])
    except Exception as e:
        print(f"An error occurred: {e}")

    return 

def multiple_assembly_operation(current_operation_group, operation_count, credentials):
    """
    Hue hue hue.
    """

    #static credentials - they are always the same for all modules
    USERNAME = credentials["thingsboard_data"]["username"]
    PASSWORD = credentials["thingsboard_data"]["password"]
    VIRTUAL_DEVICE_ID = credentials["misc_details"]["virtual_device"]["device_id"]
    THINGSBOARD_URL = credentials["thingsboard_data"]["tb_url"]
    try:
        print("Znotraj funkcije")
        print(current_operation_group)
        #print(credentials["module_details"][i["data"]["machineID"]]["device_id"])
        #dobimo poljubno operacijo

        print(credentials["module_details"][current_operation_group["data"]["machineID"]])
        update.update_attribute(USERNAME, PASSWORD, credentials["module_details"][current_operation_group["data"]["machineID"]]["device_id"], THINGSBOARD_URL, "currentOperation", current_operation_group)

        print("Operation count: ", operation_count)
        print("Current subpart: ", current_operation_group["data"]["part"])
    except Exception as e:
        print(f"An error occurred: {e}")

    return operation_count
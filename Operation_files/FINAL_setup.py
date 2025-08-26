#file for setup
import FINAL_read_attribute as read
import FINAL_update_attribute as update
import json


def setup():
    """
    Function that completes the setup of the system before the start.

    There is a possibility of an error in case some of the modules that are present in credentials file are not online.
    """

    with open('FINAL_credentials.json', 'r') as cred:
        credentials = json.load(cred)["credentials"]

    module_keys = credentials["module_details"].keys()
    agv_keys = credentials["AGV_details"].keys()

    USERNAME = credentials["thingsboard_data"]["username"]
    PASSWORD = credentials["thingsboard_data"]["password"]
    VIRTUAL_DEVICE_ID = credentials["misc_details"]["virtual_device"]["device_id"]
    THINGSBOARD_URL = credentials["thingsboard_data"]["tb_url"]

    for i in module_keys:
        last_op = read.read_attribute(USERNAME, PASSWORD, credentials["module_details"][i]["device_id"], THINGSBOARD_URL, "currentOperation")
        setup_op = last_op
        setup_op["metrics"]["status"] = "Setup"

        update.update_attribute(USERNAME, PASSWORD, credentials["module_details"][i]["device_id"], THINGSBOARD_URL, "currentOperation", setup_op)
        update.update_attribute(USERNAME, PASSWORD, credentials["module_details"][i]["device_id"], THINGSBOARD_URL, "conveyorMessage", "Idle")
        update.update_attribute(USERNAME, PASSWORD, credentials["module_details"][i]["device_id"], THINGSBOARD_URL, "conveyorResponse", "Idle")

    for i in agv_keys:
        #dodaj spremembo statusa tako da bo status == Finished
        update.update_attribute(USERNAME, PASSWORD, credentials["AGV_details"][i]["device_id"], THINGSBOARD_URL, "commandAGV", "Idle")
        update.update_attribute(USERNAME, PASSWORD, credentials["AGV_details"][i]["device_id"], THINGSBOARD_URL, "status", "Idle")

    return 
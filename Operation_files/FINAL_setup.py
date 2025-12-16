#file for setup
import FINAL_read_attribute as read
import FINAL_update_attribute as update

def setup(credentials: dict) -> None:
    """
    Function that completes the setup of the system before the start.

    There is a possibility of an error in case some of the modules that are present in credentials file are not online.
    """

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

    for i in agv_keys: #Should i set this and override ROS?
        update.update_attribute(USERNAME, PASSWORD, credentials["AGV_details"][i]["device_id"], THINGSBOARD_URL, "commandAGV", "Idle")
        update.update_attribute(USERNAME, PASSWORD, credentials["AGV_details"][i]["device_id"], THINGSBOARD_URL, "status", "Idle")

    return 
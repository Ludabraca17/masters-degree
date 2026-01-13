# file for setup
import copy
import read_attribute as read
import update_attribute as update


def setup(credentials: dict) -> None:
    """
    Function that completes the setup of the system before the start.

    It reads the currentOperation from each module and
    re-sends the entire operation as an attribute without modification.
    """

    module_keys = credentials["module_details"].keys()
    agv_keys = credentials["AGV_details"].keys()

    USERNAME = credentials["thingsboard_data"]["username"]
    PASSWORD = credentials["thingsboard_data"]["password"]
    THINGSBOARD_URL = credentials["thingsboard_data"]["tb_url"]

    # ---------- MODULES ----------
    for key in module_keys:
        device_id = credentials["module_details"][key]["device_id"]

        # Read full current operation
        current_op = read.read_attribute(
            USERNAME,
            PASSWORD,
            device_id,
            THINGSBOARD_URL,
            "currentOperation"
        )

        if current_op is None:
            continue  # or log warning

        # Defensive copy (good practice)
        operation_payload = copy.deepcopy(current_op)

        # Send entire operation as attribute
        update.update_attribute(
            USERNAME,
            PASSWORD,
            device_id,
            THINGSBOARD_URL,
            "currentOperation",
            operation_payload
        )

        # Reset conveyor states
        update.update_attribute(
            USERNAME,
            PASSWORD,
            device_id,
            THINGSBOARD_URL,
            "conveyorMessage",
            "Idle"
        )
        update.update_attribute(
            USERNAME,
            PASSWORD,
            device_id,
            THINGSBOARD_URL,
            "conveyorResponse",
            "Idle"
        )

    # ---------- AGVs ----------
    for key in agv_keys:
        device_id = credentials["AGV_details"][key]["device_id"]

        update.update_attribute(
            USERNAME,
            PASSWORD,
            device_id,
            THINGSBOARD_URL,
            "commandAGV",
            "Idle"
        )
        update.update_attribute(
            USERNAME,
            PASSWORD,
            device_id,
            THINGSBOARD_URL,
            "status",
            "Idle"
        )

    return

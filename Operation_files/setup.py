# file for setup
import copy
import read_attribute as read
import update_attribute as update
import json



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

        #if current_op is None:
        current_op = {
                        "data": {
                            "machineID": None,
                            "uniqueOpID": None,
                            "assemblyParent": None,
                            "part": None,
                            "color": None,
                            "queuePosition": None,
                            "scheduledOpStart": None,
                            "scheduledOpEnd": None,
                            "AGVstartPos": None,
                            "AGVendPos": None,
                            "AGV": None
                        },
                        "metrics": {
                            "status": "Setup",
                            "realOpStart": 1768309648600,
                            "realOpEnd": 1768309648650,
                            "startTs": None
                        }
                    }
            
        update.update_attribute(
            USERNAME,
            PASSWORD,
            device_id,
            THINGSBOARD_URL,
            "currentOperation",
            current_op
                )
            #continue  # or log warning
        #else:
            # Defensive copy (good practice)
            #operation_payload = copy.deepcopy(current_op)

            # Send entire operation as attribute
            #update.update_attribute(
                #USERNAME,
                #PASSWORD,
                #device_id,
                #THINGSBOARD_URL,
                #"currentOperation",
                #operation_payload
            #)

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

import FINAL_update_attribute as update
import FINAL_read_attribute as read
import copy
import traceback

def sort_operations_by_queue_position(order):
    """
    This function takes the entire order and extracts the operations from it.
    The operations are sorted primarily by "queuePosition". If two operations have the same queuePosition,
    they are further sorted by "uniqueOpID" to ensure a consistent order.
    The function returns a flat list of operations.

    Args:
        order (_type_): Dictionary of operations and a header in an order.

    Returns:
        _type_: List of operations sorted by queuePosition and uniqueOpID.
    """
    new_operations = []
    try:
        several_orders = order["productData"][0]["products"]

        # Extract operations from the order data
        for order in several_orders:
            for operation_key in order["assembly"]:
                new_operations.append(order["assembly"][operation_key])

        # Sort operations by queuePosition, then by uniqueOpID
        sorted_operations = sorted(
            new_operations,
            key=lambda x: (x["data"]["queuePosition"], x["data"]["uniqueOpID"])
        )

    except KeyError:
        pass

    return sorted_operations

def update_order_data(order, credentials):
    """
    Reads the current operation which is finished or processing and updates the order_data.
    If the order changes, updates the TB attribute 'productionOrder'.

    Args:
        order (_type_): Dictionary of operations and a header in an order.
        credentials (_type_): JSON file with credentials and other details of production and AMR modules.
    """
    USERNAME = credentials["thingsboard_data"]["username"]
    PASSWORD = credentials["thingsboard_data"]["password"]
    VIRTUAL_DEVICE_ID = credentials["misc_details"]["virtual_device"]["device_id"]
    THINGSBOARD_URL = credentials["thingsboard_data"]["tb_url"]
    module_keys = credentials["module_details"].keys()

    # Make separate deep copies
    original_order_data = copy.deepcopy(order)
    order_data = copy.deepcopy(order)

    for i in module_keys:
        current_op_status = read.read_attribute(USERNAME, 
                                                PASSWORD,
                                                credentials["module_details"][i]["device_id"],
                                                THINGSBOARD_URL,
                                                "currentOperation")["metrics"]["status"]
        
        print(f"Current operation status for {i}: {current_op_status}")

        # ✅ Correct way to check multiple statuses
        if current_op_status in ("Finished", "Processing", "Transporting", "Transport done"):
            current_op = read.read_attribute(
                USERNAME, PASSWORD,
                credentials["module_details"][i]["device_id"],
                THINGSBOARD_URL,
                "currentOperation"
            )
            op_ident = current_op["data"]["uniqueOpID"]
            print(f"Updating active module {i} operation ID: {op_ident}")

            for product in order_data["productData"][0]["products"]:
                for op_id, op_data in product["assembly"].items():
                    if op_data["data"]["uniqueOpID"] == op_ident:
                        product["assembly"][op_id] = current_op
                        break


    # ✅ Send updated productionOrder to TB
    update.update_attribute(USERNAME, PASSWORD, VIRTUAL_DEVICE_ID,THINGSBOARD_URL, "productionOrder", order_data)
    print("Order data has been pushed to ThingsBoard.")

    


def get_next_operations(credentials, order, sorted_operations):
    """Determine which operations can be executed next based on their status, 
    dependencies, and module availability.

    This function groups operations by module, checks whether modules are 
    currently blocked (e.g., due to processing, waiting for transport, or 
    transport in progress), and then selects the next eligible operation 
    for each module. It first prioritizes transport operations and blocks 
    modules involved in those, and then schedules normal operations if 
    their dependencies are satisfied and the module is not blocked.

    Args:
        credentials (dict): JSON-like dictionary containing module details 
            (e.g., production and AMR modules).
        order (dict): Dictionary describing the order, including product 
            data and associated operations.
        sorted_operations (list): List of all operations sorted by their 
            queue position, used for dependency checks.

    Returns:
        list: A list of operation dictionaries representing the next 
        operations that can be executed.
    """
    try:
        modules = credentials["module_details"]
        operations_by_module = {module: [] for module in modules}
        next_operations = []

        # For normal operations, block only if Processing or Waiting for transport
        blocking_statuses_normal = {"Processing", "Waiting for transport"}
        # For transport scheduling, include Transporting as well
        blocking_statuses_transport = {"Processing", "Waiting for transport", "Transporting"}

        blocked_modules = set()  # ✅ FIX: Initialize here

        products = order["productData"][0]["products"]

        # Bucket ops by machineID
        for product in products:
            for _, op_data in product["assembly"].items():
                machine_id = op_data["data"].get("machineID")
                if machine_id in operations_by_module:
                    operations_by_module[machine_id].append(op_data)

        # --- Pre-block modules involved in transport ops that are Waiting for transport ---
        for module, operations in operations_by_module.items():
            for op_data in operations:
                status = op_data["metrics"].get("status")
                if status == "Waiting for transport":  # Only block while waiting
                    start_pos = op_data["data"].get("AGVstartPos")
                    end_pos = op_data["data"].get("AGVendPos")
                    if start_pos != "null" and end_pos != "null":
                        blocked_modules.add(start_pos)
                        blocked_modules.add(end_pos)

        # --- First pass: schedule transport operations ---
        for module, operations in operations_by_module.items():
            if any(op["metrics"].get("status") in blocking_statuses_transport for op in operations):
                continue

            sorted_ops = sorted(operations, key=lambda x: x["data"].get("queuePosition", float("inf")))

            for op_data in sorted_ops:
                status = op_data["metrics"].get("status")
                if status not in ("Waiting", "Transport done"):
                    continue

                # Dependency check
                current_q = op_data["data"].get("queuePosition", float("inf"))
                current_parent = op_data["data"].get("assemblyParent")
                if any(
                    op["data"].get("assemblyParent") == current_parent
                    and op["data"].get("queuePosition", float("inf")) < current_q
                    and op["metrics"].get("status") != "Finished"
                    for op in sorted_operations
                ):
                    continue

                # Transport check
                start_pos = op_data["data"].get("AGVstartPos")
                end_pos = op_data["data"].get("AGVendPos")
                if start_pos != "null" and end_pos != "null":
                    next_operations.append(op_data)
                    # Block both modules for this cycle
                    blocked_modules.add(start_pos)
                    blocked_modules.add(end_pos)

                break  # only one op per module

        # --- Second pass: schedule normal operations ---
        for module, operations in operations_by_module.items():
            if module in blocked_modules:
                continue

            if any(op["metrics"].get("status") in blocking_statuses_normal for op in operations):
                continue

            sorted_ops = sorted(operations, key=lambda x: x["data"].get("queuePosition", float("inf")))

            for op_data in sorted_ops:
                status = op_data["metrics"].get("status")
                if status not in ("Waiting", "Transport done"):
                    continue

                # Dependency check
                current_q = op_data["data"].get("queuePosition", float("inf"))
                current_parent = op_data["data"].get("assemblyParent")
                if any(
                    op["data"].get("assemblyParent") == current_parent
                    and op["data"].get("queuePosition", float("inf")) < current_q
                    and op["metrics"].get("status") != "Finished"
                    for op in sorted_operations
                ):
                    continue

                next_operations.append(op_data)
                break  # only one op per module

        return next_operations

    except Exception as e:
        print(f"[ERROR] Exception in get_next_operations: {e}")
        import traceback
        traceback.print_exc()













    
import update_attribute as update
import read_attribute as read
from logging_functions import normalize_op_times_from_real, ensure_quality_default, now_ms, _ms_to_iso_utc, _belongs_to_this_order_strict, mark_order_start, _coerce_ts_ms
import copy
import traceback
from typing import Dict, Any, Tuple, List

def sort_operations_by_queue_position(order: dict) -> list:
    """
    This function takes the entire order and extracts the operations from it.
    The operations are sorted primarily by "queuePosition". If two operations have the same "queuePosition",
    they are further sorted by "uniqueOpID" to ensure a consistent order.
    The function returns a flat list of operations.

    Args:
        order (dict): Dictionary of operations and a header in an order.

    Returns:
        list: List of operations sorted by queuePosition and uniqueOpID.
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

def update_order_data(
        order: dict, 
        credentials: dict
        ) -> dict:
    """
    Reads the current operation for each possible module and finds if there was any change for operations that are in the order.
    If the order changes, it updates the TB attribute "productionOrder" with the updated order. Updated order is then returned.

    Args:
        order (dict): Entire production order which is to be updated to ThingsBoard.
        credentials (dict): Credentials for ThingsBoard access.

    Returns:
        dict: Updated order so that the data is synced with ThingsBoard.
    """
    import copy
    import read_attribute as read
    import update_attribute as update
    # dodatki iz logging_functions – idempotentno polnijo čase in ISO ogledala
    from logging_functions import normalize_op_times_from_real, _ms_to_iso_utc, ensure_quality_default

    USERNAME = credentials["thingsboard_data"]["username"]
    PASSWORD = credentials["thingsboard_data"]["password"]
    VIRTUAL_DEVICE_ID = credentials["misc_details"]["virtual_device"]["device_id"]
    THINGSBOARD_URL = credentials["thingsboard_data"]["tb_url"]
    module_keys = credentials["module_details"].keys()

    # Make separate deep copies
    #original_order_data = copy.deepcopy(order)
    order_data = copy.deepcopy(order)
    
    if not order:   # None ali {}
        return order  # nič ne delaj
    
    mark_order_start(order_data)
    
    pd0 = order_data.get("productData",[{}])[0]
    order_start_ts = _coerce_ts_ms(pd0.get("orderStartTs"))
    expected_pid = pd0.get("productId") #TO SPREMENI TAKO, DA BO ZNOTRAJ VSAKE OPERACIJE ISTI KOT JE V HEADERJU VENDAR VSAK DN IMA SVOJEGA
    #
    if not isinstance(order_start_ts, (int, float)):
        print(f"[WARN] order_start_ts is not numeric: {order_start_ts} (type={type(order_start_ts).__name__})")
    #
    for i in module_keys:
        current = read.read_attribute(
            USERNAME,
            PASSWORD,
            credentials["module_details"][i]["device_id"],
            THINGSBOARD_URL,
            "currentOperation"
        )
        current_op_status = current.get("metrics", {}).get("status")
        print(f"Current operation status for {i}: {current_op_status}")

        # podpiraj tudi "Waiting for transport"
        if current_op_status in ("Finished", "Processing", "Transporting", "Transport done", "Waiting for transport"):
            current_op = current  # že prebrano zgoraj
            op_ident = current_op["data"]["uniqueOpID"]
            if not _has_real_iso(current_op.get("metrics", {})):
                print(f"[SKIP] Finished op {op_ident} on module {i} lacks real ISO timestamps; treating as stale.")
                break
            else:
                incoming_uid = current.get("data", {}).get("orderUID") or current.get("data", {}).get("orderId")
                print(f"Updating active module {i} operation ID: {op_ident} | incoming orderUID={incoming_uid} expected={expected_pid}")
                
                # --- 1) primary guard: exact order ID match if present ---
                if expected_pid and incoming_uid and incoming_uid != expected_pid:
                    print(f"[SKIP] Module {i} op {op_ident} belongs to {incoming_uid}, not this order {expected_pid}.")
                    continue

                # --- 2) fallback guard: strict ISO-based staleness check (NO normalization yet) ---
                if isinstance(order_start_ts, (int, float)) and not _belongs_to_this_order_strict(current, order_start_ts):
                    print(f"[SKIP] Module {i} op {op_ident} appears stale by ISO timestamps.")
                    continue
                
                # --- NADGRADNJE (idempotentno, brez ‘merge’) ---
                # 1) iz NR ISO -> *Ts (ms), če manjkajo
                if "metrics" in current_op:
                    normalize_op_times_from_real(current_op["metrics"])  # ne prepiše obstoječih ms žigov
                    # 2) ISO ogledala za Pythonove ms žige (berljivo v končnem DN)
                    ms_start = current_op["metrics"].get("startTs")
                    ms_end   = current_op["metrics"].get("endTs")
                    if ms_start is not None:
                        iso = _ms_to_iso_utc(ms_start)
                        if iso is not None:
                            current_op["metrics"].setdefault("startTsIso", iso)
                    if ms_end is not None:
                        iso = _ms_to_iso_utc(ms_end)
                        if iso is not None:
                            current_op["metrics"].setdefault("endTsIso", iso)
                    # 3) kakovost ob Finished, če manjka
                    if current_op_status == "Finished":
                        ensure_quality_default(current_op["metrics"], default="OK")
                # --- konec nadgradenj ---

                op_ident = current_op["data"]["uniqueOpID"]
                print(f"Updating active module {i} operation ID: {op_ident}")

                for product in order_data["productData"][0]["products"]:
                    for op_id, op_data in product["assembly"].items():
                        
                        if op_data["data"]["uniqueOpID"] == op_ident:
                            if not _belongs_to_this_order_strict(current_op, order_start_ts): #PAZI NA TO!!!! mogoče zbriši
                                print(f"[SKIP] Stale op {op_ident} on module {i} (from previous order).")
                                break
                            existing = product["assembly"][op_id]
                            end_lock = existing.get("metrics", {}).get("finalTransport")
                            is_end_active = (
                                existing.get("data", {}).get("AGVendPos") == "null" and
                                existing.get("metrics", {}).get("status") in ("Waiting","Waiting for transport","Transporting")
                            )

                            # NE prepisuj, če teče end transport, ali če je že označen kot Done
                            if is_end_active or end_lock in ("InProgress", "Done"):
                                print(f"[SKIP] preserve final-transport for uid={op_ident} ({end_lock})")
                            else:
                                product["assembly"][op_id] = current_op
                            break

    # Pošlji posodobljen productionOrder v TB
    update.update_attribute(USERNAME, PASSWORD, VIRTUAL_DEVICE_ID, THINGSBOARD_URL, "productionOrder", order_data)
    print("Order data has been pushed to ThingsBoard.")
    return order_data

def tag_final_ops_with_endflag(
        order: Dict[str, Any]
        ) -> Dict[str, Any]:
    """
    Takes the order and finds final operations for each product. It then adds an "endFlag": "True" to the data of the final operation.
    That is later used to indicate end transport operations.
    
    Args:
        order (dict): Production order containing products and their operations.

    Returns:
        dict: Production order with final operations tagged with "endFlag": "True".
    """
    try:
        pd0 = order.get("productData", [{}])[0]
        for product in pd0.get("products", []):
            assembly = product.get("assembly", {})
            max_key, max_uid = None, None
            for op_key, op in assembly.items():
                try:
                    u = int(str(op.get("data", {}).get("uniqueOpID")))
                except Exception:
                    continue
                if (max_uid is None) or (u > max_uid):
                    max_uid = u; max_key = op_key
            if max_key is not None:
                d = assembly[max_key].setdefault("data", {})
                # nastavi samo, če še NI definirano
                if "endFlag" not in d:
                    d["endFlag"] = "True"
    except Exception as e:
        print(f"[WARN] tag_final_ops_with_endflag failed: {e}")
    return order

def build_final_transport_task(
        op: dict, 
        default_agv: str = "AGV1"
        ) -> dict:
    """
    Builds a final transport task from an "end" operation (where endFlag=True).

    The task is formed as follows:
    - AGVstartPos = operation"s machineID
    - AGVendPos   = "null" (represents "out of factory", not yet implemented)
    - AGV         = default_agv, unless op.data contains a specific AGV
    - metrics.status = "Finished" (signals an end-transport task)

    Args:
        op (dict): Operation marked as final (with endFlag=True).
        default_agv (str, optional): Default AGV to use if the operation does not provide one.

    Returns:
        dict: A transport task containing updated "data" and "metrics".
    """
    d = dict(op.get("data", {}))
    m = dict(op.get("metrics", {}))
    agv = d.get("AGV") or default_agv
    task = {
        "data": {
            **d,
            "AGV": agv,
            "AGVstartPos": d.get("machineID", "null"),
            "AGVendPos": "null",
        },
        "metrics": {
            **m,
            "status": "Finished"  # vstop v end_transport
        }
    }
    return task

def is_order_completed_with_final_transport(order: dict) -> bool:
    """
    Checks if the entire production order is completed, including final transport.
    
    Production order is considered completed if:
    - for all normal operations (without endFlag), metrics.status == "Finished",
    - for the operation with endFlag == True, metrics.status == "Transport done".
    
    Production order is NOT considered completed if operations with endFlag == True have status Finished.

    Args:
        order (dict): Current production order.

    Returns:
        bool: True if the order is completed with final transport, False otherwise.
    """
    try:
        products = order.get("productData", [{}])[0].get("products", [])
    except Exception:
        return False

    for p in products:
        for _k, op in p.get("assembly", {}).items():
            d = op.get("data", {})
            m = op.get("metrics", {})
            status = m.get("status", "")

            if d.get("endFlag") == "True":
                # za finalno operacijo je "Transport done" edino stanje, ki šteje kot dokončano
                if status != "End transport done":
                    return False
            else:
                # za ostale operacije zahtevamo "Finished"
                if status != "Finished":
                    return False
    return True

def _get_products(order: dict) -> List[Dict[str, Any]]:
    """Returns the list of products from the order dictionary."""
    return order.get("productData", [{}])[0].get("products", [])

def _is_product_completed_with_end_done(product: dict) -> Tuple[bool, str]:
    """
    Function takes the product from an order and checks if it is completed including final transport.
    
    Product is completed if:
    - all operations without endFlag: status == "Finished" AND have realOpStart/realOpEnd (ISO) != unknown/null
    - operation with endFlag == True: status == "End transport done" AND have realOpStart/realOpEnd (ISO) != unknown/null

    Args:
        product (dict): Product from an order.

    Returns:
        tuple: (ok: bool, why: str) - True if completed, False otherwise with reason.
    """
    assembly = product.get("assembly", {})
    has_final = False
    final_ok = False

    for _k, op in assembly.items():
        d = op.get("data", {})
        m = op.get("metrics", {})
        s = m.get("status", "")

        if d.get("endFlag") == "True":
            has_final = True

            # 1) final status must be End transport done
            if s != "End transport done":
                return (False, f"final-op status={s!r} (expected End transport done)")

            # 2) and we insist that real assembly ISO stamps are real (not leftovers)
            if not _has_real_iso(m):
                return (False, "final-op missing real ISO assembly times")

            final_ok = True

        else:
            # normal ops must be Finished AND have real ISO assembly stamps
            if s != "Finished":
                return (False, f"op {d.get('uniqueOpID')} @ {d.get('machineID')} status={s!r} (expected Finished)")
            if not _has_real_iso(m):
                return (False, f"op {d.get('uniqueOpID')} missing real ISO assembly times")

    if not has_final:
        return (False, "missing endFlag op")
    if not final_ok:
        return (False, "final op not End transport done")
    return (True, "")

def is_order_ready_to_close(order: dict) -> Tuple[bool, list]:
    """
    Check if all of the operations in the order are finished.
    
    Takes the order and checks if each product within the order is completed including final transport.
    If so it returns a True value, otherwise False along with a list of blockers indicating which products are not yet complete.
    
    Args:
        order (dict): Entire production order.

    Returns:
        tuple: (bool, list): True if order is ready to close, False otherwise with list of blockers.
    """
    blockers = []
    for idx, p in enumerate(_get_products(order), start=1):
        ok, why = _is_product_completed_with_end_done(p)
        if not ok:
            blockers.append((idx, why))
    return (len(blockers) == 0, blockers)

def _has_real_iso(m: dict) -> bool:
    """
    Checks if the metrics dictionary has real ISO timestamps for operation start and end.

    Args:
        m (dict): Metrics dictionary from an operation.

    Returns:
        bool: True if both realOpStart and realOpEnd are valid ISO timestamps, False otherwise.
    """
    def ok(x):
        if x is None: return False
        if not isinstance(x, str): return False
        s = x.strip().lower()
        if not s or s == "null" or s.startswith("unknown"):
            return False
        return True
    return ok(m.get("realOpStart")) and ok(m.get("realOpEnd"))

def get_next_operations(sorted_operations: list, credentials: dict) -> list:
    """
    Selects the next operations by modules based on statuses, dependencies, and module occupancy.
    
    Funciton takes the pre-sorted list of operations and credentials containing module details and select 
    possible next operations to execute. First it checks for possible transport operations and then for regular assembly operations.
    It selects operations on basis if their modules are currently blocked by other operations or not. The selected 
    operations are returned as a list and are differentiated if they are transport or assembly operations later in the main loop.

    Args:
        sorted_operations (list): List of operations sorted by queuePosition and uniqueOpID.
        credentials (dict): Credentials for ThingsBoard access.

    Returns:
        list: List of next operations to execute.
    """
    try:
        modules = credentials["module_details"]

        # Lists of modules in EXACT order from `sorted_operations`
        operations_by_module = {m: [] for m in modules}
        for op in sorted_operations:
            mid = op.get("data", {}).get("machineID")
            if mid in operations_by_module:
                operations_by_module[mid].append(op)

        next_operations = []
        
        blocked_modules = set()
        initial_block_uid = {}  # (če že imaš ta del v tvoji zadnji verziji, pusti)

        # Blocking statuses - PREVERI ALI SO POTREBNE
        blocking_statuses_normal = {"Processing", "Waiting for transport"}          
        blocking_statuses_transport = {"Processing", "Waiting for transport", "Transporting"}
        
        # --- PRE-BLOCK: block modules which have active transport operations ---
        for op in sorted_operations:
            d = op.get("data", {}); m = op.get("metrics", {})
            status = m.get("status")
            start_pos = d.get("AGVstartPos"); end_pos = d.get("AGVendPos")
            end_flag = d.get("endFlag") == "True"
            is_initial = (start_pos == "null" and end_pos in modules)
            is_inter   = (start_pos in modules and end_pos in modules)
            #is_final   = (start_pos in modules and end_pos == "null" and end_flag) PREVERI

            if status in {"Waiting for transport", "Transporting"}:
                if is_inter:
                    blocked_modules.add(start_pos); blocked_modules.add(end_pos)
                elif is_initial:
                    blocked_modules.add(end_pos)
                elif is_final:
                    blocked_modules.add(start_pos) #PREVERI

        # --- FIRST PASS: planning of transports ---
        for module, ops in operations_by_module.items():
            def earlier_unfinished_on_module(candidate: dict) -> bool:
                """Check if there are earlier unfinished operations on the same module as the candidate operation and return True if found."""
                cuid = int(candidate.get("data", {}).get("uniqueOpID", 10**9))
                for o in ops:
                    ouid = int(o.get("data", {}).get("uniqueOpID", 10**9))
                    if ouid < cuid and o.get("metrics", {}).get("status") not in ("Finished", "End transport done"):
                        return True
                return False

            for op in ops:
                d = op.get("data", {}); m = op.get("metrics", {})
                status = m.get("status")
                start_pos = d.get("AGVstartPos"); end_pos = d.get("AGVendPos")

                # Allowed statuses for transport: Waiting / Transport done / Finished
                if status not in {"Waiting", "Finished"}:
                    continue

                end_flag = d.get("endFlag") == "True"
                is_final_candidate = (
                    end_flag
                    and status == "Finished"
                    and m.get("finalTransport") not in {"InProgress", "Done"}
                )

                # If this is a final operation after assembly → allow it as a transport task
                if is_final_candidate:
                    next_operations.append(op)
                    # Reserve the source module so that it does not get assembly in the same cycle
                    blocked_modules.add(d.get("AGVstartPos"))
                    break  # Only one operation per module

                # Skip over transports that are already Finished as before
                if status == "Finished":
                    continue

                # Set transport type based on start/end positions and endFlag
                is_transport = not (start_pos == "null" and end_pos == "null")
                if not is_transport:
                    continue # Not a transport operation
                is_initial = (start_pos == "null" and end_pos in modules) # Start transport operation
                is_inter   = (start_pos in modules and end_pos in modules) # Inter-module transport
                is_final   = (start_pos in modules and end_pos == "null" and end_flag) # End transport operation

                if not (is_initial or is_inter or is_final):
                    continue #TO RES RABIM???

                # If there are earlier unfinished operations on this module, skip
                if earlier_unfinished_on_module(op):
                    continue

                # Check if product assembly order blocks this operation (uniqueOpID dependencies)
                cur_parent = d.get("assemblyParent"); cur_uid = int(d.get("uniqueOpID", 10**9))
                deps_block = any(
                    (so.get("data", {}).get("assemblyParent") == cur_parent) and
                    (int(so.get("data", {}).get("uniqueOpID", 10**9)) < cur_uid) and
                    (so.get("metrics", {}).get("status") not in ("Finished", "End transport done"))
                    for so in sorted_operations
                )
                if deps_block:
                    continue

                # Pick the available transport operation in block the modules that are involved in the transport
                next_operations.append(op)
                if is_inter:
                    blocked_modules.add(start_pos); blocked_modules.add(end_pos) # Reserves both source and target modules
                elif is_initial:
                    blocked_modules.add(end_pos)    # Reserves the target module
                else:  
                    blocked_modules.add(start_pos)  # Reserves the source module
                break  # Only one operation per module
            
        print("[DBG] blocked_modules after transport pass:", blocked_modules)
        
        # --- SECOND PASS: regular assembly operations ---
        for module, ops in operations_by_module.items():
            if module in blocked_modules:
                # If any op on this module is "Transport done", allow assembly despite block
                if not any(o.get("metrics", {}).get("status") == "Transport done" for o in ops):
                    continue

            def earlier_unfinished_exists(candidate: dict) -> bool:
                """Check if there are earlier unfinished operations on the same module as the candidate operation and return True if found."""
                cuid = int(candidate.get("data", {}).get("uniqueOpID", 10**9))
                for o in ops:
                    ouid = int(o.get("data", {}).get("uniqueOpID", 10**9))
                    if ouid < cuid and o.get("metrics", {}).get("status") not in ("Finished", "End transport done"):
                        return True
                return False

            chosen = None
            # 1) Priority status: "Transport done"
            for op in ops:
                d = op.get("data", {}); m = op.get("metrics", {})
                print("[DBG] asm @", module, [(o["data"]["uniqueOpID"], o["metrics"].get("status")) for o in ops])
                if m.get("status") != "Transport done":
                    continue
                if earlier_unfinished_exists(op):
                    continue
                cur_parent = d.get("assemblyParent"); cur_uid = int(d.get("uniqueOpID", 10**9))
                deps_block = any(
                    (so.get("data", {}).get("assemblyParent") == cur_parent) and
                    (int(so.get("data", {}).get("uniqueOpID", 10**9)) < cur_uid) and
                    (so.get("metrics", {}).get("status") not in ("Finished", "End transport done"))
                    for so in sorted_operations
                )
                if not deps_block:
                    chosen = op
                    break

            # 2) Otherwise: "Waiting" no transport at all in this operation
            if chosen is None:
                for op in ops:
                    d = op.get("data", {}); m = op.get("metrics", {})
                    if m.get("status") != "Waiting":
                        continue
                    # "Transport done" should be considered assembly regardless of AGV fields
                    if m.get("status") != "Transport done":
                        is_transport = not (d.get("AGVstartPos")=="null" and d.get("AGVendPos")=="null")
                        if is_transport:
                            continue
                    if earlier_unfinished_exists(op):
                        continue
                    cur_parent = d.get("assemblyParent"); cur_uid = int(d.get("uniqueOpID", 10**9))
                    deps_block = any(
                        (so.get("data", {}).get("assemblyParent") == cur_parent) and
                        (int(so.get("data", {}).get("uniqueOpID", 10**9)) < cur_uid) and
                        (so.get("metrics", {}).get("status") not in ("Finished", "End transport done"))
                        for so in sorted_operations
                    )
                    if not deps_block:
                        chosen = op
                        break

            if chosen is not None:
                next_operations.append(chosen)

        uniq, seen = [], set()
        for op in next_operations:
            key = (op["data"].get("machineID"), op["data"].get("uniqueOpID"))
            if key in seen:
                continue
            seen.add(key)
            uniq.append(op)
        return uniq 

    except Exception as e:
        print(f"[ERROR] Exception in get_next_operations: {e}")
        import traceback; traceback.print_exc()
        
    #diagnostika ker ne štarta op204 ODSTRANI?
    if not next_operations:
        print("[DBG] get_next: no ops; blocked_modules=", blocked_modules)
        print("[DBG] module2 set:", [(o["data"]["uniqueOpID"], o["metrics"]["status"]) for o in operations_by_module.get("module2", [])])
    return next_operations

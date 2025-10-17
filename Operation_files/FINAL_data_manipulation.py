import FINAL_update_attribute as update
import FINAL_read_attribute as read
from logging_functions import normalize_op_times_from_real, ensure_quality_default, now_ms, _ms_to_iso_utc, _belongs_to_this_order_strict, mark_order_start, _coerce_ts_ms
import copy
import traceback
from typing import Dict, Any, Tuple, List

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
    """
    import copy
    import FINAL_read_attribute as read
    import FINAL_update_attribute as update
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

        # podpiraj tudi 'Waiting for transport'
        if current_op_status in ("Finished", "Processing", "Transporting", "Transport done", "Waiting for transport"):
            current_op = current  # že prebrano zgoraj
            op_ident = current_op["data"]["uniqueOpID"]
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

def tag_final_ops_with_endflag(order: Dict[str, Any]) -> Dict[str, Any]:
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

def build_final_transport_task(op: Dict[str, Any], default_agv: str = "AGV1") -> Dict[str, Any]:
    """
    Iz 'zadnje' operacije (z endFlag=True) zgradi transportno nalogo:
    - AGVstartPos = machineID operacije
    - AGVendPos   = "null"  (končni odvoz, brez ciljnega modula)
    - AGV         = default_agv ali op.data.AGV, če obstaja
    - metrics.status = "Waiting" (da vstopi v end_transport state machine)
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

def is_order_completed_with_final_transport(order: Dict[str, Any]) -> bool:
    """
    DN je zaključen, ko:
        - za vse 'navadne' operacije (brez endFlag) velja metrics.status == 'Finished'
        - za operacijo z endFlag == True velja metrics.status == 'Transport done'
            (sprejmemo tudi 'Finished' kot 'NI še narejen končni transport' -> v tem primeru vrnemo False)
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
                # za finalno operacijo je 'Transport done' edino stanje, ki šteje kot dokončano
                if status != "End transport done":
                    return False
            else:
                # za ostale operacije zahtevamo 'Finished'
                if status != "Finished":
                    return False
    return True

def _get_products(order: Dict[str, Any]) -> List[Dict[str, Any]]:
    return order.get("productData", [{}])[0].get("products", [])

def _is_product_completed_with_end_done(product: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Produkt je 'completed' IFF:
        - vse operacije brez endFlag: status == 'Finished'
        - operacija z endFlag == True: status == 'End transport done'  (ne 'Transport done')
    Vrne (ok, razlog_če_ne).
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
            # samo končni odvoz šteje kot zaključek produkta
            if s == "End transport done":
                final_ok = True
            else:
                return (False, f"final-op status={s!r} (expected 'End transport done')")
        else:
            if s != "Finished":
                return (False, f"op {d.get('uniqueOpID')} @ {d.get('machineID')} status={s!r} (expected 'Finished')")
    if not has_final:
        return (False, "missing endFlag op")
    if not final_ok:
        return (False, "final op not 'End transport done'")
    return (True, "")

def is_order_ready_to_close(order: Dict[str, Any]) -> Tuple[bool, list]:
    """
    DN je pripravljen za zaprtje, ko so VSI produkti 'completed' po zgornjem pravilu.
    Vrne (ok, blockers[]) za diagnostiko.
    """
    blockers = []
    for idx, p in enumerate(_get_products(order), start=1):
        ok, why = _is_product_completed_with_end_done(p)
        if not ok:
            blockers.append((idx, why))
    return (len(blockers) == 0, blockers)

def get_next_operations(credentials, order, sorted_operations):
    """
    Izbor naslednjih operacij po modulih na osnovi statusov, odvisnosti in zasedenosti modulov.
    Uporablja že pripravljeno globalno urejenost `sorted_operations` (uniqueOpID, queuePosition).
    
    # --- Predblokiranje zaradi TRANSPORTOV ---
        for module, ops in operations_by_module.items():
            for op in ops:
                d = op.get("data", {}); m = op.get("metrics", {})
                status = m.get("status")
                start_pos = d.get("AGVstartPos")
                end_pos   = d.get("AGVendPos")

                # (1) med-modulski transport v čakanju: blokiraj start in cilj
                if status == "Waiting for transport" and start_pos != "null" and end_pos != "null":
                    blocked_modules.add(start_pos); blocked_modules.add(end_pos)

                # (2) ZAČETNI transport (AGVstartPos=="null"): rezerviraj ciljni modul
                if start_pos == "null" and end_pos in modules and status in {"Waiting", "Waiting for transport", "Transporting"}:
                    blocked_modules.add(end_pos)
                    # (neobvezno) beleženje najnižjega UID začetnega transporta za override
                    uid = int(d.get("uniqueOpID", 10**9))
                    if (end_pos not in initial_block_uid) or (uid < initial_block_uid[end_pos]):
                        initial_block_uid[end_pos] = uid
    
    """
    try:
        modules = credentials["module_details"]

        # Košare po modulih v NATANČNEM vrstnem redu iz `sorted_operations`
        operations_by_module = {m: [] for m in modules}
        for op in sorted_operations:
            mid = op.get("data", {}).get("machineID")
            if mid in operations_by_module:
                operations_by_module[mid].append(op)

        next_operations = []
        
        blocked_modules = set()
        initial_block_uid = {}  # (če že imaš ta del v tvoji zadnji verziji, pusti)

        # Blokirne množice
        blocking_statuses_normal = {"Processing", "Waiting for transport"}          # brez 'Transport done'
        blocking_statuses_transport = {"Processing", "Waiting for transport", "Transporting"}
        
        # --- PRE-BLOCK: zablokiraj module zaradi AKTIVNIH transportov ---
        for op in sorted_operations:
            d = op.get("data", {}); m = op.get("metrics", {})
            status = m.get("status")
            start_pos = d.get("AGVstartPos"); end_pos = d.get("AGVendPos")
            end_flag = d.get("endFlag") == "True"
            is_initial = (start_pos == "null" and end_pos in modules)
            is_inter   = (start_pos in modules and end_pos in modules)
            #is_final   = (start_pos in modules and end_pos == "null" and end_flag)

            if status in {"Waiting for transport", "Transporting"}:
                if is_inter:
                    blocked_modules.add(start_pos); blocked_modules.add(end_pos)
                elif is_initial:
                    blocked_modules.add(end_pos)
                elif is_final:
                    blocked_modules.add(start_pos)

        # --- PRVI PREHOD: načrtuj TRANSPORTE ---
        for module, ops in operations_by_module.items():
            #if any(o.get("metrics", {}).get("status") in blocking_statuses_transport for o in ops):
                #continue

            def earlier_unfinished_on_module(candidate):
                cuid = int(candidate.get("data", {}).get("uniqueOpID", 10**9))
                for o in ops:
                    ouid = int(o.get("data", {}).get("uniqueOpID", 10**9))
                    if ouid < cuid and o.get("metrics", {}).get("status") != "Finished":
                        return True
                return False

            for op in ops:
                d = op.get("data", {}); m = op.get("metrics", {})
                status = m.get("status")
                start_pos = d.get("AGVstartPos"); end_pos = d.get("AGVendPos")

                # dovoljen vstop v transport: Waiting / Transport done / Finished (za sintetiko končnega)
                if status not in {"Waiting", "Transport done", "Finished"}:
                    continue

                end_flag = d.get("endFlag") == "True"
                is_final_candidate = (
                    end_flag
                    and status == "Finished"
                    #and d.get("AGVstartPos") in modules
                    #and d.get("AGVendPos") == "null"
                    and m.get("finalTransport") not in {"InProgress", "Done"}
                )

                # ➊ Če je to končna operacija po montaži → jo prepustimo kot transportno nalogo
                if is_final_candidate:
                    next_operations.append(op)
                    # rezerviraj izvorni modul, da v istem ciklu ne dobi še montaže
                    blocked_modules.add(d.get("AGVstartPos"))
                    break  # ena naloga na modul

                # ➋ Vse ostale 'Finished' transporte preskočimo kot prej
                if status == "Finished":
                    continue

                # ---- NOVO: tipizacija transporta (dovolimo tudi KONČNI transport zapisa) ----
                is_transport = not (start_pos == "null" and end_pos == "null")
                if not is_transport:
                    continue
                is_initial = (start_pos == "null" and end_pos in modules)
                is_inter   = (start_pos in modules and end_pos in modules)
                # KONČNI transport zapis: start v modulu, end == "null" in endFlag=True
                is_final   = (start_pos in modules and end_pos == "null" and end_flag)

                if not (is_initial or is_inter or is_final):
                    continue

                # UID pravilo po modulu
                if earlier_unfinished_on_module(op):
                    continue

                # Odvisnosti po assemblyParent (po uniqueOpID)
                cur_parent = d.get("assemblyParent"); cur_uid = int(d.get("uniqueOpID", 10**9))
                deps_block = any(
                    (so.get("data", {}).get("assemblyParent") == cur_parent) and
                    (int(so.get("data", {}).get("uniqueOpID", 10**9)) < cur_uid) and
                    (so.get("metrics", {}).get("status") != "Finished")
                    for so in sorted_operations
                )
                if deps_block:
                    continue

                # izberi transport in pravilno blokiraj module
                next_operations.append(op)
                if is_inter:
                    blocked_modules.add(start_pos); blocked_modules.add(end_pos)
                elif is_initial:
                    blocked_modules.add(end_pos)    # rezerviraj cilj
                else:  # is_final
                    blocked_modules.add(start_pos)  # odpeljemo s stroja, cilj ni modul
                break  # ena transportna naloga na modul

        # --- DRUGI PREHOD: NAVADNE operacije (prednost: 'Transport done') ---
        for module, ops in operations_by_module.items():
            if module in blocked_modules:
                # Dovoli montažo, če je prednostna (nižji UID od rezerviranega začetnega transporta)
                min_uid = initial_block_uid.get(module, 10**9)
                # poišči najbolj zgodnjo kandidatko na modulu
                maybe = min((int(o["data"].get("uniqueOpID", 10**9)) for o in ops if o["metrics"].get("status") in ("Transport done","Waiting")
                            and (o["data"].get("AGVstartPos")=="null" and o["data"].get("AGVendPos")=="null")), default=10**9)
                if maybe < min_uid:
                    pass  # ne prekinjaj; dovoli 2. prehod za ta modul
                else:
                    continue

            #if any(o.get("metrics", {}).get("status") in blocking_statuses_normal for o in ops):
                #continue

            def earlier_unfinished_exists(candidate):
                cuid = int(candidate.get("data", {}).get("uniqueOpID", 10**9))
                for o in ops:
                    ouid = int(o.get("data", {}).get("uniqueOpID", 10**9))
                    if ouid < cuid and o.get("metrics", {}).get("status") != "Finished":
                        return True
                return False

            chosen = None
            # 1) prednostno: 'Transport done'
            for op in ops:
                d = op.get("data", {}); m = op.get("metrics", {})
                if m.get("status") != "Transport done":
                    continue
                if earlier_unfinished_exists(op):
                    continue
                cur_parent = d.get("assemblyParent"); cur_uid = int(d.get("uniqueOpID", 10**9))
                deps_block = any(
                    (so.get("data", {}).get("assemblyParent") == cur_parent) and
                    (int(so.get("data", {}).get("uniqueOpID", 10**9)) < cur_uid) and
                    (so.get("metrics", {}).get("status") != "Finished")
                    for so in sorted_operations
                )
                if not deps_block:
                    chosen = op
                    break

            # 2) sicer: 'Waiting' NE-transport
            if chosen is None:
                for op in ops:
                    d = op.get("data", {}); m = op.get("metrics", {})
                    if m.get("status") != "Waiting":
                        continue
                    is_transport = not (d.get("AGVstartPos") == "null" and d.get("AGVendPos") == "null")
                    if is_transport:
                        continue
                    if earlier_unfinished_exists(op):
                        continue
                    cur_parent = d.get("assemblyParent"); cur_uid = int(d.get("uniqueOpID", 10**9))
                    deps_block = any(
                        (so.get("data", {}).get("assemblyParent") == cur_parent) and
                        (int(so.get("data", {}).get("uniqueOpID", 10**9)) < cur_uid) and
                        (so.get("metrics", {}).get("status") != "Finished")
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
        
    #diagnostika ker ne štarta op204
    if not next_operations:
        print("[DBG] get_next: no ops; blocked_modules=", blocked_modules)
        print("[DBG] module2 set:", [(o["data"]["uniqueOpID"], o["metrics"]["status"]) 
                                    for o in operations_by_module.get("module2", [])])
    return next_operations

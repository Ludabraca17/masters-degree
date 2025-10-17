# File for storing logging functions used in system validation
import os, json, time
from typing import Set
import datetime as date
from typing import Dict, Any, Iterable, Tuple, Optional

# --- ČAS ---
def now_ms() -> int:
    return int(time.time() * 1000)

# --- ŽIGOSANJE OPERACIJ ---
def stamp_operation_metrics(op_metrics: Dict[str, Any],
                            new_status: str,
                            transport_event: Optional[str] = None) -> Dict[str, Any]:
    """
    Idempotentno doda časovne žige:
    - startTs, ko operacija prvič vstopi v Processing/Transporting
    - transportStartTs / transportEndTs, ko je transport_event 'start'/'end'
    - endTs, ko preide v Finished
    """
    t = now_ms()
    if new_status in ("Processing", "Transporting"):
        op_metrics.setdefault("startTs", t)
    if transport_event == "start":
        op_metrics.setdefault("transportStartTs", t)
    elif transport_event == "end":
        op_metrics.setdefault("transportEndTs", t)
    if new_status == "Finished":
        op_metrics.setdefault("endTs", t)
    return op_metrics

# --- POSEBNI ŽIGI ZA ZAČETNI/KONČNI TRANSPORT ---

def mark_initial_transport(op_metrics: Dict[str, Any], event: str) -> None:
    """
    Zabeleži čas za ZAČETNI transport.
    event ∈ {"start","end"}
    """
    t = now_ms()
    if event == "start":
        op_metrics.setdefault("initialTransportStartTs", t)
    elif event == "end":
        op_metrics.setdefault("initialTransportEndTs", t)

def mark_final_transport(op_metrics: Dict[str, Any], event: str) -> None:
    """
    Zabeleži čas za KONČNI transport.
    event ∈ {"start","end"}
    """
    t = now_ms()
    if event == "start":
        op_metrics.setdefault("finalTransportStartTs", t)
    elif event == "end":
        op_metrics.setdefault("finalTransportEndTs", t)

def ensure_quality_default(op_metrics: Dict[str, Any], default: str = "OK") -> None:
    """Če modul ne zapiše kakovosti, privzeto označi 'OK' ob zaključku."""
    op_metrics.setdefault("quality", default)

# --- ŽIGOSANJE NAROČILA (DN) ---
def mark_order_start(order_data: Dict[str, Any]) -> None:
    """Postavi productData[0].orderStartTs, če še ne obstaja."""
    pd0 = order_data.get("productData", [{}])[0]
    if "orderStartTs" not in pd0:
        pd0["orderStartTs"] = now_ms()

def mark_order_end(order_data: Dict[str, Any]) -> None:
    """Postavi productData[0].orderEndTs (pokliči, ko so VSE operacije Finished)."""
    pd0 = order_data.get("productData", [{}])[0]
    pd0["orderEndTs"] = now_ms()

# --- LOKALNI ZAPIS ZAKLJUČENEGA DN ---
def save_finished_order(order_data: Dict[str, Any],
                        out_dir: str = "finished_orders",
                        write_jsonl: bool = True,
                        extra_summary: Optional[Dict[str, Any]] = None) -> str:
    os.makedirs(out_dir, exist_ok=True)
    ts_iso = date.datetime.now().strftime("%Y%m%d_%H%M%S")
    header = order_data.get("productData", [{}])[0]
    order_id = (header.get("orderId") or header.get("orderID")
                or order_data.get("header", {}).get("orderID")
                or f"DN_{ts_iso}")

    # ✨ 1) Najprej obogati DN z berljivimi časi (doda startTsMs/endTsMs/procDurationSec...)
    enrich_times_readable(order_data)

    # ✨ 2) Šele nato izračunaj summary (da “vidi” *_Ms/*_Sec)
    summary = build_quick_summary(order_data)
    if extra_summary:
        summary.update(extra_summary)

    # 3) Zapiši .txt (pretty JSON) — zdaj že vsebuje obogatena polja
    txt_path = os.path.join(out_dir, f"{ts_iso}_{order_id}.txt")
    tmp = txt_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(order_data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, txt_path)

    # 4) (opcijsko) JSONL
    if write_jsonl:
        jsonl_path = os.path.join(out_dir, "finished_orders_log.jsonl")
        record = {"saved_at": ts_iso, "order_id": order_id,
                    "summary": summary, "order": order_data}
        with open(jsonl_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return os.path.abspath(txt_path)


def build_quick_summary(order_data: Dict[str, Any]) -> Dict[str, Any]:
    """Povzetek za Test A/B: DN čas in zamik do prve operacije."""
    pd0 = order_data.get("productData", [{}])[0]
    products = pd0.get("products", [])
    orderStartTs = pd0.get("orderStartTs")
    orderEndTs = pd0.get("orderEndTs")
    first_start = _first_start_ts(products)
    return {
        "num_products": len(products),
        "orderStartTs": orderStartTs,
        "orderEndTs": orderEndTs,
        "t_order": (orderEndTs - orderStartTs) if orderStartTs and orderEndTs else None,
        "t_delay": (first_start - orderStartTs) if first_start and orderStartTs else None,
    }

def _first_start_ts(products: Iterable[Dict[str, Any]]) -> Optional[int]:
    starts = []
    for p in products:
        for op in p.get("assembly", {}).values():
            st = op.get("metrics", {}).get("startTs")
            if st:
                starts.append(st)
    return min(starts) if starts else None

# --- KPI / OEE (D) ---
def summarize_for_kpi(order_data: Dict[str, Any],
                    ideal_times: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    """
    Izračun Availability/Performance/Quality/OEE iz žigov.
    ideal_times: slovar idealnih procesnih časov (s) po ključu uniqueOpID ali 'machineID:part'.
    DN se NE spreminja.
    """
    pd0 = order_data.get("productData", [{}])[0]
    products = pd0.get("products", [])
    orderStartTs = pd0.get("orderStartTs")
    orderEndTs = pd0.get("orderEndTs")
    t_order = (orderEndTs - orderStartTs) if orderStartTs and orderEndTs else None

    ops: list[Tuple[int, int, float, str]] = []  # (start,end,ideal_proc_time,quality)
    good_products, total_products = 0, 0

    for p in products:
        total_products += 1
        all_ok = True
        for op in p.get("assembly", {}).values():
            m = op.get("metrics", {})
            d = op.get("data", {})
            start, end = m.get("startTs"), m.get("endTs")
            q = m.get("quality", "OK")
            ideal = None
            if ideal_times:
                # prednost uniqueOpID, sicer (machineID:part)
                key1 = str(d.get("uniqueOpID"))
                key2 = f"{d.get('machineID')}:{d.get('part')}"
                ideal = ideal_times.get(key1, ideal_times.get(key2))
            if start and end:
                ops.append((start, end, float(ideal) if ideal is not None else None, q))
            if q != "OK":
                all_ok = False
        if all_ok:
            good_products += 1

    # 'Lite' run_time: vsota (end-start) po operacijah (konzervativno ok)
    run_time = sum((e - s) for (s, e, *_rest) in ops) if ops else None
    ideal_time = sum(it for *_x, it, _q in ops if it is not None) if ops else None
    availability = (run_time / t_order) if (run_time and t_order) else None
    performance  = (ideal_time / run_time) if (ideal_time and run_time) else None
    quality      = (good_products / total_products) if total_products else None
    oee          = (availability * performance * quality) if all(
        x is not None for x in (availability, performance, quality)
    ) else None

    return {
        "t_order": t_order,
        "run_time": run_time,
        "ideal_time": ideal_time,
        "availability": availability,
        "performance": performance,
        "quality": quality,
        "oee": oee,
        "good": good_products,
        "total": total_products,
    }

def _coerce_ts_ms(x: Any) -> Optional[int]:
    """
    Pretvori različne oblike časa v epoch ms:
    - int/float (ms ali s) -> ms
    - ISO string ('2025-10-13T14:05:06Z' ali '2025-10-13 14:05:06') -> ms
    - drugače -> None
    """
    if x is None:
        return None
    # številsko?
    if isinstance(x, (int, float)):
        # heuristika: če je < 10^12, obravnavaj kot sekunde
        return int(x if x > 10**12 else x * 1000)
    # niz?
    if isinstance(x, str):
        s = x.strip()
        if not s or s.lower() == "null" or s.lower().startswith("unknown"):
            return None
        # poskusi ISO oblike
        for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ",
                    "%Y-%m-%dT%H:%M:%SZ",
                    "%Y-%m-%d %H:%M:%S",
                    "%Y/%m/%d %H:%M:%S"):
            try:
                dt_obj = date.datetime.strptime(s, fmt).replace(tzinfo=date.timezone.utc)
                return int(dt_obj.timestamp() * 1000)
            except ValueError:
                continue
        # poskusi datetime.fromisoformat (lokalno, brez Z)
        try:
            dt_obj = date.datetime.fromisoformat(s)
            # če nima timezone, predpostavimo UTC
            if dt_obj.tzinfo is None:
                dt_obj = dt_obj.replace(tzinfo=date.timezone.utc)
            return int(dt_obj.timestamp() * 1000)
        except Exception:
            return None
    return None

def normalize_op_times_from_real(op_metrics: dict,
                                attr_last_update_ts: Optional[int] = None,
                                set_quality_default: bool = True,
                                default_quality: str = "OK") -> None:
    """
    Idempotentno:
    - če obstaja realOpStart in manjka startTs -> startTs = realOpStart (v ms)
    - če obstaja realOpEnd   in manjka endTs   -> endTs   = realOpEnd   (v ms)
    - če status == Finished in endTs še vedno manjka -> endTs = attr_last_update_ts ali now_ms()
    - opcijsko doda quality, če manjka
    """
    # 1) iz realOpStart/realOpEnd
    rst = _coerce_ts_ms(op_metrics.get("realOpStart"))
    if rst is not None:
        op_metrics.setdefault("startTs", rst)

    ret = _coerce_ts_ms(op_metrics.get("realOpEnd"))
    if ret is not None:
        op_metrics.setdefault("endTs", ret)

    # 2) če status Finished in endTs še manjka
    if op_metrics.get("status") == "Finished" and "endTs" not in op_metrics:
        op_metrics["endTs"] = attr_last_update_ts or now_ms()

    # 3) kakovost (po želji)
    if set_quality_default:
        op_metrics.setdefault("quality", default_quality)


def _parse_iso_to_ms(x: Any) -> Optional[int]:
    """
    Prebere UTC ISO str in vrne epoch ms. Ne spreminja polj v DN.
    Podpira: '...%Y-%m-%dT%H:%M:%S.%fZ', '...%Y-%m-%dT%H:%M:%SZ', 'YYYY-mm-dd HH:MM:SS'
    """
    if x is None:
        return None
    if isinstance(x, (int, float)):
        # že ms ali s → normaliziraj v ms
        return int(x if x > 10**12 else x * 1000)
    if not isinstance(x, str):
        return None
    s = x.strip()
    if not s or s.lower() == "null" or s.lower().startswith("unknown"):
        return None

    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ",
                "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%d %H:%M:%S",
                "%Y/%m/%d %H:%M:%S"):
        try:
            dt_obj = date.datetime.strptime(s, fmt).replace(tzinfo=date.timezone.utc)
            return int(dt_obj.timestamp() * 1000)
        except ValueError:
            continue
    # generični ISO (lahko brez 'Z'); če ni tz, privzemi UTC
    try:
        dt_obj = date.datetime.fromisoformat(s)
        if dt_obj.tzinfo is None:
            dt_obj = dt_obj.replace(tzinfo=date.timezone.utc)
        return int(dt_obj.timestamp() * 1000)
    except Exception:
        return None
    

def enrich_times_readable(order_data: Dict[str, Any]) -> None:
    """
    Ne spremeni obstoječih ISO polj. Samo doda:
    - startTsMs/endTsMs, procDurationMs/procDurationSec
    - transportDurationMs/transportDurationSec (če obstajata transportStartTs/EndTs)
    - handoverDelayMs/handoveDelaySec (transportEndTs -> realOpStart)
    - na DN: t_order_ms/sec, t_delay_ms/sec
    - agregatno 'readableSummary' za hiter pregled.
    """
    try:
        pd0 = order_data.get("productData", [{}])[0]
        products = pd0.get("products", [])

        orderStartTs = pd0.get("orderStartTs")
        orderEndTs   = pd0.get("orderEndTs")

        first_start_ms = None
        ops_readable = []

        for p in products:
            assembly = p.get("assembly", {})
            for op_key, op in assembly.items():
                m = op.get("metrics", {})

                # --- parse processing ISO -> ms (does not overwrite ISO) ---
                rst_iso = m.get("realOpStart")
                ret_iso = m.get("realOpEnd")
                start_ms = _parse_iso_to_ms(rst_iso)
                end_ms   = _parse_iso_to_ms(ret_iso)
                go = m.get("transportGoTs")
                ts = m.get("transportStartTs")
                te = m.get("transportEndTs")
                
                if ts and go:
                    m.setdefault("transportWaitMs", max(go - ts, 0))
                    m.setdefault("transportWaitSec", m["transportWaitMs"] / 1000.0)
                if go and te:
                    m.setdefault("transportDriveMs", max(te - go, 0))
                    m.setdefault("transportDriveSec", m["transportDriveMs"] / 1000.0)                

                if start_ms is not None:
                    m.setdefault("startTsMs", start_ms)
                    if first_start_ms is None:
                        first_start_ms = start_ms
                if end_ms is not None:
                    m.setdefault("endTsMs", end_ms)

                if start_ms is not None and end_ms is not None and end_ms >= start_ms:
                    dur_ms = end_ms - start_ms
                    m.setdefault("procDurationMs", dur_ms)
                    m.setdefault("procDurationSec", round(dur_ms / 1000.0, 3))

                # --- read transport timestamps (ms) ---
                t_st = m.get("transportStartTs")
                t_en = m.get("transportEndTs")

                # transport duration
                if isinstance(t_st, (int, float)) and isinstance(t_en, (int, float)) and t_en >= t_st:
                    t_dur = int(t_en - t_st)
                    m.setdefault("transportDurationMs", t_dur)
                    m.setdefault("transportDurationSec", round(t_dur / 1000.0, 3))

                # handover delay (transport end -> processing start)
                if isinstance(t_en, (int, float)) and start_ms is not None and start_ms >= t_en:
                    hd = int(start_ms - t_en)
                    m.setdefault("handoverDelayMs", hd)
                    m.setdefault("handoverDelaySec", round(hd / 1000.0, 3))

                # summary row
                ops_readable.append({
                    "opKey": op_key,
                    "uniqueOpID": op.get("data", {}).get("uniqueOpID"),
                    "status": m.get("status"),
                    "procDurationMs": m.get("procDurationMs"),
                    "transportDurationMs": m.get("transportDurationMs"),
                    "handoverDelayMs": m.get("handoverDelayMs"),
                })

        # DN-level summaries
        if isinstance(orderStartTs, (int, float)) and isinstance(orderEndTs, (int, float)) and orderEndTs >= orderStartTs:
            pd0.setdefault("t_order_ms", int(orderEndTs - orderStartTs))
            pd0.setdefault("t_order_sec", round((orderEndTs - orderStartTs) / 1000.0, 3))

        if isinstance(first_start_ms, (int, float)) and isinstance(orderStartTs, (int, float)):
            delay_ms = int(first_start_ms - orderStartTs)
            if delay_ms >= 0:
                pd0.setdefault("t_delay_ms", delay_ms)
                pd0.setdefault("t_delay_sec", round(delay_ms / 1000.0, 3))

        order_data.setdefault("readableSummary", {
            "ops": ops_readable,
            "t_order_ms": pd0.get("t_order_ms"),
            "t_order_sec": pd0.get("t_order_sec"),
            "t_delay_ms": pd0.get("t_delay_ms"),
            "t_delay_sec": pd0.get("t_delay_sec"),
            "num_products": len(products)
        })
    except Exception as e:
        print(f"[WARN] enrich_times_readable failed: {e}")
        
def _ms_to_iso_utc(ms):
    """
    Pretvori epoch ms -> ISO UTC 'YYYY-MM-DDTHH:MM:SS.mmmZ'.
    Ne meče izjeme; ob napaki vrne None.
    """
    if ms is None:
        return None
    try:
        ts = float(ms) / 1000.0
        dt = date.datetime.utcfromtimestamp(ts).replace(tzinfo=date.timezone.utc)
        # vrni z milisekundami (3 decimalke)
        iso_full = dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        return iso_full[:-4] + "Z"  # odrežemo na mmmZ
    except Exception:
        return None

def _belongs_to_this_order_strict(current_op: dict,
                                  order_start_ts: Optional[int],
                                  active_states: Optional[Iterable[str]] = None) -> bool:
    """
    Odloča izključno po NR ISO časih (realOpStart/realOpEnd), brez normalizacije.
    Če order_start_ts manjka, dovoli 'aktivna' stanja (npr. Setup, Processing, ...), ne pa Finished.
    """
    m = (current_op or {}).get("metrics", {})
    status = m.get("status", "")
    active: Set[str] = set(active_states or ("Processing", "Transporting", "Waiting for transport", "Waiting", "Setup"))

    # Brez order_start_ts: ne računamo razlik; dovolimo le aktivna stanja (ne Finished)
    if not isinstance(order_start_ts, (int, float)):
        return status in active

    # Uporabi SAMO NR ISO čase
    st = _coerce_ts_ms(m.get("realOpStart"))
    en = _coerce_ts_ms(m.get("realOpEnd"))

    if st is None and en is None:
        # brez ISO žigov: dovolimo le aktivna stanja
        return status in active

    TOL = 2000  # 2 s toleranca
    if st is not None and st >= (order_start_ts - TOL):
        return True
    if en is not None and en >= (order_start_ts - TOL):
        return True
    return False

def mark_transport_go(op_metrics: Dict[str, Any]) -> None:
    op_metrics.setdefault("transportGoTs", now_ms())
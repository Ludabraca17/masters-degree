# analyze_finished_orders.py
# Python-only analysis for finished_orders (no pandas, no seaborn).
# Saves outputs into a NEW subdirectory inside finished_orders/.

import argparse, json, statistics as stats, pathlib, sys, csv, datetime, math
from typing import Dict, Any, List, Tuple, Optional
import matplotlib.pyplot as plt  # one chart per figure, no custom colors

# ---------- paths & loading ----------

def find_finished_orders_root(cli_root: Optional[str]) -> pathlib.Path:
    if cli_root:
        root = pathlib.Path(cli_root).expanduser().resolve()
        if not root.exists():
            sys.exit(f"[ERR] Path does not exist: {root}")
        return root
    for c in [pathlib.Path("finished_orders"),
              pathlib.Path("../finished_orders"),
              pathlib.Path("../../finished_orders")]:
        if c.exists():
            return c.resolve()
    sys.exit("[ERR] Could not find 'finished_orders/'. Use --root <path>.")

def load_orders(root: pathlib.Path) -> List[Dict[str, Any]]:
    jsonl = root / "finished_orders_log.jsonl"
    orders: List[Dict[str, Any]] = []
    if jsonl.exists():
        with jsonl.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                order = rec.get("order")
                if order:
                    orders.append(order)
        if orders:
            print(f"[INFO] Loaded {len(orders)} orders from JSONL: {jsonl}")
            return orders
    txt_files = sorted(root.glob("*_ord*.txt"))
    for p in txt_files:
        try:
            with p.open("r", encoding="utf-8") as f:
                order = json.load(f)
                orders.append(order)
        except Exception as e:
            print(f"[WARN] Failed to load {p.name}: {e}")
    if not orders:
        sys.exit(f"[ERR] No orders found in {root}.")
    print(f"[INFO] Loaded {len(orders)} orders from TXT files in: {root}")
    return orders

def load_ideal_times(path: Optional[str]) -> Optional[Dict[str, float]]:
    if not path:
        return None
    p = pathlib.Path(path).expanduser().resolve()
    if not p.exists():
        sys.exit(f"[ERR] Ideal times file not found: {p}")
    try:
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
        # allow keys as uniqueOpID OR "machineID:part"; values in seconds
        return {str(k): float(v) for k, v in data.items()}
    except Exception as e:
        sys.exit(f"[ERR] Failed to read ideal times JSON: {e}")

# ---------- helpers & transforms ----------

def get_pd0(order: Dict[str, Any]) -> Dict[str, Any]:
    return order.get("productData", [{}])[0]

def safe_num(x):
    return x if isinstance(x, (int, float)) else None

def med_iqr(values: List[Optional[float]]) -> Tuple[Optional[float], Optional[float]]:
    vals = [float(v) for v in values if isinstance(v, (int, float))]
    if not vals:
        return None, None
    vals.sort()
    med = stats.median(vals)
    n = len(vals)
    lower = vals[: n // 2]
    upper = vals[(n + 1) // 2 :]
    if lower and upper:
        q1 = stats.median(lower); q3 = stats.median(upper); iqr = q3 - q1
    else:
        iqr = 0.0
    return round(med, 3), round(iqr, 3)

def group_by(rows: List[Dict[str, Any]], key: str) -> Dict[Any, List[Dict[str, Any]]]:
    g: Dict[Any, List[Dict[str, Any]]] = {}
    for r in rows:
        g.setdefault(r.get(key), []).append(r)
    return g

def flatten_rows(orders: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for order in orders:
        pd0 = get_pd0(order)
        order_id = pd0.get("orderId") or pd0.get("orderID") or "unknown"
        t_order_sec = safe_num(pd0.get("t_order_sec"))
        t_delay_sec = safe_num(pd0.get("t_delay_sec"))
        for p in pd0.get("products", []):
            for op_key, op in p.get("assembly", {}).items():
                d = op.get("data", {})
                m = op.get("metrics", {})
                rows.append({
                    "order_id": order_id,
                    "op_key": op_key,
                    "uniqueOpID": d.get("uniqueOpID"),
                    "machineID": d.get("machineID"),
                    "part": d.get("part"),
                    "queuePosition": d.get("queuePosition"),
                    "status": m.get("status"),
                    "proc_sec": safe_num(m.get("procDurationSec")),
                    "transport_sec": safe_num(m.get("transportDurationSec")),
                    "handover_sec": safe_num(m.get("handoverDelaySec")),
                    # timestamps for Gantt (ms; may be None)
                    "t_st_ms": m.get("transportStartTs"),
                    "t_en_ms": m.get("transportEndTs"),
                    "p_st_ms": m.get("startTsMs"),
                    "p_en_ms": m.get("endTsMs"),
                    "t_order_sec": t_order_sec,
                    "t_delay_sec": t_delay_sec,
                })
    if not rows:
        sys.exit("[ERR] Orders loaded but no operations found (empty 'products/assembly').")
    return rows

# ---------- textual stats ----------

def print_op_stats(rows: List[Dict[str, Any]]) -> None:
    by_uop = group_by(rows, "uniqueOpID")
    print("\n=== Per-operation stats (median [IQR], n) ===")
    print("(processing / transport / handover in seconds)\n")
    for u, items in sorted(by_uop.items(), key=lambda kv: (str(kv[0]))):
        mach = items[0].get("machineID"); part = items[0].get("part")
        p_med, p_iqr = med_iqr([x["proc_sec"] for x in items])
        t_med, t_iqr = med_iqr([x["transport_sec"] for x in items])
        h_med, h_iqr = med_iqr([x["handover_sec"] for x in items])
        n = len(items)
        print(f"Op {u} ({mach}:{part}) | proc {p_med}[{p_iqr}]  transport {t_med}[{t_iqr}]  handover {h_med}[{h_iqr}]  (n={n})")

# ---------- plotting primitives ----------

def bar_chart(xlabels, values, title, path, ylabel="seconds"):
    fig = plt.figure()
    ax = fig.add_subplot(111)
    ax.bar(range(len(values)), values)
    ax.set_xticks(range(len(values)))
    ax.set_xticklabels([str(x) for x in xlabels], rotation=45, ha="right")
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)

def hist_chart(values, title, path, bins=10, xlabel="seconds"):
    vals = [v for v in values if isinstance(v, (int, float))]
    if not vals:
        return
    fig = plt.figure()
    ax = fig.add_subplot(111)
    ax.hist(vals, bins=bins)
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("count")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)

def line_chart(x, y, title, path, xlabel="order index", ylabel="seconds"):
    xs = list(range(len(y))) if x is None else x
    ys = [v if isinstance(v, (int, float)) else None for v in y]
    xs2, ys2 = zip(*[(xi, yi) for xi, yi in zip(xs, ys) if yi is not None]) if any(v is not None for v in ys) else ([],[])
    fig = plt.figure()
    ax = fig.add_subplot(111)
    if xs2:
        ax.plot(xs2, ys2, marker="o")
    ax.set_title(title); ax.set_xlabel(xlabel); ax.set_ylabel(ylabel)
    fig.tight_layout(); fig.savefig(path, dpi=150); plt.close(fig)

def stacked_bar_three(xlabels, a, b, c, title, path, ylabel="seconds"):
    # a+b+c stacked per label
    idx = list(range(len(xlabels)))
    fig = plt.figure()
    ax = fig.add_subplot(111)
    a2 = [v or 0.0 for v in a]
    b2 = [v or 0.0 for v in b]
    c2 = [v or 0.0 for v in c]
    p1 = ax.bar(idx, a2, label="transport")
    p2 = ax.bar(idx, b2, bottom=a2, label="handover")
    bottom_c = [x+y for x,y in zip(a2,b2)]
    p3 = ax.bar(idx, c2, bottom=bottom_c, label="processing")
    ax.set_xticks(idx); ax.set_xticklabels([str(x) for x in xlabels], rotation=45, ha="right")
    ax.set_title(title); ax.set_ylabel(ylabel); ax.legend()
    fig.tight_layout(); fig.savefig(path, dpi=150); plt.close(fig)

# ---------- advanced plots for Chapter 4 ----------

def make_gantt_latest_order(orders: List[Dict[str, Any]], out_path: pathlib.Path) -> None:
    # pick the last order by orderEndTs if present; else by file order
    if not orders:
        return
    # try to choose by orderEndTs (ms) if available
    def ord_end_ms(o):
        pd0 = get_pd0(o); return pd0.get("orderEndTs") or 0
    order = sorted(orders, key=ord_end_ms)[-1]
    pd0 = get_pd0(order)
    base = pd0.get("orderStartTs") or 0
    rows = []
    for p in pd0.get("products", []):
        for op_key, op in p.get("assembly", {}).items():
            d = op.get("data", {}); m = op.get("metrics", {})
            label = f"{d.get('uniqueOpID')}:{d.get('part')}"
            # transport segment
            t0 = m.get("transportStartTs"); t1 = m.get("transportEndTs")
            if isinstance(t0,(int,float)) and isinstance(t1,(int,float)) and t1>=t0:
                rows.append(("transport", label, (t0-base)/1000.0, (t1-t0)/1000.0))
            # handover: transportEnd -> procStart
            p0 = m.get("startTsMs"); p1 = m.get("endTsMs")
            if isinstance(t1,(int,float)) and isinstance(p0,(int,float)) and p0>=t1:
                rows.append(("handover", label, (t1-base)/1000.0, (p0-t1)/1000.0))
            # processing
            if isinstance(p0,(int,float)) and isinstance(p1,(int,float)) and p1>=p0:
                rows.append(("processing", label, (p0-base)/1000.0, (p1-p0)/1000.0))

    if not rows:
        return
    # sort by queuePosition / label to be stable
    try:
        order_ops = []
        for p in pd0.get("products", []):
            for op_key, op in p.get("assembly", {}).items():
                d = op.get("data", {})
                order_ops.append((d.get("queuePosition") or 9999, f"{d.get('uniqueOpID')}:{d.get('part')}"))
        order_ops.sort()
        label_order = [lab for _, lab in order_ops]
    except Exception:
        label_order = sorted(set([lab for _t, lab, _s, _d in rows]))

    # plot
    fig = plt.figure()
    ax = fig.add_subplot(111)
    ylabels = label_order
    ymap = {lab:i for i, lab in enumerate(ylabels)}
    for seg, lab, start_s, dur_s in rows:
        y = ymap.get(lab, 0)
        ax.broken_barh([(start_s, dur_s)], (y-0.4, 0.8))
    ax.set_yticks(range(len(ylabels))); ax.set_yticklabels(ylabels)
    ax.set_xlabel("seconds from orderStart")
    ax.set_title("Gantt timeline (latest order)")
    fig.tight_layout(); fig.savefig(out_path, dpi=150); plt.close(fig)

def make_control_charts(rows: List[Dict[str, Any]], out_dir: pathlib.Path, top_k: int = 6) -> None:
    # top K operations by count
    by_uop = group_by(rows, "uniqueOpID")
    freq = sorted([(u, len(items)) for u, items in by_uop.items() if u is not None],
                  key=lambda x: x[1], reverse=True)[:top_k]
    for u, _n in freq:
        items = by_uop[u]
        # order index is just 0..n-1 in appearance order
        y_proc = [r["proc_sec"] for r in items]
        y_trans = [r["transport_sec"] for r in items]
        y_hand = [r["handover_sec"] for r in items]
        line_chart(None, y_proc, f"Control chart – Processing (Op {u})",
                   out_dir / f"cc_proc_op{u}.png", ylabel="seconds")
        line_chart(None, y_trans, f"Control chart – Transport (Op {u})",
                   out_dir / f"cc_transport_op{u}.png", ylabel="seconds")
        line_chart(None, y_hand, f"Control chart – Handover (Op {u})",
                   out_dir / f"cc_handover_op{u}.png", ylabel="seconds")

def make_stacked_medians(rows: List[Dict[str, Any]], out_path: pathlib.Path) -> None:
    by_uop = group_by(rows, "uniqueOpID")
    uops = sorted([u for u in by_uop.keys() if u is not None], key=str)
    trans_meds = []; hand_meds = []; proc_meds = []
    totals = []
    for u in uops:
        items = by_uop[u]
        tm = med_iqr([x["transport_sec"] for x in items])[0] or 0.0
        hm = med_iqr([x["handover_sec"] for x in items])[0] or 0.0
        pm = med_iqr([x["proc_sec"] for x in items])[0] or 0.0
        trans_meds.append(tm); hand_meds.append(hm); proc_meds.append(pm)
        totals.append(tm+hm+pm)
    # sort by total descending (Pareto-like)
    order = sorted(range(len(uops)), key=lambda i: totals[i], reverse=True)
    uops_sorted = [uops[i] for i in order]
    trans_sorted = [trans_meds[i] for i in order]
    hand_sorted  = [hand_meds[i]  for i in order]
    proc_sorted  = [proc_meds[i]  for i in order]
    stacked_bar_three(uops_sorted, trans_sorted, hand_sorted, proc_sorted,
                      "Stacked medians by operation (transport+handover+processing)",
                      out_path)

# ---------- optional OEE ----------

def compute_oee_per_order(orders: List[Dict[str, Any]], ideal: Optional[Dict[str, float]]) -> List[Dict[str, Any]]:
    """Returns list of dicts with per-order availability, performance, quality, oee."""
    if ideal is None:
        return []
    out = []
    for order in orders:
        pd0 = get_pd0(order)
        products = pd0.get("products", [])
        t_order = pd0.get("orderEndTs"); t_start = pd0.get("orderStartTs")
        if not (isinstance(t_order,(int,float)) and isinstance(t_start,(int,float)) and t_order > t_start):
            continue
        span = (t_order - t_start) / 1000.0  # seconds

        run_time = 0.0
        ideal_time = 0.0
        good_products = 0; total_products = 0

        for p in products:
            total_products += 1
            all_ok = True
            assembly = p.get("assembly", {})
            for _k, op in assembly.items():
                m = op.get("metrics", {}); d = op.get("data", {})
                s = m.get("startTsMs") or m.get("startTs")
                e = m.get("endTsMs") or m.get("endTs")
                if isinstance(s,(int,float)) and isinstance(e,(int,float)) and e >= s:
                    run_time += (e - s) / 1000.0
                key1 = str(d.get("uniqueOpID"))
                key2 = f"{d.get('machineID')}:{d.get('part')}"
                it = ideal.get(key1, ideal.get(key2))
                if isinstance(it,(int,float)):
                    ideal_time += float(it)
                if m.get("quality","OK") != "OK":
                    all_ok = False
            if all_ok:
                good_products += 1

        availability = (run_time / span) if (span > 0 and run_time > 0) else None
        performance  = (ideal_time / run_time) if (run_time > 0 and ideal_time > 0) else None
        quality      = (good_products / total_products) if total_products else None
        oee = (availability * performance * quality) if all(v is not None for v in (availability,performance,quality)) else None

        out.append({
            "order_id": pd0.get("orderId") or pd0.get("orderID") or "unknown",
            "availability": availability,
            "performance": performance,
            "quality": quality,
            "oee": oee
        })
    return out

def plot_oee(oee_rows: List[Dict[str, Any]], out_dir: pathlib.Path) -> None:
    if not oee_rows:
        return
    # order index on x
    availability = [r["availability"] for r in oee_rows]
    performance  = [r["performance"] for r in oee_rows]
    quality      = [r["quality"] for r in oee_rows]
    oee          = [r["oee"] for r in oee_rows]
    line_chart(None, availability, "Availability trend", out_dir / "trend_availability.png", ylabel="ratio")
    line_chart(None, performance,  "Performance trend",  out_dir / "trend_performance.png",  ylabel="ratio")
    line_chart(None, quality,      "Quality trend",      out_dir / "trend_quality.png",      ylabel="ratio")
    line_chart(None, oee,          "OEE trend",          out_dir / "trend_oee.png",          ylabel="ratio")

# ---------- orchestration ----------

def make_outputs(rows: List[Dict[str, Any]], orders: List[Dict[str, Any]],
                 out_dir: pathlib.Path, ideal: Optional[Dict[str, float]], cc_top_k: int) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    # CSV: flat breakdown
    per_op_csv = out_dir / "per_op_breakdown.csv"
    with per_op_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)

    # CSV: per-op stats
    by_uop = group_by(rows, "uniqueOpID")
    stats_csv = out_dir / "per_op_stats.csv"
    with stats_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["uniqueOpID","machineID","part",
                    "proc_med","proc_IQR",
                    "transport_med","transport_IQR",
                    "handover_med","handover_IQR",
                    "n"])
        for u, items in sorted(by_uop.items(), key=lambda kv: (str(kv[0]))):
            mach = items[0].get("machineID"); part = items[0].get("part")
            def m(key): return med_iqr([x[key] for x in items])[0] or 0.0
            def i(key): return med_iqr([x[key] for x in items])[1] or 0.0
            w.writerow([u, mach, part, m("proc_sec"), i("proc_sec"),
                        m("transport_sec"), i("transport_sec"),
                        m("handover_sec"), i("handover_sec"),
                        len(items)])

    # Baseline charts
    uops = sorted([u for u in by_uop.keys() if u is not None], key=str)
    proc_meds = [(med_iqr([x["proc_sec"] for x in by_uop[u]])[0] or 0.0) for u in uops]
    trans_meds = [(med_iqr([x["transport_sec"] for x in by_uop[u]])[0] or 0.0) for u in uops]
    hand_meds  = [(med_iqr([x["handover_sec"] for x in by_uop[u]])[0] or 0.0) for u in uops]
    if uops:
        bar_chart(uops, proc_meds, "Median processing time by operation", out_dir / "median_processing_by_op.png")
        bar_chart(uops, trans_meds, "Median transport time by operation", out_dir / "median_transport_by_op.png")
        bar_chart(uops, hand_meds,  "Median handover delay by operation", out_dir / "median_handover_by_op.png")
        make_stacked_medians(rows, out_dir / "stacked_medians_by_operation.png")

    # Order histograms & run charts
    by_order = group_by(rows, "order_id")
    t_orders, t_delays = [], []
    for oid, items in by_order.items():
        r0 = next((r for r in items if r.get("t_order_sec") is not None), None)
        if r0: t_orders.append(r0["t_order_sec"])
        r1 = next((r for r in items if r.get("t_delay_sec") is not None), None)
        if r1: t_delays.append(r1["t_delay_sec"])
    hist_chart(t_orders, "Distribution of total order time", out_dir / "hist_t_order.png")
    hist_chart(t_delays, "Distribution of delay to first operation", out_dir / "hist_t_delay.png")
    line_chart(None, t_orders, "Run chart – total order time", out_dir / "run_t_order.png")
    line_chart(None, t_delays, "Run chart – delay to first op", out_dir / "run_t_delay.png")

    # Control charts for top-K operations
    make_control_charts(rows, out_dir, top_k=cc_top_k)

    # Gantt for latest order
    make_gantt_latest_order(orders, out_dir / "gantt_latest_order.png")

    # Optional OEE trend
    oee_rows = compute_oee_per_order(orders, ideal)
    if oee_rows:
        (out_dir / "oee_per_order.json").write_text(json.dumps(oee_rows, ensure_ascii=False, indent=2), encoding="utf-8")
        plot_oee(oee_rows, out_dir)

    # Machine-readable JSON dump
    (out_dir / "per_op_rows.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=str, default=None, help="Path to finished_orders/ directory.")
    ap.add_argument("--out", type=str, default=None,
                    help="Name of subdirectory to create inside finished_orders/ for outputs.")
    ap.add_argument("--overwrite", action="store_true",
                    help="If the output directory exists, allow overwriting.")
    ap.add_argument("--ideal", type=str, default=None,
                    help="Path to ideal_times.json to compute OEE (keys: uniqueOpID or 'machineID:part', values in seconds).")
    ap.add_argument("--cc_top_k", type=int, default=6,
                    help="How many operations (by frequency) to include in control charts.")
    args = ap.parse_args()

    root = find_finished_orders_root(args.root)
    if args.out:
        out_dir = (root / args.out).resolve()
    else:
        ts = datetime.datetime.now().strftime("analysis_run_%Y%m%d_%H%M%S")
        out_dir = (root / ts).resolve()
    if out_dir.exists() and not args.overwrite:
        sys.exit(f"[ERR] Output directory already exists: {out_dir}\n"
                 f"Use --overwrite to reuse it, or pass a different --out name.")

    ideal = load_ideal_times(args.ideal)
    orders = load_orders(root)
    rows = flatten_rows(orders)

    print_op_stats(rows)
    make_outputs(rows, orders, out_dir, ideal, cc_top_k=args.cc_top_k)

    print("\nWrote analysis outputs to:")
    for p in sorted(out_dir.iterdir()):
        print(f" - {p}")

if __name__ == "__main__":
    main()

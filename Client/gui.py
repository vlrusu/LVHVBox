#!/usr/bin/env python3
# LV/HV monitor GUI (Pi 7" optimized; auto-connect, table-only, with currents)
# Tabs:
#  - HV (12 ch): get_vhv(ch), get_ihv(ch), trip_status(ch)
#  - 48V (6 ch): readMonV48(), readMonI48()   <-- bulk no-arg first, fallback per-channel
#  - Board:      pcb_temp(0), pico_current(0)
#
# Shows N/A until server is reachable; reconnects automatically.

import argparse
import queue
import threading
import time
from datetime import datetime
from typing import Dict, Optional, List, Any

import tkinter as tk
from tkinter import ttk
import tkinter.font as tkfont

from PowerSupplyServerConnection import PowerSupplyServerConnection

import json
import socket
hostname = socket.gethostname()

HV_CHANNELS = 12
MON48_CHANNELS = 6

# -------------------- parsing helpers --------------------

def parse_scalar(rv) -> Optional[float]:
    """Accept 12.3, [12.3], (12.3,), [(12.3,)], [[12.3]], JSON strings, etc. -> float or None."""
    try:
        if isinstance(rv, (int, float)):
            return float(rv)
        if isinstance(rv, (list, tuple)) and rv:
            first = rv[0]
            if isinstance(first, (int, float)):
                return float(first)
            if isinstance(first, (list, tuple)) and first:
                inner = first[0]
                if isinstance(inner, (int, float)):
                    return float(inner)
        if isinstance(rv, str):
            s = rv.strip()
            try:
                return float(s)
            except Exception:
                pass
            try:
                obj = json.loads(s)
                return parse_scalar(obj)
            except Exception:
                pass
    except Exception:
        pass
    return None

def _flatten_to_floats(x: Any) -> List[float]:
    """Flatten common container/encoding variants to a flat list of floats."""
    out: List[float] = []

    def _walk(v: Any):
        if isinstance(v, (int, float)):
            out.append(float(v))
        elif isinstance(v, (list, tuple)):
            for it in v:
                _walk(it)
        elif isinstance(v, dict):
            # accept {"values":[...]} or {"v":[...]} or {"data":[...]}
            for key in ("values", "v", "data"):
                if key in v:
                    _walk(v[key])
                    return
            for it in v.values():
                _walk(it)
        elif isinstance(v, str):
            s = v.strip()
            # JSON?
            try:
                obj = json.loads(s)
                _walk(obj)
                return
            except Exception:
                pass
            # CSV?
            if "," in s:
                for p in s.split(","):
                    p = p.strip()
                    try:
                        out.append(float(p))
                    except Exception:
                        pass
            else:
                try:
                    out.append(float(s))
                except Exception:
                    pass
        # ignore others

    _walk(x)
    return out

def parse_vector6(rv) -> Optional[List[float]]:
    """Return exactly 6 floats if possible; accept list/tuple/nested/JSON/CSV."""
    vals = _flatten_to_floats(rv)
    if len(vals) >= 6:
        return vals[:6]
    return None

def read_scalar(conn: PowerSupplyServerConnection, cmd: str, *args) -> Optional[float]:
    rv = conn.WriteRead(cmd, *args)
    return parse_scalar(rv)

def read_int(conn: PowerSupplyServerConnection, cmd: str, *args) -> Optional[int]:
    v = read_scalar(conn, cmd, *args)
    if v is None:
        return None
    try:
        return int(round(v))
    except Exception:
        return None

def read_vector6_noarg_then_fallback(conn: PowerSupplyServerConnection, cmd: str, n: int) -> Optional[List[float]]:
    """
    Try bulk no-arg: WriteRead(cmd) → 6 values.
    If that fails, fall back to per-channel: WriteRead(cmd, ch) for ch in [0..n-1].
    """
    # bulk first
    try:
        rv = conn.WriteRead(cmd)
        vec = parse_vector6(rv)
        if vec is not None:
            return vec
    except Exception:
        pass

    # fallback loop
    out: List[float] = []
    try:
        for ch in range(n):
            v = read_scalar(conn, cmd, ch)
            out.append(float(v) if v is not None else float("nan"))
        return out
    except Exception:
        return None

# -------------------- polling thread (auto-connect) --------------------

class Poller(threading.Thread):
    """
    Emits dicts like:
    {
      "timestamp": "...",
      "connected": bool,
      "hv":     {ch: {"V": float|None, "I": float|None, "trip": 0/1/None}},
      "mon48":  {ch: {"V": float|None, "I": float|None}},
      "single": {"pcb_temp": float|None, "pico_current": float|None},
    }
    """
    def __init__(self, host: str, port: int, header: str, interval: float, out_q: queue.Queue):
        super().__init__(daemon=True, name="HV-Poller")
        self.host, self.port, self.header = host, port, header
        self.interval = max(0.1, float(interval))
        self.q = out_q
        self.stop_evt = threading.Event()
        self.conn: Optional[PowerSupplyServerConnection] = None
        self.connected = False

    def _ensure_connected(self):
        """Try to (re)establish a connection and verify with a cheap probe."""
        if self.conn is None:
            self.conn = PowerSupplyServerConnection(self.host, self.port, self.header)
        try:
            if hasattr(self.conn, "Open"):
                self.conn.Open()
            _ = read_scalar(self.conn, "get_vhv", 0)  # probe
            self.connected = True
        except Exception:
            self.conn = None
            self.connected = False

    def _na_payload(self):
        ts = datetime.now().isoformat(timespec="seconds")
        return {
            "timestamp": ts,
            "connected": False,
            "hv": {ch: {"V": None, "I": None, "trip": None} for ch in range(HV_CHANNELS)},
            "mon48": {ch: {"V": None, "I": None} for ch in range(MON48_CHANNELS)},
            "single": {"pcb_temp": None, "pico_current": None},
        }

    def run(self):
        while not self.stop_evt.is_set():
            t0 = time.time()
            try:
                self._ensure_connected()

                if not self.connected:
                    self.q.put(self._na_payload())
                else:
                    hv: Dict[int, Dict[str, Optional[float]]] = {}
                    mon48: Dict[int, Dict[str, Optional[float]]] = {}

                    # HV: V + I + trip per channel
                    for ch in range(HV_CHANNELS):
                        v  = read_scalar(self.conn, "get_vhv", ch)
                        i  = read_scalar(self.conn, "get_ihv", ch)          # µA
                        tr = read_int(   self.conn, "trip_status", ch)      # 0/1
                        hv[ch] = {"V": v, "I": i, "trip": tr}

                    # 48V monitor: BULK both V and I first, fallback if needed
                    v48_all = read_vector6_noarg_then_fallback(self.conn, "readMonV48", MON48_CHANNELS)
                    i48_all = read_vector6_noarg_then_fallback(self.conn, "readMonI48", MON48_CHANNELS)

                    for ch in range(MON48_CHANNELS):
                        v48 = None if (v48_all is None or ch >= len(v48_all)) else v48_all[ch]
                        i48 = None if (i48_all is None or ch >= len(i48_all)) else i48_all[ch]
                        # If one of the bulks failed, optionally patch with per-channel fallback on that one only
                        if v48 is None:
                            v48 = read_scalar(self.conn, "readMonV48", ch)
                        if i48 is None:
                            i48 = read_scalar(self.conn, "readMonI48", ch)
                        mon48[ch] = {"V": v48, "I": i48}

                    # Singles (dummy arg 0 required)
                    pcb  = read_scalar(self.conn, "pcb_temp", 0)
                    pico = read_scalar(self.conn, "pico_current", 0)

                    self.q.put({
                        "timestamp": datetime.now().isoformat(timespec="seconds"),
                        "connected": True,
                        "hv": hv,
                        "mon48": mon48,
                        "single": {"pcb_temp": pcb, "pico_current": pico},
                    })

            except Exception:
                self.conn = None
                self.connected = False
                self.q.put(self._na_payload())

            rem = self.interval - (time.time() - t0)
            if rem > 0 and self.stop_evt.wait(rem):
                break

    def stop(self):
        self.stop_evt.set()

# -------------------- GUI (Pi 7" optimized) --------------------

class App(tk.Tk):
    def __init__(self, args):
        super().__init__()

        # Window & scaling for 800x480
        self.title("LV/HV Monitor")
        self.geometry("800x480+0+0")
        if not args.windowed:
            self.attributes("-fullscreen", True)
        self.bind("<Escape>", lambda e: self.destroy())

        base_size = args.font_size or 16  # good default for 7"
        self._apply_fonts(base_size)

        # Queue + poller
        self.q: queue.Queue = queue.Queue()
        self.poller = Poller(args.host, args.port, args.cmd_header, args.interval, self.q)
        self.poller.start()

        # Notebook tabs
        nb = ttk.Notebook(self); nb.pack(fill="both", expand=True)
        hv_tab  = ttk.Frame(nb); nb.add(hv_tab,  text="HV")
        m48_tab = ttk.Frame(nb); nb.add(m48_tab, text="48V")
        brd_tab = ttk.Frame(nb); nb.add(brd_tab, text="Board")

        # HV table: Channel | Voltage [V] | Current [µA] | Trip
        self.hv_tree, _ = self._make_table(
            parent=hv_tab,
            columns=[("ch","Channel","center",0.15),
                     ("v","Voltage [V]","e",0.40),
                     ("i","Current [µA]","e",0.25),
                     ("trip","Trip","center",0.20)],
            rows=HV_CHANNELS, iid_prefix="hv-", add_scroll=True,
        )
        self.hv_tree.tag_configure("ok",   foreground="green")
        self.hv_tree.tag_configure("trip", foreground="red")
        for ch in range(HV_CHANNELS):
            self.hv_tree.insert("", "end", iid=f"hv-{ch}", values=(ch, "—", "—", "—"))

        # 48V table: Channel | Voltage [V] | Current [A]
        self.m_tree, _ = self._make_table(
            parent=m48_tab,
            columns=[("ch","Channel","center",0.25),
                     ("v","Voltage [V]","e",0.40),
                     ("i","Current [A]","e",0.35)],
            rows=MON48_CHANNELS, iid_prefix="m48-", add_scroll=True,
        )
        for ch in range(MON48_CHANNELS):
            self.m_tree.insert("", "end", iid=f"m48-{ch}", values=(ch, "—", "—"))

        # --- Add a blank spacer row ---
        self.m_tree.insert("", "end", iid="m48-spacer", values=("", "", ""))

            
        # Add a total power row
        self.m_tree.insert("", "end", iid="m48-total", values=("Power [W]", "—", "—"))
        self.m_tree.tag_configure("total", foreground="blue", font=("TkDefaultFont",  base_size + 2, "bold"))
            
        # Board table (3 rows): Name | Value
        self.s_tree, _ = self._make_table(
            parent=brd_tab,
            columns=[("name","Name","w",0.55),
                     ("val","Value","e",0.45)],
            rows=3, iid_prefix="s-", add_scroll=False,
        )
        self.hostname = socket.gethostname()
        self.s_tree.insert("", "end", iid="s-machine", values=("Machine", self.hostname))
        self.s_tree.insert("", "end", iid="s-pcb",    values=("PCB Temp [°C]", "—"))
        self.s_tree.insert("", "end", iid="s-pico",   values=("Pico Current [A]", "—"))
        
        self.after(100, self._drain_queue)

    # ---------- styling & table helpers ----------

    def _apply_fonts(self, base_size: int):
        default_font = tkfont.nametofont("TkDefaultFont")
        text_font    = tkfont.nametofont("TkTextFont")
        heading_font = tkfont.nametofont("TkHeadingFont")
        default_font.configure(size=base_size)
        text_font.configure(size=base_size)
        heading_font.configure(size=base_size + 2)

        style = ttk.Style(self)
        style.configure("Treeview", rowheight=int(base_size * 2.0))
        style.configure("Treeview.Heading", font=heading_font)
        style.configure("TNotebook.Tab", padding=(12, 6, 12, 6), font=heading_font)

    def _make_table(self, parent, columns, rows, iid_prefix, add_scroll: bool):
        frame = ttk.Frame(parent); frame.pack(fill="both", expand=True, padx=8, pady=8)
        tree = ttk.Treeview(frame, columns=[c[0] for c in columns], show="headings", height=rows)

        def resize_cols(event=None):
            w = tree.winfo_width() or 1
            for i, (cid, _heading, anchor, rel) in enumerate(columns):
                tree.column(cid, width=max(60, int(w * rel)), anchor=anchor)

        for cid, heading, anchor, _rel in columns:
            tree.heading(cid, text=heading)
            tree.column(cid, anchor=anchor, stretch=True)

        yscroll = None
        if add_scroll:
            yscroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
            tree.configure(yscrollcommand=yscroll.set)
            yscroll.pack(side="right", fill="y")

        tree.pack(side="left", fill="both", expand=True)
        tree.bind("<Configure>", resize_cols)
        return tree, yscroll

    # ---------- update pump ----------

    def _drain_queue(self):
        try:
            while True:
                item = self.q.get_nowait()
                self._update(item)
        except queue.Empty:
            pass
        self.after(100, self._drain_queue)

    def _update(self, item: dict):
        hv = item.get("hv", {})
        mon48 = item.get("mon48", {})
        singles = item.get("single", {})

        # HV rows
        for ch in range(HV_CHANNELS):
            row  = hv.get(ch, {})
            v    = row.get("V")
            i    = row.get("I")
            trip = row.get("trip")

            v_txt = f"{v:.3f}" if isinstance(v, (int, float)) else "N/A"
            i_txt = f"{i:.3f}" if isinstance(i, (int, float)) else "N/A"

            if trip == 1:
                trip_txt = "TRIPPED"; tags = ("trip",)
            elif trip == 0:
                trip_txt = "OK";       tags = ("ok",)
            else:
                trip_txt = "N/A";      tags = ()

            self.hv_tree.item(f"hv-{ch}", values=(ch, v_txt, i_txt, trip_txt), tags=tags)

        # 48V rows
        for ch in range(MON48_CHANNELS):
            row = mon48.get(ch, {})
            v48 = row.get("V")
            i48 = row.get("I")
            v48_txt = f"{v48:.3f}" if isinstance(v48, (int, float)) else "N/A"
            i48_txt = f"{i48:.3f}" if isinstance(i48, (int, float)) else "N/A"
            self.m_tree.item(f"m48-{ch}", values=(ch, v48_txt, i48_txt))

        # --- Compute total power ---
        try:
            total_power = 0.0
            for row in mon48.values():
                v = row.get("V")
                i = row.get("I")
                if isinstance(v, (int, float)) and isinstance(i, (int, float)):
                    total_power += v * i
                power_txt = f"{total_power:.1f}" if total_power > 0 else "0.0"
        except Exception:
            power_txt = "N/A"

        self.m_tree.item("m48-total", values=("Power [W]", power_txt, ""), tags=("total",))
            
        # Singles
        pcb  = singles.get("pcb_temp")
        pico = singles.get("pico_current")
        pcb_txt  = f"{pcb:.2f}"  if isinstance(pcb, (int, float))  else "N/A"
        pico_txt = f"{pico:.3f}" if isinstance(pico, (int, float)) else "N/A"
        self.s_tree.item("s-pcb",  values=("PCB Temp [°C]",  pcb_txt))
        self.s_tree.item("s-pico", values=("Pico Current [A]", pico_txt))

    def destroy(self):
        try:
            if hasattr(self, "poller") and self.poller:
                self.poller.stop()
                self.poller.join(timeout=1.5)
        finally:
            super().destroy()

# -------------------- CLI --------------------

def parse_args():
    p = argparse.ArgumentParser(
        description="Pi 7\" LV/HV Monitor (auto-connect): HV V/I/trip, 48V V/I, pcb_temp(0), pico_current(0)"
    )
    p.add_argument("--host", default="localhost")
    p.add_argument("--port", type=int, default=12000)
    p.add_argument("--cmd-header", default="/etc/mu2e-tracker-lvhv-tools/commands.h")
    p.add_argument("--interval", type=float, default=3, help="Polling interval seconds")
    p.add_argument("--windowed", action="store_true", help="Run in a window instead of fullscreen")
    p.add_argument("--font-size", type=int, default=None, help="Override base font size (default 16)")
    return p.parse_args()

def main():
    args = parse_args()
    app = App(args)
    app.mainloop()

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# LV/HV monitor GUI (Pi 7") — MessagingConnection, status bar, optional HV, optional Power tab.
# Defaults: HV monitoring ON, Power tab ON.
# Flags:
#   --no-hv     : disable HV queries and hide HV tab
#   --no-power  : hide Power tab (monitoring still runs)
#
# Tabs (by default):
#   - HV (12 ch): get_vhv(ch), get_ihv(ch), trip_status(ch)
#   - 48V (6 ch): readMonV48(6), readMonI48(6)   (bulk first, then per-channel fallback)
#   - Power:     6x (On N / Off N) + All On / All Off (each uses its own MessagingConnection)
#   - Board:     pcb_temp(0), pico_current(0)
#
# Connection model:
#   - No fragile probe. We assume the socket is up if it opens.
#   - Individual reads may fail -> they show as N/A and set "partial" status.
#   - Poller keeps a single connection for reads; Power buttons use separate short-lived connections.

import argparse, queue, threading, time
from datetime import datetime
from typing import Dict, Optional, List, Any

import tkinter as tk
from tkinter import ttk
import tkinter.font as tkfont

import json, socket, ctypes, math, os
from MessagingConnection import MessagingConnection

HV_CHANNELS = 12
MON48_CHANNELS = 6
COMMANDS_H_PATH = "/etc/mu2e-tracker-lvhv-tools/commands.h"

_command_dict: Optional[dict] = None

# ---------- command map ----------
def read_commands(path: str = COMMANDS_H_PATH) -> dict:
    d = {}
    with open(path, "r") as f:
        for line in f:
            parts = line.split()
            if len(parts) >= 3:
                d[parts[1]] = int(parts[2])
    return d

def command_map() -> dict:
    global _command_dict
    if _command_dict is None:
        if not os.path.exists(COMMANDS_H_PATH):
            raise FileNotFoundError(f"Cannot find commands.h at {COMMANDS_H_PATH}")
        _command_dict = read_commands(COMMANDS_H_PATH)
    return _command_dict

# ---------- parsing utils ----------
def is_valid_num(x): return isinstance(x, (int, float)) and math.isfinite(x)
def fmt_num(x, digits): return f"{x:.{digits}f}" if is_valid_num(x) else "N/A"

def _flatten_to_floats(x: Any) -> List[float]:
    out: List[float] = []
    def _walk(v: Any):
        if isinstance(v, (int, float)):
            out.append(float(v))
        elif isinstance(v, (list, tuple)):
            for it in v: _walk(it)
        elif isinstance(v, dict):
            for key in ("values", "v", "data"):
                if key in v: _walk(v[key]); return
            for it in v.values(): _walk(it)
        elif isinstance(v, str):
            s = v.strip()
            try:
                obj = json.loads(s); _walk(obj); return
            except Exception: pass
            if "," in s:
                for p in s.split(","):
                    try: out.append(float(p.strip()))
                    except Exception: pass
            else:
                try: out.append(float(s))
                except Exception: pass
    _walk(x); return out

def parse_vector6(rv) -> Optional[List[float]]:
    vals = _flatten_to_floats(rv)
    return vals[:6] if len(vals) >= 6 else None

# ---------- Messaging read helpers ----------
def send_msg_and_recv_scalar(conn: MessagingConnection, cmd_name: str, type_key: str,
                             channel: int = 0, val: float = 0.0) -> Optional[float]:
    cmap = command_map()
    c_cmd = ctypes.c_uint(cmap["COMMAND_" + cmd_name])
    c_typ = ctypes.c_uint(cmap["TYPE_" + type_key])
    c_chn = ctypes.c_char(channel)
    c_val = ctypes.c_float(float(val))
    conn.send_message(c_cmd, c_typ, c_chn, c_val)
    blocks = conn.recv_message()
    try: return float(blocks[0][0])
    except Exception: return None

def send_msg_and_recv_vector6(conn: MessagingConnection, cmd_name: str, type_key: str) -> Optional[List[float]]:
    cmap = command_map()
    c_cmd = ctypes.c_uint(cmap["COMMAND_" + cmd_name])
    c_typ = ctypes.c_uint(cmap["TYPE_" + type_key])
    c_chn = ctypes.c_char(6)
    c_val = ctypes.c_float(0.0)
    conn.send_message(c_cmd, c_typ, c_chn, c_val)
    blocks = conn.recv_message()
    return parse_vector6(blocks)

# ---------- Poller ----------
class Poller(threading.Thread):
    def __init__(self, host: str, port: int, interval: float, out_q: queue.Queue, hv_enabled: bool):
        super().__init__(daemon=True, name="LVHV-Poller")
        self.host, self.port = host, port
        self.interval = max(0.1, float(interval))
        self.q = out_q
        self.stop_evt = threading.Event()
        self.conn: Optional[MessagingConnection] = None
        self.hv_enabled = hv_enabled

    def _ensure_connected(self):
        if self.conn is None:
            command_map()  # load once
            self.conn = MessagingConnection(self.host, self.port)

    def _na_payload(self):
        ts = datetime.now().isoformat(timespec="seconds")
        empty_hv = {} if not self.hv_enabled else {ch: {"V": None, "I": None, "trip": None} for ch in range(HV_CHANNELS)}
        return {
            "timestamp": ts, "connected": False, "partial": False,
            "hv": empty_hv,
            "mon48": {ch: {"V": None, "I": None} for ch in range(MON48_CHANNELS)},
            "single": {"pcb_temp": None, "pico_current": None},
        }

    def run(self):
        while not self.stop_evt.is_set():
            t0 = time.time()
            try:
                self._ensure_connected()

                hv: Dict[int, Dict[str, Optional[float]]] = {}
                mon48: Dict[int, Dict[str, Optional[float]]] = {}
                partial = False

                # HV (optional)
                if self.hv_enabled:
                    for ch in range(HV_CHANNELS):
                        try: v = send_msg_and_recv_scalar(self.conn, "get_vhv", "pico", ch, 0.0)
                        except Exception: v = None
                        try: i = send_msg_and_recv_scalar(self.conn, "get_ihv", "pico", ch, 0.0)
                        except Exception: i = None
                        try:
                            trf = send_msg_and_recv_scalar(self.conn, "trip_status", "pico", ch, 0.0)
                            tr = int(round(trf)) if is_valid_num(trf) else None
                        except Exception:
                            tr = None
                        if v is None or i is None or tr is None: partial = True
                        hv[ch] = {"V": v, "I": i, "trip": tr}

                # 48V bulk → fallback
                try: v48_all = send_msg_and_recv_vector6(self.conn, "readMonV48", "lv")
                except Exception: v48_all = None
                try: i48_all = send_msg_and_recv_vector6(self.conn, "readMonI48", "lv")
                except Exception: i48_all = None

                for ch in range(MON48_CHANNELS):
                    v48 = (v48_all[ch] if (v48_all and ch < len(v48_all) and is_valid_num(v48_all[ch])) else None)
                    i48 = (i48_all[ch] if (i48_all and ch < len(i48_all) and is_valid_num(i48_all[ch])) else None)
                    if v48 is None:
                        try: v48 = send_msg_and_recv_scalar(self.conn, "readMonV48", "lv", ch, 0.0)
                        except Exception: v48 = None
                    if i48 is None:
                        try: i48 = send_msg_and_recv_scalar(self.conn, "readMonI48", "lv", ch, 0.0)
                        except Exception: i48 = None
                    if v48 is None or i48 is None: partial = True
                    mon48[ch] = {"V": v48, "I": i48}

                # singles
                try: pcb = send_msg_and_recv_scalar(self.conn, "pcb_temp", "pico", 0, 0.0)
                except Exception: pcb = None
                try: pico = send_msg_and_recv_scalar(self.conn, "pico_current", "pico", 0, 0.0)
                except Exception: pico = None
                if pcb is None or pico is None: partial = True

                self.q.put({
                    "timestamp": datetime.now().isoformat(timespec="seconds"),
                    "connected": True, "partial": partial,
                    "hv": hv, "mon48": mon48, "single": {"pcb_temp": pcb, "pico_current": pico},
                })

            except Exception:
                # socket/protocol failure
                self.conn = None
                self.q.put(self._na_payload())

            rem = self.interval - (time.time() - t0)
            if rem > 0 and self.stop_evt.wait(rem): break

    def stop(self):
        self.stop_evt.set()
        try:
            if self.conn: self.conn.close()
        except Exception: pass

# ---------- GUI ----------
class App(tk.Tk):
    def __init__(self, args):
        super().__init__()
        self.args = args
        self.hv_enabled = not args.no_hv
        self.power_enabled = not args.no_power

        # Window (Pi 7")
        self.title("LV/HV Monitor")
        self.geometry("800x480+0+0")
        if not args.windowed: self.attributes("-fullscreen", True)
        self.bind("<Escape>", lambda e: self.destroy())

        base_size = args.font_size or 16
        self._apply_fonts(base_size)

        # Queue + poller
        self.q = queue.Queue()
        self.poller = Poller(args.host, args.port, args.interval, self.q, hv_enabled=self.hv_enabled)
        self.poller.start()

        # Status bar
        top = ttk.Frame(self); top.pack(fill="x", padx=6, pady=4)
        self.status_var = tk.StringVar(value="Connecting…")
        self.status_lbl = ttk.Label(top, textvariable=self.status_var,
                                    font=("TkDefaultFont", base_size), foreground="orange")
        self.status_lbl.pack(side="left")

        # Notebook
        nb = ttk.Notebook(self); nb.pack(fill="both", expand=True)

        # HV tab
        if self.hv_enabled:
            hv_tab = ttk.Frame(nb); nb.add(hv_tab, text="HV")
            self.hv_tree, _ = self._make_table(
                parent=hv_tab,
                columns=[("ch","Channel","center",0.15),
                         ("v","Voltage [V]","e",0.40),
                         ("i","Current [µA]","e",0.25),
                         ("trip","Trip","center",0.20)],
                rows=HV_CHANNELS, iid_prefix="hv-", add_scroll=True,
            )
            self.hv_tree.tag_configure("ok", foreground="green")
            self.hv_tree.tag_configure("trip", foreground="red")
            for ch in range(HV_CHANNELS):
                self.hv_tree.insert("", "end", iid=f"hv-{ch}", values=(ch, "—", "—", "—"))

        # 48V tab
        m48_tab = ttk.Frame(nb); nb.add(m48_tab, text="48V")
        self.m_tree, _ = self._make_table(
            parent=m48_tab,
            columns=[("ch","Channel","center",0.25),
                     ("v","Voltage [V]","e",0.40),
                     ("i","Current [A]","e",0.35)],
            rows=MON48_CHANNELS + 2, iid_prefix="m48-", add_scroll=True,
        )
        for ch in range(MON48_CHANNELS):
            self.m_tree.insert("", "end", iid=f"m48-{ch}", values=(ch, "—", "—"))
        self.m_tree.insert("", "end", iid="m48-spacer", values=("", "", ""))
        self.m_tree.insert("", "end", iid="m48-total", values=("Total Power [W]", "—", "—"))
        self.m_tree.tag_configure("total", foreground="blue", font=("TkDefaultFont", base_size + 2, "bold"))

        # Power tab (optional)
        if self.power_enabled:
            power_tab = ttk.Frame(nb); nb.add(power_tab, text="Power")
            ctrl = ttk.Frame(power_tab); ctrl.pack(fill="both", expand=True, padx=16, pady=16)
            self.power_status = tk.StringVar(value="Ready")
            btn_style = ttk.Style(self)
            btn_style.configure("Power.TButton", padding=(12, 4), font=("TkDefaultFont", base_size + 2, "bold"))
            for idx in range(6):
                row = ttk.Frame(ctrl); row.pack(pady=4)
                ttk.Button(row, text=f"On {idx}",  style="Power.TButton",
                           command=lambda i=idx: self._call_power_method("powerOn",  i)).pack(side="left", padx=10)
                ttk.Button(row, text=f"Off {idx}", style="Power.TButton",
                           command=lambda i=idx: self._call_power_method("powerOff", i)).pack(side="left", padx=10)
            row_all = ttk.Frame(ctrl); row_all.pack(pady=8)
            ttk.Button(row_all, text="All On",  style="Power.TButton",
                       command=lambda: self._call_power_method("powerOn",  -1)).pack(side="left", padx=10)
            ttk.Button(row_all, text="All Off", style="Power.TButton",
                       command=lambda: self._call_power_method("powerOff", -1)).pack(side="left", padx=10)
            row_status = ttk.Frame(ctrl); row_status.pack(pady=6)
            ttk.Label(row_status, textvariable=self.power_status,
                      font=("TkDefaultFont", base_size + 2)).pack()

        # Board tab
        brd_tab = ttk.Frame(nb); nb.add(brd_tab, text="Board")
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

    # --- UI helpers ---
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
            tree.configure(yscrollcommand=yscroll.set); yscroll.pack(side="right", fill="y")
        tree.pack(side="left", fill="both", expand=True)
        tree.bind("<Configure>", resize_cols)
        return tree, yscroll

    # --- Power (dedicated connection, synchronous) ---
    def _set_power_status(self, msg: str):
        if hasattr(self, "power_status"): self.power_status.set(msg)

    def _call_power_method(self, method_name: str, idx: int):
        self._set_power_status(f"{method_name} {idx}…")
        conn = None
        try:
            cmap = command_map()
            cmd_id = cmap["COMMAND_" + method_name]
            type_id = cmap["TYPE_lv"]
            conn = MessagingConnection(self.args.host, self.args.port)

            def send_one(channel: int, val: float = 0.0):
                c_cmd = ctypes.c_uint(cmd_id)
                c_typ = ctypes.c_uint(type_id)
                c_chn = ctypes.c_char(channel)
                c_val = ctypes.c_float(float(val))
                conn.send_message(c_cmd, c_typ, c_chn, c_val)
                _ = conn.recv_message()

            if idx == -1:
                if method_name == "powerOff":
                    send_one(6, 0.0)  # special "all off"
                else:
                    for ch in range(MON48_CHANNELS):
                        send_one(ch, 0.0); time.sleep(0.05)
            else:
                send_one(int(idx), 0.0)

            self._set_power_status(f"{method_name} {idx} OK")
        except Exception as e:
            self._set_power_status(f"{method_name} {idx} failed: {e}")
        finally:
            try:
                if conn: conn.close()
            except Exception: pass

    # --- update pump ---
    def _drain_queue(self):
        try:
            while True:
                item = self.q.get_nowait()
                self._update(item)
        except queue.Empty:
            pass
        self.after(100, self._drain_queue)

    def _update(self, item: dict):
        connected = item.get("connected", False)
        partial   = item.get("partial", False)
        if not connected:
            self.status_var.set("🔴 Disconnected"); self.status_lbl.configure(foreground="red")
        else:
            if partial:
                self.status_var.set("🟡 Connected (partial data)"); self.status_lbl.configure(foreground="goldenrod")
            else:
                self.status_var.set("🟢 Connected"); self.status_lbl.configure(foreground="darkgreen")

        # HV
        if self.hv_enabled:
            hv = item.get("hv", {})
            for ch in range(HV_CHANNELS):
                row = hv.get(ch, {})
                v, i, trip = row.get("V"), row.get("I"), row.get("trip")
                v_txt, i_txt = fmt_num(v, 3), fmt_num(i, 3)
                if trip == 1: trip_txt, tags = "TRIPPED", ("trip",)
                elif trip == 0: trip_txt, tags = "OK", ("ok",)
                else: trip_txt, tags = "N/A", ()
                self.hv_tree.item(f"hv-{ch}", values=(ch, v_txt, i_txt, trip_txt), tags=tags)

        # 48V
        mon48 = item.get("mon48", {})
        total_power = 0.0
        for ch in range(MON48_CHANNELS):
            row = mon48.get(ch, {})
            v48, i48 = row.get("V"), row.get("I")
            self.m_tree.item(f"m48-{ch}", values=(ch, fmt_num(v48,3), fmt_num(i48,3)))
            if is_valid_num(v48) and is_valid_num(i48): total_power += v48 * i48
        self.m_tree.item("m48-total", values=("Total Power [W]", f"{total_power:.1f}", ""), tags=("total",))

        # Board
        singles = item.get("single", {})
        pcb, pico = singles.get("pcb_temp"), singles.get("pico_current")
        self.s_tree.item("s-pcb",  values=("PCB Temp [°C]",  fmt_num(pcb,2)))
        self.s_tree.item("s-pico", values=("Pico Current [A]", fmt_num(pico,3)))

    def destroy(self):
        try:
            if hasattr(self, "poller") and self.poller:
                self.poller.stop(); self.poller.join(timeout=1.5)
        finally:
            super().destroy()

# ---------- CLI ----------
def parse_args():
    p = argparse.ArgumentParser(description="Pi 7\" LV/HV Monitor (MessagingConnection)")
    p.add_argument("--host", default="localhost")
    p.add_argument("--port", type=int, default=12000)
    p.add_argument("--interval", type=float, default=3, help="Polling interval seconds")
    p.add_argument("--windowed", action="store_true", help="Run in a window instead of fullscreen")
    p.add_argument("--font-size", type=int, default=None, help="Override base font size (default 16)")
    p.add_argument("--no-hv", action="store_true", help="Disable HV monitoring and hide the HV tab")
    p.add_argument("--no-power", action="store_true", help="Hide the Power tab")
    return p.parse_args()

def main():
    args = parse_args()
    app = App(args)
    app.mainloop()

if __name__ == "__main__":
    main()

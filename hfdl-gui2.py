import os
import time
import math
import threading
import queue
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import tkinter as tk
from tkinter import ttk, filedialog

BASE_URL_PREFIX = "https://huggingface.co/"
BASE_URL_SUFFIX = "/tree/main"

# ---------------------------
# Helpers for UI-safe logging
# ---------------------------
def human_bytes(n):
    if n is None:
        return "?"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}"
        n /= 1024

def human_time(seconds):
    if seconds is None or math.isinf(seconds):
        return "—"
    seconds = int(seconds)
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h: return f"{h}h {m}m {s}s"
    if m: return f"{m}m {s}s"
    return f"{s}s"

# ---------------------------
# Worker thread
# ---------------------------
class Downloader(threading.Thread):
    def __init__(self, model_path, output_dir, ui_queue, cancel_event):
        super().__init__(daemon=True)
        self.model_path = model_path.strip().strip("/")
        self.output_dir = output_dir
        self.ui_queue = ui_queue
        self.cancel_event = cancel_event
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "hf-downloader-gui/1.0"})

    def send(self, kind, **payload):
        self.ui_queue.put((kind, payload))

    def run(self):
        try:
            if self.cancel_event.is_set():
                return
            base_url = f"{BASE_URL_PREFIX}{self.model_path}{BASE_URL_SUFFIX}"
            model_name = self.model_path.split('/')[-1]
            output_subdir = os.path.join(self.output_dir, model_name)
            os.makedirs(output_subdir, exist_ok=True)

            # 1) Discover files from the model "tree"
            self.send("status", text="Fetching file list…")
            resp = self.session.get(base_url, timeout=30)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.content, 'html.parser')

            links = soup.find_all('a', href=True)
            # Keep common large file types; also many HF links end in ?download=true
            exts = ('.safetensors', '.json', '.model', '.bin')
            download_links = []
            for a in links:
                href = a['href']
                if href.endswith("?download=true") or href.endswith(exts):
                    download_links.append(href)

            if not download_links:
                self.send("finished", ok=False, message="No downloadable files were found on this page.")
                return

            base_domain = urlparse(base_url).scheme + '://' + urlparse(base_url).netloc
            full_urls = [urljoin(base_domain, link) for link in download_links]
            file_names = [os.path.basename(link.split("?")[0]) for link in download_links]

            # 2) HEAD all files to get sizes (for overall progress/ETA)
            sizes = []
            total_size = 0
            self.send("status", text="Probing file sizes…")
            for url in full_urls:
                if self.cancel_event.is_set(): 
                    self.send("finished", ok=False, message="Canceled.")
                    return
                size = None
                try:
                    # some endpoints block HEAD; fall back to GET with stream and no read
                    h = self.session.head(url, allow_redirects=True, timeout=20)
                    if "content-length" in h.headers:
                        size = int(h.headers["content-length"])
                    elif h.status_code >= 400:
                        # try GET for content-length
                        g = self.session.get(url, stream=True, timeout=20)
                        size = int(g.headers.get("content-length") or 0) or None
                        g.close()
                except Exception:
                    size = None
                sizes.append(size)
                if size:
                    total_size += size

            self.send("prepare_overall", total=total_size or 0, count=len(full_urls))
            downloaded_total = 0
            t0 = time.time()

            # 3) Download each file sequentially so progress is clean & simple
            for idx, (url, name, fsize) in enumerate(zip(full_urls, file_names, sizes), start=1):
                if self.cancel_event.is_set():
                    self.send("finished", ok=False, message="Canceled.")
                    return

                out_path = os.path.join(output_subdir, name)
                self.send("file_start", index=idx, name=name, size=fsize or 0)

                try:
                    with self.session.get(url, stream=True, timeout=60) as r:
                        r.raise_for_status()
                        # Prefer response header size if HEAD failed
                        r_size = int(r.headers.get("content-length") or 0) or fsize or 0
                        written = 0
                        last_update = 0
                        chunk = 1024 * 1024  # 1 MB

                        with open(out_path, "wb") as fh:
                            for part in r.iter_content(chunk_size=chunk):
                                if self.cancel_event.is_set():
                                    self.send("finished", ok=False, message="Canceled.")
                                    return
                                if not part:
                                    continue
                                fh.write(part)
                                written += len(part)
                                downloaded_total += len(part)

                                # throttle UI updates to ~10/s
                                now = time.time()
                                if now - last_update > 0.1:
                                    elapsed = now - t0
                                    speed = downloaded_total / elapsed if elapsed > 0 else 0
                                    remaining = (total_size - downloaded_total) / speed if speed and total_size else None
                                    self.send(
                                        "progress",
                                        file_written=written,
                                        file_total=r_size,
                                        overall_written=downloaded_total,
                                        overall_total=total_size,
                                        speed=speed,
                                        eta=remaining
                                    )
                                    last_update = now

                    self.send("log", text=f"✔ Downloaded {name} ({human_bytes(written)}).")
                except Exception as e:
                    self.send("log", text=f"✖ Failed {name}: {e}")

            self.send("finished", ok=True, message="All done.")
        except Exception as e:
            self.send("finished", ok=False, message=f"Error: {e}")

# ---------------------------
# GUI
# ---------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("HF Raw Model Downloader (with progress)")
        self.geometry("600x440")

        self.model_var = tk.StringVar()
        self.outdir_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Idle")
        self.file_label_var = tk.StringVar(value="No file")
        self.speed_eta_var = tk.StringVar(value="")

        # Input row
        frm_in = ttk.Frame(self, padding=8)
        frm_in.pack(fill="x")
        ttk.Label(frm_in, text="Model Path (e.g. meta-llama/Llama-2-7b-hf):").pack(anchor="w")
        ttk.Entry(frm_in, textvariable=self.model_var).pack(fill="x")

        frm_out = ttk.Frame(self, padding=(8, 0, 8, 8))
        frm_out.pack(fill="x")
        ttk.Label(frm_out, text="Output Directory:").pack(anchor="w")
        out_row = ttk.Frame(frm_out)
        out_row.pack(fill="x")
        ttk.Entry(out_row, textvariable=self.outdir_var).pack(side="left", fill="x", expand=True)
        ttk.Button(out_row, text="Browse", command=self.browse).pack(side="left", padx=6)

        # Controls
        frm_btns = ttk.Frame(self, padding=(8, 0))
        frm_btns.pack(fill="x")
        self.btn_download = ttk.Button(frm_btns, text="Download", command=self.start)
        self.btn_download.pack(side="left")
        self.btn_cancel = ttk.Button(frm_btns, text="Cancel", command=self.cancel, state="disabled")
        self.btn_cancel.pack(side="left", padx=6)

        # Current file & per-file bar
        frm_file = ttk.Frame(self, padding=(8, 8, 8, 0))
        frm_file.pack(fill="x")
        ttk.Label(frm_file, textvariable=self.file_label_var).pack(anchor="w")
        self.file_bar = ttk.Progressbar(frm_file, length=560, mode="determinate")
        self.file_bar.pack(fill="x")

        # Overall bar
        frm_overall = ttk.Frame(self, padding=(8, 8, 8, 0))
        frm_overall.pack(fill="x")
        ttk.Label(frm_overall, text="Overall Progress").pack(anchor="w")
        self.overall_bar = ttk.Progressbar(frm_overall, length=560, mode="determinate")
        self.overall_bar.pack(fill="x")
        ttk.Label(frm_overall, textvariable=self.speed_eta_var).pack(anchor="w")

        # Status + log
        frm_status = ttk.Frame(self, padding=8)
        frm_status.pack(fill="both", expand=True)
        ttk.Label(frm_status, textvariable=self.status_var).pack(anchor="w")
        self.log = tk.Text(frm_status, height=10, wrap="word")
        self.log.pack(fill="both", expand=True)

        self.queue = queue.Queue()
        self.cancel_event = threading.Event()
        self.worker = None

        # Poll UI queue
        self.after(100, self.on_pulse)

    def browse(self):
        d = filedialog.askdirectory()
        if d:
            self.outdir_var.set(d)

    def start(self):
        model = self.model_var.get().strip()
        outdir = self.outdir_var.get().strip()
        if not model or not outdir:
            self.status_var.set("Please fill in both fields.")
            return

        self.file_label_var.set("Preparing…")
        self.file_bar["value"] = 0
        self.file_bar["maximum"] = 1
        self.overall_bar["value"] = 0
        self.overall_bar["maximum"] = 1
        self.speed_eta_var.set("")
        self.log.delete("1.0", "end")
        self.status_var.set("Starting…")

        self.cancel_event.clear()
        self.worker = Downloader(model, outdir, self.queue, self.cancel_event)
        self.worker.start()
        self.btn_download["state"] = "disabled"
        self.btn_cancel["state"] = "normal"

    def cancel(self):
        self.cancel_event.set()
        self.status_var.set("Canceling…")

    def append_log(self, text):
        self.log.insert("end", text + "\n")
        self.log.see("end")

    def on_pulse(self):
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind == "status":
                    self.status_var.set(payload["text"])
                elif kind == "prepare_overall":
                    total = payload.get("total", 0)
                    count = payload.get("count", 0)
                    self.overall_bar["maximum"] = max(total, 1)
                    self.overall_bar["value"] = 0
                    self.append_log(f"Found {count} files. Total size: {human_bytes(total) if total else 'unknown'}")
                elif kind == "file_start":
                    idx = payload["index"]
                    name = payload["name"]
                    size = payload.get("size", 0)
                    self.file_label_var.set(f"File {idx}: {name} ({human_bytes(size) if size else 'size unknown'})")
                    self.file_bar["maximum"] = max(size, 1)
                    self.file_bar["value"] = 0
                elif kind == "progress":
                    fw = payload.get("file_written", 0)
                    ft = payload.get("file_total", 0)
                    ow = payload.get("overall_written", 0)
                    ot = payload.get("overall_total", 0)
                    speed = payload.get("speed", 0.0)
                    eta = payload.get("eta", None)

                    # Update bars
                    self.file_bar["maximum"] = max(ft, 1)
                    self.file_bar["value"] = min(fw, ft) if ft else fw
                    self.overall_bar["maximum"] = max(ot, 1)
                    self.overall_bar["value"] = min(ow, ot) if ot else ow

                    # Speed/ETA
                    sp = f"{human_bytes(speed)}/s" if speed else "—"
                    self.speed_eta_var.set(f"Speed: {sp}   ETA: {human_time(eta)}")
                elif kind == "log":
                    self.append_log(payload["text"])
                elif kind == "finished":
                    ok = payload.get("ok", False)
                    msg = payload.get("message", "")
                    self.status_var.set(msg)
                    self.btn_download["state"] = "normal"
                    self.btn_cancel["state"] = "disabled"
        except queue.Empty:
            pass
        self.after(100, self.on_pulse)

if __name__ == "__main__":
    App().mainloop()

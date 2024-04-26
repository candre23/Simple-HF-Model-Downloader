import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from concurrent.futures import ThreadPoolExecutor
import tkinter as tk
from tkinter import filedialog, messagebox

BASE_URL_PREFIX = "https://huggingface.co/"
BASE_URL_SUFFIX = "/tree/main"

def download_file(full_url, file_name, output_dir):
    file_path = os.path.join(output_dir, file_name)
    try:
        with requests.get(full_url, stream=True) as response:
            response.raise_for_status()
            with open(file_path, 'wb') as file:
                for chunk in response.iter_content(chunk_size=1024):
                    file.write(chunk)
            print(f'Downloaded: {file_name} to {output_dir}')
    except requests.exceptions.RequestException as e:
        print(f'Failed to download {file_name} from {full_url}: {e}')
    except Exception as e:
        print(f'An error occurred while downloading {file_name} from {full_url}: {e}')

def download_files(model_path, output_dir):
    base_url = f"{BASE_URL_PREFIX}{model_path}{BASE_URL_SUFFIX}"
    model_name = model_path.split('/')[-1]
    output_subdir = os.path.join(output_dir, model_name)
    os.makedirs(output_subdir, exist_ok=True)

    response = requests.get(base_url)
    soup = BeautifulSoup(response.content, 'html.parser')

    links = soup.find_all('a', href=True)
    download_links = [link['href'] for link in links if link['href'].endswith(('.safetensors', '.json', '.model', '.bin') + ('?download=true',))]

    base_domain = urlparse(base_url).scheme + '://' + urlparse(base_url).netloc
    full_urls = [urljoin(base_domain, link) for link in download_links]
    file_names = [os.path.basename(link).replace('?download=true', '') for link in download_links]

    with ThreadPoolExecutor(max_workers=5) as executor:
        executor.map(download_file, full_urls, file_names, [output_subdir] * len(full_urls))

def browse_directory():
    global output_dir_entry  # Declare output_dir_entry as a global variable
    directory = filedialog.askdirectory()
    output_dir_entry.delete(0, tk.END)  # Use the global output_dir_entry variable
    output_dir_entry.insert(0, directory)

def start_download():
    model_path = model_path_entry.get()
    output_dir = output_dir_entry.get()

    if not model_path or not output_dir:
        warning_label.config(text="Please fill in both fields.", fg="red")
        return

    download_files(model_path, output_dir)
    warning_label.config(text="Download complete.", fg="green")

# Create the main window
root = tk.Tk()
root.title("HF Raw Model Downloader")
root.geometry("350x170")  # Set the window size

# Create and pack the widgets
model_path_label = tk.Label(root, text="Model Path:")
model_path_label.pack()

model_path_entry = tk.Entry(root)
model_path_entry.pack()
model_path_entry.config(width=50)  # Set the width of the entry field

output_dir_label = tk.Label(root, text="Output Directory:")
output_dir_label.pack()

global output_dir_entry
output_dir_entry = tk.Entry(root)
output_dir_entry.pack()
output_dir_entry.config(width=50)  # Set the width of the entry field

browse_button = tk.Button(root, text="Browse", command=browse_directory)
browse_button.pack()

warning_label = tk.Label(root, text="", fg="red")
warning_label.pack()

download_button = tk.Button(root, text="Download", command=start_download)
download_button.pack()

root.mainloop()

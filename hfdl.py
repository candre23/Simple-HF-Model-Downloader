import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from concurrent.futures import ThreadPoolExecutor

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
            print(f'Downloading: {file_name} to {output_dir}')
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

if __name__ == "__main__":
    import sys

    if len(sys.argv) != 3:
        print("Usage: python download.py <model_path> <output_dir>")
        sys.exit(1)

    model_path = sys.argv[1]
    output_dir = sys.argv[2]

    download_files(model_path, output_dir)

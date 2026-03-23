import json
from typing import Tuple
import requests
from tqdm import tqdm

FIGSHARE_FILE_ID = 51832613

def download_figshare_to_memory(file_id: int) -> bytes:
    """
    Stream-download a Figshare file into memory without saving to disk.
    Returns the raw bytes.
    """
    url = f"https://figshare.com/ndownloader/files/{file_id}"
    with requests.get(url, stream=True) as response:
        response.raise_for_status()
        total_size = int(response.headers.get("content-length", 0))
        block_size = 8192
        progress_bar = tqdm(total=total_size, unit="iB", unit_scale=True)
        chunks = []
        for chunk in response.iter_content(chunk_size=block_size):
            if chunk:
                chunks.append(chunk)
                progress_bar.update(len(chunk))
        progress_bar.close()
        data = b"".join(chunks)
        if total_size and len(data) != total_size:
            print("Warning: downloaded size mismatch; content-length may be missing or incorrect.")
        return data


def compute_counts_and_mean_energy_from_json_text(json_text: str) -> Tuple[int, float]:
    """
    Compute total frame count and mean energy_per_atom from the given JSON text.
    Expects structure: { 'mp-id': { 'frame-id': { 'energy_per_atom': ... } } }
    """
    data = json.loads(json_text)

    num_frames = 0
    energy_sum = 0.0
    energy_count = 0

    for _mp_id, frames in data.items():
        if not isinstance(frames, dict):
            continue
        for _frame_id, payload in frames.items():
            if not isinstance(payload, dict):
                continue
            num_frames += 1
            value = payload.get("energy_per_atom")
            if value is not None:
                try:
                    energy_sum += float(value)
                    energy_count += 1
                except (TypeError, ValueError):
                    pass

    mean_energy = energy_sum / energy_count if energy_count > 0 else float("nan")
    return num_frames, energy_count, mean_energy


if __name__ == "__main__":
    raw_bytes = download_figshare_to_memory(FIGSHARE_FILE_ID)
    json_text = raw_bytes.decode("utf-8", errors="ignore")
    frames, energy_count, mean_e = compute_counts_and_mean_energy_from_json_text(json_text)
    print(f"Total frame ids: {frames}")
    print(f"Total energy_count: {energy_count}")
    print(f"Mean energy_per_atom [eV/atom]: {mean_e}")



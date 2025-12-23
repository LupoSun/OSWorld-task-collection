import numpy as np
from PIL import Image
import os
import logging
import cv2

logging.basicConfig(level=logging.INFO)

def check_seamlessness(image_path: str, threshold: float = 1.4) -> (bool, float):
    """
    Checks if an image is seamless by tiling it 2x2 and checking edge intensity at seams.
    Returns (is_seamless, ratio).
    ratio = seam_edge_intensity / global_edge_intensity
    If ratio > threshold, it's likely not seamless.
    """
    try:
        img = Image.open(image_path).convert('L')
        w, h = img.size
        
        # Create 2x2 tiling
        tiled = Image.new('L', (w*2, h*2))
        tiled.paste(img, (0, 0))
        tiled.paste(img, (w, 0))
        tiled.paste(img, (0, h))
        tiled.paste(img, (w, h))
        
        tiled_arr = np.array(tiled)
        
        # Apply Laplacian to detect edges
        laplacian = cv2.Laplacian(tiled_arr, cv2.CV_64F)
        laplacian_abs = np.abs(laplacian)
        
        # Define seam regions
        # Vertical seam is at column w
        # Horizontal seam is at row h
        margin = 2
        
        v_seam_region = laplacian_abs[:, w-margin:w+margin]
        h_seam_region = laplacian_abs[h-margin:h+margin, :]
        
        seam_mean = (np.mean(v_seam_region) + np.mean(h_seam_region)) / 2
        global_mean = np.mean(laplacian_abs)
        
        if global_mean == 0:
            return True, 0.0
            
        ratio = seam_mean / global_mean
        
        return ratio < threshold, ratio
        
    except Exception as e:
        logging.error(f"Error in check_seamlessness: {e}")
        return False, 999.0

files = [
    "/Users/taosun/Downloads/OSWorld/evaluation_examples/examples/new_tasks/no_seam.png",
    "/Users/taosun/Downloads/OSWorld/evaluation_examples/examples/new_tasks/with_seam.png"
]

print("--- Testing seamlessness check (Threshold 1.4) ---")
for f in files:
    is_seamless, ratio = check_seamlessness(f)
    print(f"{os.path.basename(f)}: Seamless? {is_seamless} (Ratio: {ratio:.4f})")

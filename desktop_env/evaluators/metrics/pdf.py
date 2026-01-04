import operator
from typing import Any, Dict
import logging
import fitz  # PyMuPDF
from pypdf import PdfReader
from skimage.metrics import structural_similarity as ssim
import numpy as np
from PIL import Image
from .gimp import structure_check_by_ssim, structure_check_by_mse
import io
import os
import requests

def check_pdf_visual_similarity(pdf_file: str, rules: Dict[str, Any]) -> float:
    """
    Compares the visual similarity of the submission PDF against a Ground Truth PDF.
    Expects 'ground_truth_path' in rules (can be local path or URL).
    """
    if pdf_file is None: return 0.0
    gt_path = rules.get("ground_truth_path")
    if not gt_path: return 0.0
    
    try:
        doc_sub = fitz.open(pdf_file)
        
        # Handle Remote GT
        if gt_path.startswith("http"):
             logging.info(f"Downloading GT from {gt_path}...")
             response = requests.get(gt_path)
             if response.status_code != 200:
                 print(f"Failed to download GT: {response.status_code}")
                 return 0.0
             doc_gt = fitz.open(stream=response.content, filetype="pdf")
        else:
             doc_gt = fitz.open(gt_path)
        
        if len(doc_sub) != len(doc_gt):
            return 0.0
            
        threshold = rules.get("threshold", 0.9)
        mse_thresh = rules.get("mse_threshold", 0.05) # Loose MSE
        
        for i in range(len(doc_gt)):
            page_gt = doc_gt[i]
            page_sub = doc_sub[min(i, len(doc_sub)-1)]
            
            # Render to pixmap (image)
            mat = fitz.Matrix(2, 2)
            pix_gt = page_gt.get_pixmap(matrix=mat)
            pix_sub = page_sub.get_pixmap(matrix=mat)
            
            # Convert to PIL Image
            img_gt = Image.open(io.BytesIO(pix_gt.tobytes("png")))
            img_sub = Image.open(io.BytesIO(pix_sub.tobytes("png")))
            
            # Use SSIM first
            if structure_check_by_ssim(img_gt, img_sub, threshold=threshold):
                continue
                
            # Fallback to MSE
            if structure_check_by_mse(img_gt, img_sub, threshold=mse_thresh):
                continue
                
            return 0.0
            
        return 1.0
        
    except Exception as e:
        print(f"Error checking PDF visual similarity: {e}")
        return 0.0



def check_pdf_pages(pdf_file: str, rules: Dict[str, Any]) -> float:
    if pdf_file is None:
        return 0.0
    reader = PdfReader(pdf_file)
    nb_pages: int = len(reader.pages)
    return float(getattr(operator, rules["relation"])(nb_pages, rules["ref_value"]))


def check_pdf_size(pdf_file: str, rules: Dict[str, Any]) -> float:
    """Checks if PDF page size matches expected standard (A3, A4, etc)."""
    if pdf_file is None:
        return 0.0
    
    try:
        reader = PdfReader(pdf_file)
        if len(reader.pages) == 0:
            return 0.0
            
        # Get first page size in points
        # 1 inch = 72 points
        # A3 Landscape: 420mm x 297mm = 16.54in x 11.69in = 1191pt x 842pt
        # A1 Landscape: 841mm x 594mm = 33.11in x 23.39in = 2384pt x 1684pt
        
        box = reader.pages[0].mediabox
        width = float(box.width)
        height = float(box.height)
        
        target_format = rules.get("format", "A3") # Default A3
        
        # Define tolerances
        if target_format == "A3":
            # Allow rotation? Usually Landscape specified.
            expected_w, expected_h = 1191, 842 
            print(f"DEBUG SIZE: Expected A3 (~{expected_w} x ~{expected_h})")
        elif target_format == "A1":
             expected_w, expected_h = 2384, 1684
        elif target_format == "4:3":
             expected_w, expected_h = 1008, 756
        else:
             # Add other formats if needed
             expected_w, expected_h = 0, 0
             
        # Check matching (allowing for small rounding errors and rotation)
        # Check if Landscape
        if width > height:
             match_w = abs(width - expected_w) < 50
             match_h = abs(height - expected_h) < 50
        else:
             # Portrait
             match_w = abs(width - expected_h) < 50
             match_h = abs(height - expected_w) < 50
             
        return 1.0 if (match_w and match_h) else 0.0

    except Exception as e:
        print(f"Error checking PDF size: {e}")
        return 0.0


def check_pdf_text_content(pdf_file: str, rules: Dict[str, Any]) -> float:
    if pdf_file is None: return 0.0
    try:
        # Pypdf text extraction
        reader = PdfReader(pdf_file)
        full_text = ""
        for page in reader.pages:
            full_text += page.extract_text()
            
        expected_text = rules.get("text", "")
        if expected_text.lower() in full_text.lower():
            return 1.0
        return 0.0
    except:
        return 0.0


def check_pdf_image_count(pdf_file: str, rules: Dict[str, Any]) -> float:
    if pdf_file is None: return 0.0
    try:
        reader = PdfReader(pdf_file)
        count = 0
        for page in reader.pages:
            if '/XObject' in page['/Resources']:
                xObject = page['/Resources']['/XObject'].get_object()
                for obj in xObject:
                    if xObject[obj]['/Subtype'] == '/Image':
                        count += 1
        
        expected = rules.get("ref_value", 0)
        relation = rules.get("relation", "ge") # Default >=
        
        return float(getattr(operator, relation)(count, expected))
    except Exception as e:
        print(f"Error counting images: {e}")
        return 0.0

def check_pdf_text_position(pdf_file: str, rules: Dict[str, Any]) -> float:
    """
    Checks if specific text is located in a specific region (e.g., center) of the page.
    """
    if pdf_file is None: return 0.0
    text = rules.get("text", "")
    page_idx = rules.get("page_index", 0)
    region_type = rules.get("region", "center")
    
    try:
        doc = fitz.open(pdf_file)
        if page_idx >= len(doc): return 0.0
        page = doc[page_idx]
        
        # Search for text
        rects = page.search_for(text)
        if not rects:
            return 0.0
            
        # Consider the first occurrence
        rect = rects[0]
        text_center_x = (rect.x0 + rect.x1) / 2
        text_center_y = (rect.y0 + rect.y1) / 2
        
        page_w = page.rect.width
        page_h = page.rect.height
        
        if region_type == "center":
            # Check horizontally centered? Or both?
            # Title usually horizontally centered.
            # Allow 10% deviation
            dev_x = abs(text_center_x - page_w/2)
            dev_y = abs(text_center_y - page_h/2)
            
            # For title, centered usually means horizontally.
            # Vertical center might not be true for a title at the top.
            # If rules say "center", assumes center of page?
            # User said "text box is around the centre".
            # I will check horizontal centering strictly, and ignore vertical unless specified.
            # But "around the centre" might mean spatial center of page.
            # Let's check both with loose tolerance (20%?) or check specific "title" logic.
            # Safe bet: Check if it's "roughly" in the middle 50% box.
            
            in_x = (0.25 * page_w) < text_center_x < (0.75 * page_w)
            in_y = (0.25 * page_h) < text_center_y < (0.75 * page_h)
            
            # If user meant "Title text around center", they often mean Alignment.
            # But let's assume spatial location.
            return 1.0 if (in_x and in_y) else 0.0
            
        elif region_type == "title_top":
             # Horizontally centered, Vertically top
             in_x = (0.25 * page_w) < text_center_x < (0.75 * page_w)
             in_y = text_center_y < (0.4 * page_h)
             return 1.0 if (in_x and in_y) else 0.0

        return 0.0
        
    except Exception as e:
        print(f"Error checking text position: {e}")
        return 0.0

    return answers


def check_presentation_file_exists(file_path: str, rules: Dict[str, Any]) -> float:
    """
    Wrapper to return 1.0 if the file was successfully retrieved.
    If the getter failed (FileNotFound), this won't be called.
    """
    return 1.0 if file_path and os.path.exists(file_path) else 0.0

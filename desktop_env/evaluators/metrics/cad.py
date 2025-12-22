import re
import math
from typing import Dict, Any, List, Set, Union
import logging

logger = logging.getLogger("desktopenv.metrics.cad")

def check_step_bounding_box(result: str, rules: Dict[str, Any]) -> float:
    """
    Checks if a STEP file's geometry matches the expected Bounding Box dimensions,
    allowing for rotation (swapping X, Y, Z) and translation.
    
    Args:
        result (str): Path to the STEP file.
        rules (Dict[str, Any]): Dictionary containing expectation rules:
            - "dimensions": List of [len_a, len_b, len_c] expected dimensions.
                                 Example: [10000, 15000, 9000]
            - "tolerance": Float, tolerance for dimension matching (default 1.0).
            - "check_z_levels": Optional List[float]. If provided, verifies that
                                distinct Z-heights exist relative to the lowest point.
                                Useful to ensure features like a tower exist.
            
    Returns:
        float: 1.0 if dimensions match, 0.0 otherwise.
    """
    if not result:
        logger.error("Result file path is None")
        return 0.0

    try:
        with open(result, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except Exception as e:
        logger.error(f"Failed to read file {result}: {e}")
        return 0.0

    # 1. Basic Header Check
    if "ISO-10303-21" not in content[:1000]: 
        logger.error(f"File {result} is not a valid ISO-10303-21 STEP file.")
        return 0.0

    # 2. Extract all Cartesian Points
    # Regex for CARTESIAN_POINT('',(x,y,z))
    point_pattern = re.compile(r"CARTESIAN_POINT\s*\(\s*'[^']*'\s*,\s*\(\s*([^,]+),\s*([^,]+),\s*([^)]+)\s*\)\s*\)", re.IGNORECASE)
    
    xs, ys, zs = [], [], []
    for match in point_pattern.finditer(content):
        try:
            xs.append(float(match.group(1)))
            ys.append(float(match.group(2)))
            zs.append(float(match.group(3)))
        except ValueError:
            continue

    if not xs:
        logger.warning("No CARTESIAN_POINT entries found in STEP file.")
        return 0.0

    # 3. Calculate Bounding Box Dimensions
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    min_z, max_z = min(zs), max(zs)
    
    dims = [
        max_x - min_x,
        max_y - min_y,
        max_z - min_z
    ]
    
    # 4. Compare validation
    expected_dims = rules.get("dimensions", [])
    if not expected_dims:
        return 1.0 # No dimension check requested

    tolerance = rules.get("tolerance", 1.0)
    
    # Sort both to allow for rotation (e.g. X and Y swapped)
    dims.sort()
    expected_dims.sort()
    
    logger.info(f"Calculated BBox: {dims}")
    logger.info(f"Expected BBox:   {expected_dims}")

    dims_match = True
    for d, e in zip(dims, expected_dims):
        if not math.isclose(d, e, abs_tol=tolerance):
            dims_match = False
            break
            
    if not dims_match:
        logger.info("Dimension mismatch.")
        return 0.0

    # 5. Optional: Check Z-Levels (relative to Z-min)
    # This ensures "Tower" exists (e.g. we expect points at 0, 6000, 9000 height)
    # We map all Z's to relative Z (z - min_z), then check if expected levels exist near them.
    expected_levels = rules.get("check_z_levels")
    if expected_levels:
        rel_zs = [z - min_z for z in zs]
        
        # Look for rotation again? 
        # Actually, if we sorted dimensions, we don't know which axis corresponds to 'height' in the expected_levels.
        # But typically 'height' is unique or we assume Up-Axis is Z. 
        # For robustness, we can try to find the axis that matches the expected levels.
        # Simple approach: Assume Z is Up (typical in AEC) or check all 3 axes.
        
        # Let's try to match expected levels against relative coordinates of X, Y, or Z axes.
        
        def check_axis_levels(coords, levels, tol):
            min_c = min(coords)
            rel_c = [c - min_c for c in coords]
            for lvl in levels:
                if not any(math.isclose(rc, lvl, abs_tol=tol) for rc in rel_c):
                    return False
            return True

        # Check if *any* axis satisfies the level requirements
        valid_axis_found = (
            check_axis_levels(xs, expected_levels, tolerance) or
            check_axis_levels(ys, expected_levels, tolerance) or
            check_axis_levels(zs, expected_levels, tolerance)
        )
        
        if not valid_axis_found:
            logger.info(f"Could not find axis containing relative levels {expected_levels}")
            return 0.0

    return 1.0

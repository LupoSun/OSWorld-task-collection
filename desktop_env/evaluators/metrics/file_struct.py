
import os
import glob
import logging

logger = logging.getLogger("desktopenv.metrics.file_struct")

def check_folder_structure(submission_dir, rule) -> float:
    """
    Checks if the submission directory structure matches the ground truth directory structure.
    
    Args:
        submission_dir (str): Path to the agent's organized directory (or zip).
        rule (dict): Rule containing 'ground_truth_path'.
        
    Returns:
        float: 1.0 if all GT files exist in submission at correct relative paths, 0.0 otherwise.
    """

    import zipfile
    import tempfile
    import shutil

    # Handle String Input (stdout from 'find' command)
    if isinstance(submission_dir, str) and "\n" in submission_dir:
        # It's a list of files from 'find'
        # Filter lines and normalize path
        submission_files = []
        for line in submission_dir.splitlines():
            line = line.strip()
            if not line: continue
            
            # Remove './' prefix carefully
            if line.startswith("./"):
                line = line[2:]
            
            # Normalize to match OS path separator if needed, but VM is usually Linux (/)
            # GT Rel path uses os.sep (Local Host). If Host is Mac/Linux, it matches.
            submission_files.append(line)
        
        # We need to verify against GT files
        # Check if we have an explicit list in rule
        gt_files = rule.get("expected_files")
        
        if not gt_files:
            # Fallback to local path check (backward compatibility)
            ground_truth_dir = rule.get("ground_truth_path")
            if not ground_truth_dir:
                 logger.error("check_folder_structure: No 'expected_files' or 'ground_truth_path' in rule")
                 return 0.0
            
            if not os.path.exists(ground_truth_dir):
                logger.error(f"Ground Truth directory not found: {ground_truth_dir}")
                return 0.0

            gt_files = []
            for root, _, files in os.walk(ground_truth_dir):
                for f in files:
                    if f == ".DS_Store": continue
                    rel_path = os.path.relpath(os.path.join(root, f), ground_truth_dir)
                    gt_files.append(rel_path)

        if not gt_files:
            return 1.0

        missing_files = []
        for expected in gt_files:
            if expected not in submission_files:
                # Try relaxed match? e.g. Linux case sensitivity?
                # For now strict
                missing_files.append(expected)

        if missing_files:
            logger.info(f"Missing files in submission list: {missing_files[:5]}...")
            logger.debug(f"Submission list sample: {submission_files[:5]}")
            return 0.0
            
        return 1.0

    # Handle Zip Submission
    if submission_dir.endswith(".zip"):
        if not os.path.exists(submission_dir):
            logger.error(f"Submission zip not found: {submission_dir}")
            return 0.0
            
        temp_dir = tempfile.mkdtemp()
        try:
            with zipfile.ZipFile(submission_dir, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)
            
            # Use the extracted folder (Assuming it extracts to root or one subfolder?)
            # If user zipped "Project_Archive/" it might be inside.
            # Let's inspect content. If single dir, enter it.
            extracted_items = os.listdir(temp_dir)
            if len(extracted_items) == 1 and os.path.isdir(os.path.join(temp_dir, extracted_items[0])):
                 check_root = os.path.join(temp_dir, extracted_items[0])
            else:
                 check_root = temp_dir
                 
            # Recursive check logic
            return _verify_structure(check_root, ground_truth_dir)
            
        except zipfile.BadZipFile:
            logger.error(f"Invalid zip file: {submission_dir}")
            return 0.0
        finally:
             shutil.rmtree(temp_dir) # Cleanup
             
    if not os.path.exists(submission_dir):
        logger.error(f"Submission directory not found: {submission_dir}")
        return 0.0
        
    return _verify_structure(submission_dir, ground_truth_dir)

def _verify_structure(submission_path, ground_truth_path):
    if not os.path.exists(ground_truth_path):
        logger.error(f"Ground Truth directory not found: {ground_truth_path}")
        return 0.0

    # Get all files in Ground Truth
    gt_files = []
    for root, _, files in os.walk(ground_truth_path):
        for f in files:
            if f == ".DS_Store": continue
            # Relative path
            rel_path = os.path.relpath(os.path.join(root, f), ground_truth_path)
            gt_files.append(rel_path)
            
    if not gt_files:
        logger.warning("Ground Truth directory is empty (ignoring .DS_Store)")
        return 1.0
        
    missing_files = []
    for rel_path in gt_files:
        expected_path = os.path.join(submission_path, rel_path)
        if not os.path.exists(expected_path):
            missing_files.append(rel_path)
            
    if missing_files:
        logger.info(f"Missing files in submission: {missing_files[:5]} (Total: {len(missing_files)})")
        return 0.0
        
    return 1.0

import fnmatch
from typing import Dict, List

import lxml.cssselect
import lxml.etree
from lxml.etree import _Element as Element

_libconf_namespaces = [("oor", "http://openoffice.org/2001/registry")]
_libconf_ns_mapping = dict(_libconf_namespaces)
_setup_locale_selector = lxml.cssselect.CSSSelector('item[oor|path$=L10N]>prop[oor|name=ooSetupSystemLocale]>value',
                                                    namespaces=_libconf_ns_mapping)
_locale_selector = lxml.cssselect.CSSSelector('item[oor|path$=L10N]>prop[oor|name=ooLocale]>value',
                                              namespaces=_libconf_ns_mapping)


def check_libre_locale(config_file: str, rules: Dict[str, List[str]]) -> float:
    config: Element = lxml.etree.parse(config_file).getroot()
    setup_locale_setting: List[Element] = _setup_locale_selector(config)
    locale_setting: List[Element] = _locale_selector(config)

    setup_locale_setting: str = setup_locale_setting[0].text \
        if len(setup_locale_setting) > 0 \
        else locale_setting[0].text

    return float(any(fnmatch.fnmatchcase(setup_locale_setting, ptn) \
                     for ptn in rules["locale_set"]
                     )
                 )

import pandas as pd
from datetime import datetime

def check_schedule_recovery(submission_path: str, rule: dict) -> float:
    """
    Verifies the ODS submission against a Ground Truth ODS file.
    Uses pandas to compare content logic (Dates) and visualization (Gantt X's).
    """
    if not submission_path or not rule.get("ground_truth"):
        return 0.0

    try:
        # Load Submission
        df_sub = pd.read_excel(submission_path, engine="odf")
        
        # Load Ground Truth
        gt_source = rule["ground_truth"]
        
        # Handle Remote URL
        if gt_source.startswith("http"):
            import requests
            import tempfile
            
            # Simple download (assuming direct link or handling Google Drive 'uc' export)
            # For robustness, we might want the same gdown logic if it's strictly Drive, 
            # but standard requests is often enough for 'export=download' links if public.
            try:
                response = requests.get(gt_source, allow_redirects=True)
                response.raise_for_status()
                
                with tempfile.NamedTemporaryFile(suffix=".ods", delete=False) as tmp_gt:
                    tmp_gt.write(response.content)
                    gt_path = tmp_gt.name
            except Exception as e:
                print(f"Failed to download GT: {e}")
                return 0.0
        else:
            gt_path = gt_source

        df_gt = pd.read_excel(gt_path, engine="odf")
        
        # Cleanup temp file if we created one
        if gt_source.startswith("http") and 'gt_path' in locals():
            try:
                import os
                os.remove(gt_path)
            except:
                pass
        
        # Normalize DataFrames
        # 1. Check Basics: Shape, Columns
        if df_sub.shape != df_gt.shape:
            print(f"Shape Mismatch: Sub {df_sub.shape} != GT {df_gt.shape}")
            return 0.0
            
        # 2. Key Data Columns: Start Date, End Date
        # We enforce strict match on these.
        cols_to_check = ["Task ID", "Start Date", "End Date"]
        for col in cols_to_check:
            if col not in df_sub.columns:
                print(f"Missing Column: {col}")
                return 0.0
                
            # Compare values
            # Convert to string to avoid Timestamp vs String issues
            sub_col = df_sub[col].astype(str).str.strip()
            gt_col = df_gt[col].astype(str).str.strip()
            
            if not sub_col.equals(gt_col):
                print(f"Column Mismatch {col}")
                # print(sub_col.compare(gt_col))
                return 0.0
                
        # 3. Gantt Chart Verification
        # Check all "Date" columns (columns that are not fixed info)
        # Headers: ID, Name, Start, Dur, End, Pred, (Spacer) ... [May 06, May 07...]
        fixed_cols = ["Task ID", "Task Name", "Start Date", "Duration (Days)", "End Date", "Predecessors", ""]
        gantt_cols = [c for c in df_gt.columns if c not in fixed_cols]
        
        for col in gantt_cols:
            if col not in df_sub.columns:
                print(f"Missing Gantt Column: {col}")
                return 0.0
            
            # Normalization: "X", "x" -> "X". Empty/Nan -> ""
            sub_gantt = df_sub[col].fillna("").astype(str).str.upper().str.strip()
            gt_gantt = df_gt[col].fillna("").astype(str).str.upper().str.strip()
            
            # Logic: We only care that "X" matches "X".
            # If agent puts "x" or "X " it should pass.
            
            if not sub_gantt.equals(gt_gantt):
                print(f"Gantt Mismatch on {col}")
                return 0.0

        return 1.0
        
    except Exception as e:
        print(f"Metric Error: {e}")
        return 0.0

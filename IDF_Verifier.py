import os
import re

def strip_comments(idf_text):
    return re.sub(r'!.*', '', idf_text)

def verify_idf_parameters(target_path):
    all_ready = True
    error_log = []
    
    expected_wall = "Typical Insulation 2"
    expected_roof = "Typical Insulation"
    expected_window = "BTAP-Ext-FixedWindow:U=0.280 SHGC=0.600"
    expected_window_2 = "BTAP-Ext-Skylights:U=0.241 SHGC=0.600"
    
    target_wall_const = "BTAP-Ext-Wall-Mass:U-0.29"
    target_roof_const = "BTAP-Ext-Roof-Metal"

    # Support parsing a singular file OR a directory
    if os.path.isfile(target_path) and target_path.lower().endswith('.idf'):
        all_idf_files = [target_path]
    elif os.path.isdir(target_path):
        all_idf_files = [os.path.join(target_path, f) for f in os.listdir(target_path) if f.lower().endswith('.idf')]
    else:
        all_idf_files = []

    if not all_idf_files:
        return False, f"No .idf files found for verification at:\n{os.path.abspath(target_path)}"
    
    for file_path in all_idf_files:
        filename = os.path.basename(file_path)
        display_name = f"{filename}"
        
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            raw_text = f.read()
            
        clean_text = strip_comments(raw_text)
        objects = clean_text.split(';')
        
        wall_insulation = None
        roof_insulation = None
        window_constructions = set()
        
        for obj in objects:
            fields = [field.strip() for field in obj.split(',')]
            if not fields or not fields[0]: 
                continue
                
            obj_type = fields[0].upper()
            
            if obj_type == 'CONSTRUCTION':
                if len(fields) > 1:
                    name = fields[1].upper()
                    if name == target_wall_const.upper():
                        if len(fields) > 4: 
                            wall_insulation = fields[4]
                    elif name == target_roof_const.upper():
                        if len(fields) > 3: 
                            roof_insulation = fields[3]
                            
            elif obj_type == 'FENESTRATIONSURFACE:DETAILED':
                if len(fields) > 3: 
                    window_constructions.add(fields[3])
        
        errors = []
        if wall_insulation is None:
            errors.append(f"Missing wall construction: '{target_wall_const}'")
        elif wall_insulation.upper() != expected_wall.upper():
            errors.append(f"Wall Layer 3 mismatch: Found '{wall_insulation}', Expected '{expected_wall}'")
            
        if roof_insulation is None:
            errors.append(f"Missing roof construction: '{target_roof_const}'")
        elif roof_insulation.upper() != expected_roof.upper():
            errors.append(f"Roof Layer 2 mismatch: Found '{roof_insulation}', Expected '{expected_roof}'")
            
        if not window_constructions:
            errors.append("No FenestrationSurface:Detailed objects found.")
        else:
            for wc in window_constructions:
                if wc.upper() != expected_window.upper() and wc.upper() != expected_window_2.upper():
                    errors.append(f"Window Construction mismatch: Found '{wc}', Expected '{expected_window}'")
                    
        if errors:
            all_ready = False
            error_log.append(f"[FAIL] {display_name}:")
            for err in errors:
                error_log.append(f"  - {err}")
            
    if all_ready:
        return True, "SUCCESS! All IDF parameters are valid and ready to run."
    else:
        return False, "ERROR: Inconsistencies found.\n" + "\n".join(error_log)
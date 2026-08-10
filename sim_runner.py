import os
import re
import glob
import math
import shutil
import subprocess
from concurrent.futures import ProcessPoolExecutor, as_completed
import hvac_generator

def sanitize_idf(idf_path, target_version="25.2"):
    """
    Cleans an IDF file by ensuring only one Version and one Site:Location 
    object exist to prevent EnergyPlus strict validation fatal errors.
    """
    with open(idf_path, 'r') as f:
        content = f.read()

    content = re.sub(r'(?i)Version,.*?;', '', content, flags=re.DOTALL)
    site_locations = re.findall(r'(?i)Site:Location,.*?;', content, flags=re.DOTALL)
    content = re.sub(r'(?i)Site:Location,.*?;', '', content, flags=re.DOTALL)
    
    final_location = site_locations[-1] if site_locations else ""
    clean_header = f"Version, {target_version};\n\n{final_location}\n\n"
    final_content = re.sub(r'\n{3,}', '\n\n', clean_header + content)
    
    with open(idf_path, 'w') as f:
        f.write(final_content)
        
    return True
    
def get_ground_temps(epw_name):
    """Returns monthly ground temperatures based on the city in the EPW filename."""
    default_temps = [18.0] * 12
    name_lower = epw_name.lower()
    
    temps = {'surface': default_temps, 'deep': default_temps, 'shallow': default_temps, 'fc': default_temps}
    
    if 'calgary' in name_lower:
        temps['surface'] = [-5.3, -0.7, 4.6, 8.6, 14.1, 15.3, 13.4, 8.9, 3.0, -2.5, -6.3, -7.4]
        temps['deep'] = [-1.8, -0.6, 1.6, 3.6, 7.3, 9.2, 9.7, 8.6, 6.2, 3.3, 0.5, -1.3]
    elif 'winnipeg' in name_lower:
        temps['surface'] = [-12.8, -14.4, -11.7, -7.4, 3.7, 12.2, 18.0, 19.8, 16.8, 10.1, 1.3, -7.0]
        temps['deep'] = [-2.6, -5.4, -6.0, -5.1, -0.9, 3.6, 7.8, 10.6, 11.3, 9.7, 6.1, 1.7]
    elif 'resolute' in name_lower:
        temps['surface'] = [-18.4, -26.4, -31.2, -32.7, -29.8, -23.2, -15.0, -7.0, -1.6, -0.4, -3.5, -10.0]
        temps['deep'] = [-13.6, -17.9, -21.5, -23.5, -24.7, -23.0, -19.7, -15.4, -11.4, -8.9, -8.4, -10.1]
    elif 'whitehorse' in name_lower:
        temps['surface'] = [-15.2, -16.6, -14.1, -10.3, -0.2, 7.6, 12.9, 14.5, 11.8, 5.7, -2.4, -9.9]
        temps['deep'] = [-5.9, -8.4, -9.0, -8.2, -4.4, -0.2, 3.5, 6.2, 6.8, 5.3, 2.0, -2.0]
    elif 'phoenix' in name_lower:
        temps['surface'] = [13.0, 15.0, 19.0, 22.7, 29.8, 33.5, 34.5, 32.7, 28.3, 22.9, 17.5, 14.0]
        temps['deep'] = [18.7, 18.3, 19.3, 20.8, 24.3, 27.0, 28.8, 29.2, 28.1, 25.9, 23.0, 20.5]
    elif 'angeles' in name_lower:
        temps['surface'] = [14.2, 14.0, 14.4, 15.1, 17.0, 18.4, 19.4, 19.7, 19.2, 18.1, 16.6, 15.2]
        temps['deep'] = [15.9, 15.5, 15.4, 15.5, 16.2, 17.0, 17.7, 18.2, 18.3, 18.0, 17.4, 16.7]
    elif 'denver' in name_lower:
        temps['surface'] = [0.4, 2.3, 6.2, 9.8, 16.7, 20.3, 21.3, 19.4, 15.2, 9.9, 4.7, 1.3]
        temps['deep'] = [5.9, 5.5, 6.5, 7.9, 11.4, 14.0, 15.7, 16.1, 15.0, 12.9, 10.1, 7.6]
    elif 'miami' in name_lower:
        temps['surface'] = [22.3, 20.9, 20.5, 20.9, 22.7, 24.7, 26.6, 28.0, 28.4, 27.8, 26.2, 24.2]
        temps['deep'] = [24.3, 23.3, 22.7, 22.5, 22.8, 23.7, 24.7, 25.7, 26.3, 26.5, 26.1, 25.3]
    elif 'chicago' in name_lower:
        temps['surface'] = [3.4, -1.4, -2.7, -1.5, 4.9, 12.1, 18.9, 23.8, 25.3, 23.0, 17.4, 10.4]
        temps['deep'] = [10.5, 7.0, 4.9, 4.3, 5.5, 8.4, 12.0, 15.5, 17.8, 18.4, 17.0, 14.2]
    elif 'minneapolis' in name_lower:
        temps['surface'] = [-6.8, -8.2, -5.7, -1.7, 8.6, 16.6, 21.9, 23.6, 20.8, 14.6, 6.3, -1.3]
        temps['deep'] = [2.8, 0.2, -0.4, 0.4, 4.3, 8.5, 12.4, 15.1, 15.7, 14.2, 10.8, 6.7]
    elif 'houston' in name_lower:
        temps['surface'] = [15.8, 13.0, 12.3, 12.9, 16.6, 20.8, 24.7, 27.5, 28.4, 27.0, 23.8, 19.8]
        temps['deep'] = [19.9, 17.9, 16.6, 16.3, 17.0, 18.6, 20.7, 22.7, 24.1, 24.4, 23.6, 22.0]
    elif 'seattle' in name_lower:
        temps['surface'] = [7.5, 5.3, 4.7, 5.3, 8.2, 11.6, 14.7, 17.0, 17.7, 16.6, 14.0, 10.8]
        temps['deep'] = [10.8, 9.2, 8.2, 7.9, 8.5, 9.8, 11.5, 13.1, 14.2, 14.5, 13.9, 12.5]
    else:
        temps['surface'] = default_temps
        
    temps['shallow'] = temps['surface']
    temps['fc'] = temps['surface']
    return temps

def inject_ground_temps(idf_text, epw_name):
    """Replaces ground temperature objects with city-specific values."""
    t_data = get_ground_temps(epw_name)
    
    patterns = [
        r'(?i)Site:GroundTemperature:BuildingSurface,[^;]*;',
        r'(?i)Site:GroundTemperature:FCfactorMethod,[^;]*;',
        r'(?i)Site:GroundTemperature:Shallow,[^;]*;',
        r'(?i)Site:GroundTemperature:Deep,[^;]*;'
    ]
    new_text = idf_text
    for p in patterns:
        new_text = re.sub(p, '', new_text)
        
    def format_obj(name, vals):
        return (f"{name},\n  " + 
                ", ".join(f"{v:.2f}" for v in vals[:6]) + ",\n  " + 
                ", ".join(f"{v:.2f}" for v in vals[6:]) + ";\n\n")

    new_block = (
        format_obj('Site:GroundTemperature:BuildingSurface', t_data['surface']) +
        format_obj('Site:GroundTemperature:FCfactorMethod', t_data['fc']) +
        format_obj('Site:GroundTemperature:Shallow', t_data['shallow']) +
        format_obj('Site:GroundTemperature:Deep', t_data['deep'])
    )
    return new_text + "\n! --- INJECTED GROUND TEMPS ---\n" + new_block

def apply_geometry_config(idf_text, geom_type):
    """Scales X, Y, or Z coordinates based on layout selection. 
       If geom_type is 4, reduces window height (Z) by 50% to cut WWR."""
    if geom_type == 1:
        return idf_text
        
    lines = idf_text.splitlines()
    is_wwr = (geom_type == 4)
    
    scale_x = 2 if geom_type == 2 else 1
    scale_y = 2 if geom_type == 2 else 1
    scale_z = 3 if geom_type == 3 else 1
    
    num_regex = r'[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?'
    expr = re.compile(rf'^(\s*)({num_regex})(\s*,\s*)({num_regex})(\s*,\s*)({num_regex})(\s*[,;]?.*)$')
    single_num_expr = re.compile(rf'^(\s*)({num_regex})(\s*[,;]?.*)$')

    in_geometry = False
    in_window = False
    
    for i, line in enumerate(lines):
        line_trim = line.strip()
        clean_line = line_trim.split('!')[0]
        
        if not is_wwr:
            geo_keywords = ['BuildingSurface:Detailed', 'FenestrationSurface:Detailed', 'Shading:', 'Wall:Detailed', 'RoofCeiling:Detailed', 'Floor:Detailed', 'Window', 'Door']
            if any(line_trim.lower().startswith(kw.lower()) for kw in geo_keywords):
                in_geometry = True
                continue
                
            if in_geometry:
                m3 = expr.match(line)
                if m3:
                    x = float(m3.group(2)) * scale_x
                    y = float(m3.group(4)) * scale_y
                    z = float(m3.group(6)) * scale_z
                    lines[i] = f"{m3.group(1)}{x:g}{m3.group(3)}{y:g}{m3.group(5)}{z:g}{m3.group(7)}"
                else:
                    m1 = single_num_expr.match(line)
                    if m1:
                        val = float(m1.group(2))
                        if 'x-coordinate' in line.lower():
                            lines[i] = f"{m1.group(1)}{val * scale_x:g}{m1.group(3)}"
                        elif 'y-coordinate' in line.lower():
                            lines[i] = f"{m1.group(1)}{val * scale_y:g}{m1.group(3)}"
                        elif 'z-coordinate' in line.lower():
                            lines[i] = f"{m1.group(1)}{val * scale_z:g}{m1.group(3)}"
                            
                if ';' in clean_line:
                    in_geometry = False
        else:
            win_keywords = ['FenestrationSurface:Detailed', 'Window']
            if any(line_trim.lower().startswith(kw.lower()) for kw in win_keywords):
                in_window = True
                continue
                
            if in_window:
                m3 = expr.match(line)
                if m3:
                    z = float(m3.group(6)) * 0.5
                    lines[i] = f"{m3.group(1)}{m3.group(2)}{m3.group(3)}{m3.group(4)}{m3.group(5)}{z:g}{m3.group(7)}"
                    
                if ';' in clean_line:
                    in_window = False

    return '\n'.join(lines)

def set_no_mass_resistance(idf_text, target_names, absolute_val):
    """Sets the U-value/resistance for mass-less insulation materials."""
    lines = idf_text.splitlines()
    i = 0
    while i < len(lines):
        if lines[i].strip().lower().startswith('material:nomass,'):
            found_target = False
            for j in range(i + 1, min(i + 11, len(lines))):
                if not found_target:
                    if any(name.lower() in lines[j].lower() for name in target_names):
                        found_target = True
                if found_target and 'thermal resistance' in lines[j].lower():
                    lines[j] = re.sub(r'([\d\.]+)', f"{absolute_val:.4f}", lines[j], count=1)
                    break
                if ';' in lines[j]:
                    break
        i += 1
    return '\n'.join(lines)

def set_window_u_factor(idf_text, absolute_val):
    """Sets window U-Factor."""
    lines = idf_text.splitlines()
    i = 0
    while i < len(lines):
        if lines[i].strip().lower().startswith('windowmaterial:simpleglazingsystem,'):
            for j in range(i + 1, min(i + 11, len(lines))):
                if 'u-factor' in lines[j].lower():
                    lines[j] = re.sub(r'([\d\.]+)', f"{absolute_val:.4f}", lines[j], count=1)
                    break
                if ';' in lines[j]:
                    break
        i += 1
    return '\n'.join(lines)

def run_worker(job_dict, main_dir, report_dir, eplus_dir):
    """Executes a single EnergyPlus simulation using ExpandObjects and EnergyPlus."""
    eplus_exe = os.path.join(eplus_dir, 'energyplus.exe')
    expand_exe = os.path.join(eplus_dir, 'ExpandObjects.exe')
    worker_dir = os.path.join(main_dir, f"Worker_{job_dict['id']}")
    
    os.makedirs(worker_dir, exist_ok=True)
    status_msg = "FAILED"
    
    try:
        shutil.copyfile(job_dict['epw_path'], os.path.join(worker_dir, 'weather.epw'))
        shutil.copyfile(os.path.join(eplus_dir, 'Energy+.idd'), os.path.join(worker_dir, 'Energy+.idd'))
        
        with open(job_dict['source_idf'], 'r') as f:
            idf_text = f.read()
            
        idf_text = set_no_mass_resistance(idf_text, ["Typical Insulation 2"], job_dict['wall_mult'])
        idf_text = set_no_mass_resistance(idf_text, ["Typical Insulation 3"], job_dict['roof_mult'])
        idf_text = set_window_u_factor(idf_text, job_dict['win_mult'])
        
        idf_text = re.sub(r'[-+]?\d*\.?\d+([eE][-+]?\d+)?(?=,(\s+)!- Flow Rate per Exterior Surface Area)', 
                          f"{job_dict['inf_val']:.2E}", idf_text)
                          
        with open(os.path.join(worker_dir, 'in.idf'), 'w') as f:
            f.write(idf_text)
            
        sanitize_idf(os.path.join(worker_dir, 'in.idf'))
        
        subprocess.run(f'cd /d "{worker_dir}" && "{expand_exe}" in.idf', shell=True, stdout=subprocess.DEVNULL)
        if os.path.exists(os.path.join(worker_dir, 'expanded.idf')):
            shutil.move(os.path.join(worker_dir, 'expanded.idf'), os.path.join(worker_dir, 'in.idf'))
            
        res = subprocess.run(f'cd /d "{worker_dir}" && "{eplus_exe}" -w weather.epw -i Energy+.idd in.idf', shell=True, stdout=subprocess.DEVNULL)
        
        if res.returncode == 0 and os.path.exists(os.path.join(worker_dir, 'eplustbl.csv')):
            status_msg = "SUCCESS"
            city_name = os.path.splitext(os.path.basename(job_dict['epw_path']))[0]
            base_report_name = f"Sim{job_dict['id']}_{city_name}_Sys{job_dict['sys_id']}_Geo{job_dict['geom_type']}_W{job_dict['wall_mult']}_R{job_dict['roof_mult']}_Win{job_dict['win_mult']}_I{job_dict['inf_val']:.2E}"
            
            shutil.copyfile(os.path.join(worker_dir, 'eplustbl.csv'), os.path.join(report_dir, f"{base_report_name}.csv"))
            
            err_path = os.path.join(worker_dir, 'eplusout.err')
            if os.path.exists(err_path):
                shutil.copyfile(err_path, os.path.join(report_dir, f"{base_report_name}.err"))
                
            shutil.rmtree(worker_dir)
        else:
            status_msg = "E+ ERR: Check Log"
            
    except Exception as e:
        status_msg = f"PYTHON ERR: {str(e)}"
        
    return status_msg

def start_batch_simulation(idf_file, weather_dir, eplus_dir, num_threads, main_dir, report_dir, wall_mults, roof_mults, win_mults, inf_vals, hvac_list=None, progress_callback=None, selected_cities=None, geom_list=None):

    if hvac_list is None:
        hvac_list = list(range(1, 10))

    if selected_cities:
        epw_list = [
            os.path.join(weather_dir, f) 
            for f in os.listdir(weather_dir) 
            if f.lower().endswith('.epw') and any(city.lower() in f.lower() for city in selected_cities)
        ]
    else:
        epw_list = [os.path.join(weather_dir, f) for f in os.listdir(weather_dir) if f.lower().endswith('.epw')]
    if geom_list:
        geom_types = geom_list
    else:
        geom_types = [1, 2, 3, 4]
    
    hvac_dir = os.path.join(main_dir, "HVAC_Models")
    os.makedirs(hvac_dir, exist_ok=True)
    
    base_idf = idf_file
    
    with open(base_idf, 'r') as f:
        base_idf_text = f.read()

    for epw_path in epw_list:
        epw_dir, epw_name = os.path.split(epw_path)
        epw_name = os.path.splitext(epw_name)[0]
        
        ddy_path = os.path.join(epw_dir, f"{epw_name}.ddy")
        ddy_text = ""
        if os.path.exists(ddy_path):
            with open(ddy_path, 'r') as df:
                ddy_text = df.read()
                
        for g in geom_types:
            mod_idf = apply_geometry_config(base_idf_text, g)
            mod_idf = inject_ground_temps(mod_idf, epw_name)
            
            final_pre_idf = f"Version, 25.2;\n{mod_idf}\n{ddy_text}"
            temp_name = os.path.join(hvac_dir, f"Temp_Base_{epw_name}_G{g}.idf")
            
            with open(temp_name, 'w') as f:
                f.write(final_pre_idf)
                
            out_prefix = os.path.join(hvac_dir, f"{epw_name}_G{g}")
            
            hvac_generator.generate_parametric_idfs(temp_name, out_prefix, hvac_list)
            os.remove(temp_name)

    jobs = []
    counter = 1
    for epw_path in epw_list:
        epw_name = os.path.splitext(os.path.basename(epw_path))[0]
        for g in geom_types:
            for sys_id in hvac_list: 
                out_prefix = os.path.join(hvac_dir, f"{epw_name}_G{g}")
                sys_file = f"{out_prefix}_System_{sys_id}.idf"
                
                for wm in wall_mults:
                    for rm in roof_mults:
                        for win in win_mults:
                            for inf in inf_vals:
                                run_dir = os.path.join(main_dir, "Runs", f"Run_{counter:05d}")
                                jobs.append({
                                    'id': counter,
                                    'run_dir': run_dir,
                                    'source_idf': sys_file,
                                    'epw_path': epw_path,
                                    'eplus_dir': eplus_dir,
                                    'geom_type': g,
                                    'wall_mult': wm, 
                                    'roof_mult': rm, 
                                    'win_mult': win, 
                                    'inf_val': inf,
                                    'sys_id': sys_id
                                })
                                counter += 1

    total_jobs = len(jobs)
    completed = 0
    
    with ProcessPoolExecutor(max_workers=num_threads) as executor:
        futures = {executor.submit(run_worker, job, main_dir, report_dir, eplus_dir): job for job in jobs}
        
        for future in as_completed(futures):
            completed += 1
            if progress_callback:
                progress_callback(completed, total_jobs)
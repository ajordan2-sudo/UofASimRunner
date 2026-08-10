import os
import re
import shutil

def format_vertical(obj_list):
    """Formats a list of EnergyPlus object strings vertically."""
    out = ""
    for raw_str in obj_list:
        if not raw_str.strip():
            continue
        
        has_semicolon = raw_str.strip().endswith(';')
        if has_semicolon:
            raw_str = re.sub(r';\s*$', '', raw_str)
            
        parts = [p.strip() for p in raw_str.split(',')]
        formatted = ",\n  ".join(parts)
        
        if has_semicolon:
            formatted += ';\n\n'
        else:
            formatted += '\n\n'
            
        out += formatted
    return out

def shorten_idf_names(idf_text):
    """Shortens zone names longer than 25 characters to prevent EnergyPlus string length errors."""
    tokens = re.findall(r'(?im)^\s*Zone\s*,[ \t\r\n]*([^,;!]+)', idf_text)
    if not tokens:
        return idf_text
        
    unique_zones = list(set([t.strip() for t in tokens]))
    unique_zones.sort(key=len, reverse=True)
    
    new_idf_text = idf_text
    z_count = 1
    
    for old_name in unique_zones:
        if len(old_name) > 25:
            new_name = f"ZN_{z_count:03d}"
            z_count += 1
            new_idf_text = new_idf_text.replace(old_name, new_name)
            
    if z_count > 1:
        print(f"Successfully shortened {z_count - 1} overly long zone names.")
        
    return new_idf_text

def extract_hvac_and_thermostats(input_filename):
    """Parses the IDF to find HVAC zones, thermostats, outdoor air specs, water equipment, and fan schedule."""
    with open(input_filename, 'r') as f:
        idf_text = f.read()
        
    clean_idf = re.sub(r'!.*?\n', '\n', idf_text)
    
    sch_match = re.search(r'Schedule:(?:Year|Compact|Constant)\s*,\s*(sys_[^,;]+)', clean_idf, re.IGNORECASE)
    fan_sch = sch_match.group(1).strip() if sch_match else "Always_On"

    hvac_zones = list(set([z.strip() for z in re.findall(r'ZoneHVAC:EquipmentConnections\s*,[ \t\r\n]*([^,;]+)', clean_idf)]))
    
    sp_blocks = re.findall(r'ThermostatSetpoint:DualSetpoint\s*,([^;]+);', clean_idf)
    sp_map = {}
    for block in sp_blocks:
        fields = [f.strip() for f in block.split(',')]
        if len(fields) >= 3:
            sp_map[fields[0]] = {'heat': fields[1], 'cool': fields[2]}
            
    tc_blocks = re.findall(r'ZoneControl:Thermostat\s*,([^;]+);', clean_idf)
    zone_schedules = {}
    for block in tc_blocks:
        fields = [f.strip() for f in block.split(',')]
        if len(fields) >= 5:
            z_name, sp_name = fields[1], fields[4]
            if sp_name in sp_map:
                zone_schedules[z_name] = sp_map[sp_name]
                
    oa_blocks = re.findall(r'DesignSpecification:OutdoorAir\s*,([^;]+);', clean_idf)
    oa_map = {}
    for block in oa_blocks:
        fields = [f.strip() for f in block.split(',')]
        name = fields[0]
        method = fields[1] if len(fields) >= 2 and fields[1] else 'Flow/Person'
        oa_p = fields[2] if len(fields) >= 3 else ''
        oa_a = fields[3] if len(fields) >= 4 else ''
        oa_z = fields[4] if len(fields) >= 5 else ''
        oa_map[name] = {'method': method, 'oa_p': oa_p, 'oa_a': oa_a, 'oa_z': oa_z}
        
    sz_blocks = re.findall(r'Sizing:Zone\s*,([^;]+);', clean_idf)
    zone_to_oa_name = {}
    for block in sz_blocks:
        fields = [f.strip() for f in block.split(',')]
        if len(fields) >= 14 and fields[13]:
            zone_to_oa_name[fields[0]] = fields[13]
            
    zone_oa = {}
    oa_keys = list(oa_map.keys())
    for z in hvac_zones:
        found = False
        if z in zone_to_oa_name and zone_to_oa_name[z] in oa_map:
            zone_oa[z] = oa_map[zone_to_oa_name[z]]
            found = True
        elif z in oa_map:
            zone_oa[z] = oa_map[z]
            found = True
        else:
            for k in oa_keys:
                if z.lower() in k.lower() or k.lower() in z.lower():
                    zone_oa[z] = oa_map[k]
                    found = True
                    break
        if not found:
            if len(oa_keys) == 1:
                zone_oa[z] = oa_map[oa_keys[0]]
            else:
                zone_oa[z] = {'method': 'Sum', 'oa_p': '0.002539', 'oa_a': '0.0003048', 'oa_z': ''}
                
    we_blocks = re.findall(r'WaterUse:Equipment\s*,([^;]+);', clean_idf)
    water_equip = [f.split(',')[0].strip() for f in we_blocks if f.strip()]
    
    return hvac_zones, zone_schedules, zone_oa, water_equip, fan_sch

def clean_idf_hvac(input_filename, output_filename):
    """Removes existing HVAC and plant objects from the base IDF."""
    objects_to_remove = [
        'AirLoopHVAC', 'AirTerminal', 'AvailabilityManager', 'Boiler', 'Branch', 'Chiller', 'Coil', 
        'Condenser', 'Connector', 'Controller', 'CoolingTower', 'DesignSpecification:OutdoorAir', 
        'DistrictCooling', 'DistrictHeating', 'Duct', 'EvaporativeCooler', 'Fan', 'HeatExchanger', 
        'HeatPump', 'Humidifier', 'NodeList', 'OutdoorAir', 'Pipe', 'PlantComponent', 'PlantEquipment', 
        'PlantLoop', 'Pump', 'SetpointManager', 'Sizing:Plant', 'Sizing:System', 'Sizing:Zone', 
        'SolarCollector', 'WaterHeater', 'ZoneControl', 'ZoneHVAC', 'ThermostatSetpoint', 'WaterUse:Connections'
    ]
    
    with open(input_filename, 'r') as fid_in, open(output_filename, 'w') as fid_out:
        inside_object = False
        object_type = ''
        current_object_lines = []
        
        for line in fid_in:
            clean_line = re.sub(r'!.*', '', line).strip()
            
            if not clean_line and not inside_object:
                fid_out.write(line)
                continue
                
            if not inside_object:
                tokens = re.match(r'^([a-zA-Z0-9:]+)', clean_line)
                if tokens:
                    inside_object = True
                    object_type = tokens.group(1)
                    current_object_lines = [line]
                else:
                    fid_out.write(line)
            else:
                current_object_lines.append(line)
                
            if inside_object and ';' in clean_line:
                should_remove = any(object_type.lower().startswith(obj.lower()) for obj in objects_to_remove)
                if not should_remove:
                    for l in current_object_lines:
                        fid_out.write(l)
                inside_object = False
                current_object_lines = []
                object_type = ''

def get_common_dhw(water_equip, ambient_zone):
    """Generates the common domestic hot water system template."""
    if not water_equip:
        connection_str = 'WaterUse:Connections, DHW_Connections, DHW_Demand_Inlet_Node, DHW_Demand_Outlet_Node, , , , , None;'
    else:
        equip_list = ', '.join(water_equip)
        connection_str = f'WaterUse:Connections, DHW_Connections, DHW_Demand_Inlet_Node, DHW_Demand_Outlet_Node, , , , , None, , , {equip_list};'

    objs = [
        'Schedule:Constant, Always_On, , 1;',
        'Schedule:Constant, DHW_Temp_Sch, Temperature, 70;',
        'WaterHeater:Sizing, DHW_Water_Heater, PeakDraw, 1, 1.5;',
        'BranchList, DHW_Supply_Branch_List, DHW_Supply_Branch;',
        'BranchList, DHW_Demand_Branch_List, DHW_Demand_Branch;',
        'Branch, DHW_Supply_Branch, , Pump:VariableSpeed, DHW_Pump, DHW_Supply_Inlet_Node, DHW_Pump_Outlet_Node, WaterHeater:Mixed, DHW_Water_Heater, DHW_Pump_Outlet_Node, DHW_Supply_Outlet_Node;',
        'Branch, DHW_Demand_Branch, , WaterUse:Connections, DHW_Connections, DHW_Demand_Inlet_Node, DHW_Demand_Outlet_Node;',
        'Pump:VariableSpeed, DHW_Pump, DHW_Supply_Inlet_Node, DHW_Pump_Outlet_Node, autosize, 179352, autosize, 0.9, 0, 0, 1, 0, 0, 0, Intermittent, , , , , , , , , , , , PowerPerFlowPerPressure, 348701.1, 1.282051282, , General;',
        f'WaterHeater:Mixed, DHW_Water_Heater, 1.0, DHW_Temp_Sch, 2, 82.2, Cycle, 1000000, , 0, , NaturalGas, 0.8, , , , , , , , Zone, , {ambient_zone}, , , 1, , 1, , , , DHW_Pump_Outlet_Node, DHW_Supply_Outlet_Node, 1, , , 1, autosize, autosize, 1.5, IndirectHeatPrimarySetpoint, , General;',
        'PlantEquipmentOperationSchemes, DHW_Loop_Op_Scheme, PlantEquipmentOperation:HeatingLoad, DHW_Heating_Op, Always On Discrete;',
        'PlantEquipmentOperation:HeatingLoad, DHW_Heating_Op, 0, 10000000, DHW_Plant_List;',
        'PlantEquipmentList, DHW_Plant_List, WaterHeater:Mixed, DHW_Water_Heater;',
        'SetpointManager:Scheduled, DHW_Outlet_Setpoint_Mgr, Temperature, DHW_Temp_Sch, DHW_Supply_Outlet_Node;',
        'Sizing:Plant, DHW_Loop, Heating, 70, 11, NonCoincident, 1;',
        connection_str,
        'PlantLoop, DHW_Loop, Water, , DHW_Loop_Op_Scheme, DHW_Supply_Outlet_Node, 100, 3, autosize, , autocalculate, DHW_Supply_Inlet_Node, DHW_Supply_Outlet_Node, DHW_Supply_Branch_List, , DHW_Demand_Inlet_Node, DHW_Demand_Outlet_Node, DHW_Demand_Branch_List, , SequentialLoad, , SingleSetpoint, None, None, 2;'
    ]
    return format_vertical(objs)

def get_global_objects(sys_id, master_zone, fan_sch):
    """Returns global plant and DOAS objects based on system ID."""
    vent_sch = fan_sch 
    global_doas = f'HVACTemplate:System:DedicatedOutdoorAir, Main_DOAS, {vent_sch}, DirectIntoZone, autosize, 0.39975, 600, 0.615, 1, DrawThrough, None, , FixedSetpoint, 21, , 21, 15.6, 21, 23.3, autosize, autosize, 3, None, , FixedSetpoint, 21, , 15, 7.8, 21, 12.2, 0.8, , None, 0.7, 0.65, Plate, None, None, 0.00924, None, , 0.000001, autosize, 0.003, , ;'

    objs = []
    if sys_id == 1:
        objs = [
            'HVACTemplate:Plant:HotWaterLoop, HWLoop, , Intermittent, Default, , , 82, VariableFlow, 179352, None, 82.2, -6.7, 65.6, 10, SinglePump, Yes, Yes, Water, 11, , SequentialLoad;',
            'HVACTemplate:Plant:Boiler, Boiler, HotWaterBoiler, autosize, 0.8, NaturalGas, , 1, , 1.1, 1, 100;'
        ]
    elif sys_id == 2:
        objs = [f'HVACTemplate:System:Unitary, Main_Furnace, Always_On, {master_zone}, autosize, {fan_sch}, 0.39975, 600, 0.615, 1, SingleSpeedDX, , 12.8, autosize, autosize, 3, Gas, , 50, autosize, 0.8, , autosize, autosize, {vent_sch}, NoEconomizer, NoLockout, , , , , , , BlowThrough, CycleOnAny, , None, , , None, 60, None, , 0.000001, autosize, , 30, No, 0.7, 500, 0.9, 1;']
    elif sys_id == 3:
        objs = [f'HVACTemplate:System:Unitary, Main_Furnace, Always_On, {master_zone}, autosize, {fan_sch}, 0.39975, 600, 0.615, 1, None, , 12.8, autosize, autosize, 3, Gas, , 50, autosize, 0.8, , autosize, autosize, {vent_sch}, NoEconomizer, NoLockout, , , , , , , BlowThrough, CycleOnAny, , None, , , None, 60, None, , 0.000001, autosize, , 30, No, 0.7, 500, 0.9, 1;']
    elif sys_id == 4:
        objs = [f'HVACTemplate:System:ConstantVolume, AHU_System, {fan_sch}, autosize, 0.39975, 600, 0.615, 1, DrawThrough, None, , ControlZone, {master_zone}, 12.8, , 15.6, 15.6, 12.8, 23.3, Electric, , ControlZone, {master_zone}, 40, , 15, 7.8, 12.2, 12.2, autosize, 0.8, , None, , 7.2, , 0.8, , autosize, autosize, {vent_sch}, NoEconomizer, , , , , , , CycleOnAny, , None, 0.7, 0, Plate, None, None, , 60, , None, , 0.000001, autosize, , 30, , No, 0.7, 300, 0.9, 1;']
    elif sys_id == 5:
        objs = [] 
    elif sys_id == 6:
        objs = [
            'HVACTemplate:Plant:Boiler, Boiler_Main, HotWaterBoiler, autosize, 0.8, NaturalGas, , 1, , 1.1, 1, 100;',
            'HVACTemplate:Plant:HotWaterLoop, HW_Loop, , Intermittent, Default, , , 82, VariableFlow, 179352, None, 82.2, -6.7, 65.6, 10, SinglePump, Yes, Yes, Water, 11, , SequentialLoad;'
        ]
    elif sys_id == 7:
        objs = []
    elif sys_id == 8:
        objs = [
            global_doas,
            'HVACTemplate:Plant:Tower, WSHP_Tower, SingleSpeed, autosize, autosize, autosize, autosize, autosize, , 1;',
            'HVACTemplate:Plant:Boiler, WSHP_Boiler, HotWaterBoiler, autosize, 0.8, NaturalGas, , 1, , 1.1, 1, 100;',
            'HVACTemplate:Plant:MixedWaterLoop, WSHP_Loop, , Intermittent, Default, , , 33, , 20, VariableFlow, 179352, SinglePump, Yes, Yes, Water, 5.6, SequentialLoad;'
        ]
    elif sys_id == 9:
        objs = [
            global_doas,
            'HVACTemplate:System:VRF, VRF_System, , autosize, 3.3, -6, 43, autosize, 1, 3.4, -20, 16, 0.15, , LoadPriority, , No, 30, 10, 30, 33, 2, 0.5, 5, Resistive, Timed, 0.058333, autosize, 5, AirCooled, autosize, 0.9, autosize, , , 2, , Electricity, -15, 45;',
            'HVACTemplate:Plant:Boiler, VRF_Boiler, HotWaterBoiler, autosize, 0.8, NaturalGas, , 1, , 1.1, 1, 100;',
            'HVACTemplate:Plant:HotWaterLoop, VRF_HW_Loop, , Intermittent, Default, , , 82, VariableFlow, 179352, None, 82.2, -6.7, 65.6, 10, SinglePump, Yes, Yes, Water, 11, , SequentialLoad;'
        ]
    elif sys_id == 10:
        objs = []
    elif sys_id == 11:
        objs = []
    elif sys_id == 12:
        objs = []
    elif sys_id == 13:
        objs = [f'HVACTemplate:System:PackagedVAV, Main_Furnace, Always_On, autosize, autosize, DrawThrough, 0.7, 1000, 0.9, 1, TwoSpeedDX, , , 12.8, autosize, autosize, 3, Gas, , , 10, autosize, 0.8, , autosize, autosize, ProportionalMinimum, {fan_sch}, NoEconomizer, NoLockout, , , , , , , InletVaneDampers, StayOff, , None, 0.7, 0.65, None, None, None, , 60, None, , 0.000001, autosize, , 30, NonCoincident, No, 0.7, 500, 0.9, 1, InletVaneDampers;']
    elif sys_id == 14:
        objs = [
            f'HVACTemplate:System:ConstantVolume, Main_Furnace, Always_On, autosize, 0.7, 600, 0.9, 1, DrawThrough, ChilledWater, , FixedSetpoint, , 12.8, , 15.6, 15.6, 12.8, 23.3, Gas, , FixedSetpoint, , 10, , 15, 7.8, 12.2, 12.2, autosize, 0.8, , None, , 7.2, , 0.8, , autosize, autosize, {fan_sch}, NoEconomizer, , , , , , , StayOff, , None, 0.7, 0.65, Plate, None, None, , 60, , None, , 0.000001, autosize, , 30, , No, 0.7, 300, 0.9, 1;',
            'HVACTemplate:Plant:ChilledWaterLoop, MainChilledWaterLoop, , Intermittent, Default, , , 7.22, ConstantPrimaryNoSecondary, 179352, 179352, Default, , , , 29.4, 179352, None, 12.2, 15.6, 6.7, 26.7, SinglePump, SinglePump, SinglePump, Yes, Yes, Yes, Yes, Water, 6.67, , SequentialLoad, SequentialLoad;',
            'HVACTemplate:Plant:Chiller, PlantChiller, ElectricReciprocatingChiller, autosize, 3, AirCooled, , 1, , 1, 1, 0.25, 5;'
        ]
    elif sys_id == 15: 
        objs = [
            f'HVACTemplate:System:VAV, AHU_System, , autosize, autosize, 0.7, 1000, 0.9, 1, ChilledWater, , , 12.8, Gas, , , 10, 0.8, , None, , , 7.2, 0.8, , autosize, autosize, ProportionalMinimum, {fan_sch}, NoEconomizer, NoLockout, , , , , , , DrawThrough, InletVaneDampers, StayOff, , None, 0.7, 0.65, None, None, None, , 60, None, , 0.000001, autosize, , 30, NonCoincident, No, 0.7, 500, 0.9, 1, InletVaneDampers;',
            'HVACTemplate:Plant:ChilledWaterLoop, MainChilledWaterLoop, , Intermittent, Default, , , 7.22, ConstantPrimaryNoSecondary, 179352, 179352, Default, , , , 29.4, 179352, None, 12.2, 15.6, 6.7, 26.7, SinglePump, SinglePump, SinglePump, Yes, Yes, Yes, Yes, Water, 6.67, , SequentialLoad, SequentialLoad;',
            'HVACTemplate:Plant:Chiller, PlantChiller, ElectricReciprocatingChiller, autosize, 3, AirCooled, , 1, , 1, 1, 0.25, 5;'
        ]
    elif sys_id == 16:
        objs = [
            f'HVACTemplate:System:ConstantVolume, Main_Furnace, Always_On, autosize, 0.7, 600, 0.9, 1, DrawThrough, ChilledWater, , FixedSetpoint, , 12.8, , 15.6, 15.6, 12.8, 23.3, HotWater, , FixedSetpoint, , 10, , 15, 7.8, 12.2, 12.2, autosize, 0.8, , None, , 7.2, , 0.8, , autosize, autosize, {fan_sch}, NoEconomizer, , , , , , , StayOff, , None, 0.7, 0.65, Plate, None, None, , 60, , None, , 0.000001, autosize, , 30, , No, 0.7, 300, 0.9, 1;',
            'HVACTemplate:Plant:HotWaterLoop, HWLoop, , Intermittent, Default, , , 82, VariableFlow, 179352, None, 82.2, -6.7, 65.6, 10, SinglePump, Yes, Yes, Water, 11, , SequentialLoad;',
            'HVACTemplate:Plant:Boiler, Boiler, HotWaterBoiler, autosize, 0.8, NaturalGas, , 1, , 1.1, 1, 100;',
            'HVACTemplate:Plant:ChilledWaterLoop, MainChilledWaterLoop, , Intermittent, Default, , , 7.22, ConstantPrimaryNoSecondary, 179352, 179352, Default, , , , 29.4, 179352, None, 12.2, 15.6, 6.7, 26.7, SinglePump, SinglePump, SinglePump, Yes, Yes, Yes, Yes, Water, 6.67, , SequentialLoad, SequentialLoad;',
            'HVACTemplate:Plant:Chiller, PlantChiller, ElectricReciprocatingChiller, autosize, 3, AirCooled, , 1, , 1, 1, 0.25, 5;'
        ]
    elif sys_id == 17:
        objs = [
            f'HVACTemplate:System:VAV, AHU_System, , autosize, autosize, 0.7, 1000, 0.9, 1, ChilledWater, , , 12.8, HotWater, , , 10, 0.8, , None, , , 7.2, 0.8, , autosize, autosize, ProportionalMinimum, {fan_sch}, NoEconomizer, NoLockout, , , , , , , DrawThrough, InletVaneDampers, StayOff, , None, 0.7, 0.65, None, None, None, , 60, None, , 0.000001, autosize, , 30, NonCoincident, No, 0.7, 500, 0.9, 1, InletVaneDampers;',
            'HVACTemplate:Plant:HotWaterLoop, HWLoop, , Intermittent, Default, , , 82, VariableFlow, 179352, None, 82.2, -6.7, 65.6, 10, SinglePump, Yes, Yes, Water, 11, , SequentialLoad;',
            'HVACTemplate:Plant:Boiler, Boiler, HotWaterBoiler, autosize, 0.8, NaturalGas, , 1, , 1.1, 1, 100;',
            'HVACTemplate:Plant:ChilledWaterLoop, MainChilledWaterLoop, , Intermittent, Default, , , 7.22, ConstantPrimaryNoSecondary, 179352, 179352, Default, , , , 29.4, 179352, None, 12.2, 15.6, 6.7, 26.7, SinglePump, SinglePump, SinglePump, Yes, Yes, Yes, Yes, Water, 6.67, , SequentialLoad, SequentialLoad;',
            'HVACTemplate:Plant:Chiller, PlantChiller, ElectricReciprocatingChiller, autosize, 3, AirCooled, , 1, , 1, 1, 0.25, 5;'
        ]
    elif sys_id == 18:
        objs = [
            'HVACTemplate:Plant:HotWaterLoop, HWLoop, , Intermittent, Default, , , 82, VariableFlow, 179352, None, 82.2, -6.7, 65.6, 10, SinglePump, Yes, Yes, Water, 11, , SequentialLoad;',
            'HVACTemplate:Plant:Boiler, Boiler, HotWaterBoiler, autosize, 0.8, NaturalGas, , 1, , 1.1, 1, 100;',
            'HVACTemplate:Plant:ChilledWaterLoop, MainChilledWaterLoop, , Intermittent, Default, , , 7.22, ConstantPrimaryNoSecondary, 179352, 179352, Default, , , , 29.4, 179352, None, 12.2, 15.6, 6.7, 26.7, SinglePump, SinglePump, SinglePump, Yes, Yes, Yes, Yes, Water, 6.67, , SequentialLoad, SequentialLoad;',
            'HVACTemplate:Plant:Chiller, PlantChiller, ElectricReciprocatingChiller, autosize, 3, AirCooled, , 1, , 1, 1, 0.25, 5;'
        ]
    elif sys_id == 19:
        objs = [
            f'HVACTemplate:System:VAV, AHU_System, , autosize, autosize, 0.7, 1000, 0.9, 1, ChilledWater, , , 12.8, HotWater, , , 10, 0.8, , None, , , 7.2, 0.8, , autosize, autosize, ProportionalMinimum, {fan_sch}, NoEconomizer, NoLockout, , , , , , , DrawThrough, InletVaneDampers, StayOff, , None, 0.7, 0.65, None, None, None, , 60, None, , 0.000001, autosize, , 30, NonCoincident, No, 0.7, 500, 0.9, 1, InletVaneDampers;',
            'HVACTemplate:Plant:HotWaterLoop, HWLoop, , Intermittent, Default, , , 82, VariableFlow, 179352, None, 82.2, -6.7, 65.6, 10, SinglePump, Yes, Yes, Water, 11, , SequentialLoad;',
            'HVACTemplate:Plant:Boiler, Boiler, HotWaterBoiler, autosize, 0.8, NaturalGas, , 1, , 1.1, 1, 100;',
            'HVACTemplate:Plant:ChilledWaterLoop, MainChilledWaterLoop, , Intermittent, Default, , , 7.22, ConstantPrimaryNoSecondary, 179352, 179352, Default, , , , 29.4, 179352, None, 12.2, 15.6, 6.7, 26.7, SinglePump, SinglePump, SinglePump, Yes, Yes, Yes, Yes, Water, 6.67, , SequentialLoad, SequentialLoad;',
            'HVACTemplate:Plant:Chiller, PlantChiller, ElectricReciprocatingChiller, autosize, 3, AirCooled, , 1, , 1, 1, 0.25, 5;'
        ]
    elif sys_id == 20:
        objs = [
            global_doas,
            'HVACTemplate:Plant:HotWaterLoop, HWLoop, , Intermittent, Default, , , 82, VariableFlow, 179352, None, 82.2, -6.7, 65.6, 10, SinglePump, Yes, Yes, Water, 11, , SequentialLoad;',
            'HVACTemplate:Plant:Boiler, Boiler, HotWaterBoiler, autosize, 0.8, NaturalGas, , 1, , 1.1, 1, 100;',
            'HVACTemplate:Plant:ChilledWaterLoop, MainChilledWaterLoop, , Intermittent, Default, , , 7.22, ConstantPrimaryNoSecondary, 179352, 179352, Default, , , , 29.4, 179352, None, 12.2, 15.6, 6.7, 26.7, SinglePump, SinglePump, SinglePump, Yes, Yes, Yes, Yes, Water, 6.67, , SequentialLoad, SequentialLoad;',
            'HVACTemplate:Plant:Chiller, PlantChiller, ElectricReciprocatingChiller, autosize, 3, AirCooled, , 1, , 1, 1, 0.25, 5;'
        ]
    elif sys_id == 21:
        objs = []
    elif sys_id == 22:
        objs = []
    elif sys_id == 23:
        objs = []
    elif sys_id == 24:
        objs = [
            'HVACTemplate:Plant:ChilledWaterLoop, CW_Loop, , Intermittent, Default, , , 7.22, ConstantPrimaryNoSecondary, 179352, 179352, Default, , , , 29.4, 179352, None, 12.2, 15.6, 6.7, 26.7, SinglePump, SinglePump, SinglePump, Yes, Yes, Yes, Yes, Water, 6.67, , SequentialLoad, SequentialLoad;',
            'HVACTemplate:Plant:Chiller, Chiller, DistrictChilledWater, autosize, 5, WaterCooled, , 1, , 1, 1, 0.25, 5;',
            'HVACTemplate:Plant:HotWaterLoop, HW_Loop, , Intermittent, Default, , , 82, ConstantFlow, 179352, None, 82.2, -6.7, 65.6, 10, SinglePump, Yes, Yes, Water, 11, , SequentialLoad;',
            'HVACTemplate:Plant:Boiler, Boiler, DistrictHotWater, autosize, 0.8, NaturalGas, , 1, , 1.1, 1, 100;',
            'HVACTemplate:System:VAV, VAV, , autosize, autosize, 0.7, 1000, 0.9, 1, ChilledWater, , , 12.8, None, , , 10, 0.8, , None, , , 7.2, 0.8, , autosize, autosize, ProportionalMinimum, , NoEconomizer, NoLockout, , , , , , , DrawThrough, InletVaneDampers, StayOff, , None, 0.7, 0.65, None, None, None, , 60, None, , 0.000001, autosize, , 30, NonCoincident, No, 0.7, 500, 0.9, 1, InletVaneDampers;'
        ]
    elif sys_id == 25:
        objs = [
            'HVACTemplate:Plant:ChilledWaterLoop, CW_Loop, , Intermittent, Default, , , 7.22, ConstantPrimaryNoSecondary, 179352, 179352, Default, , , , 29.4, 179352, None, 12.2, 15.6, 6.7, 26.7, SinglePump, SinglePump, SinglePump, Yes, Yes, Yes, Yes, Water, 6.67, , SequentialLoad, SequentialLoad;',
            'HVACTemplate:Plant:Chiller, Chiller, DistrictChilledWater, autosize, 5, WaterCooled, , 1, , 1, 1, 0.25, 5;',
            'HVACTemplate:Plant:HotWaterLoop, HW_Loop, , Intermittent, Default, , , 82, ConstantFlow, 179352, None, 82.2, -6.7, 65.6, 10, SinglePump, Yes, Yes, Water, 11, , SequentialLoad;',
            'HVACTemplate:Plant:Boiler, Boiler, DistrictHotWater, autosize, 0.8, NaturalGas, , 1, , 1.1, 1, 100;',
            'HVACTemplate:System:VAV, VAV, , autosize, autosize, 0.7, 1000, 0.9, 1, ChilledWater, , , 12.8, None, , , 10, 0.8, , None, , , 7.2, 0.8, , autosize, autosize, ProportionalMinimum, , NoEconomizer, NoLockout, , , , , , , DrawThrough, InletVaneDampers, StayOff, , None, 0.7, 0.65, None, None, None, , 60, None, , 0.000001, autosize, , 30, NonCoincident, No, 0.7, 500, 0.9, 1, InletVaneDampers;'
        ]
    elif sys_id == 26:
        objs = [
            'HVACTemplate:Plant:ChilledWaterLoop, CW_Loop, , Intermittent, Default, , , 7.22, ConstantPrimaryNoSecondary, 179352, 179352, Default, , , , 29.4, 179352, None, 12.2, 15.6, 6.7, 26.7, SinglePump, SinglePump, SinglePump, Yes, Yes, Yes, Yes, Water, 6.67, , SequentialLoad, SequentialLoad;',
            'HVACTemplate:Plant:Chiller, Chiller, DistrictChilledWater, autosize, 5, WaterCooled, , 1, , 1, 1, 0.25, 5;',
            'HVACTemplate:Plant:HotWaterLoop, HW_Loop, , Intermittent, Default, , , 82, ConstantFlow, 179352, None, 82.2, -6.7, 65.6, 10, SinglePump, Yes, Yes, Water, 11, , SequentialLoad;',
            'HVACTemplate:Plant:Boiler, Boiler, DistrictHotWater, autosize, 0.8, NaturalGas, , 1, , 1.1, 1, 100;'
        ]
    elif sys_id == 27:
        objs = [
            'HVACTemplate:Plant:ChilledWaterLoop, CW_Loop, , Intermittent, Default, , , 7.22, ConstantPrimaryNoSecondary, 179352, 179352, Default, , , , 29.4, 179352, None, 12.2, 15.6, 6.7, 26.7, SinglePump, SinglePump, SinglePump, Yes, Yes, Yes, Yes, Water, 6.67, , SequentialLoad, SequentialLoad;',
            'HVACTemplate:Plant:Chiller, Chiller, DistrictChilledWater, autosize, 5, WaterCooled, , 1, , 1, 1, 0.25, 5;',
            'HVACTemplate:Plant:HotWaterLoop, HW_Loop, , Intermittent, Default, , , 82, ConstantFlow, 179352, None, 82.2, -6.7, 65.6, 10, SinglePump, Yes, Yes, Water, 11, , SequentialLoad;',
            'HVACTemplate:Plant:Boiler, Boiler, DistrictHotWater, autosize, 0.8, NaturalGas, , 1, , 1.1, 1, 100;',
            'HVACTemplate:System:VAV, VAV, , autosize, autosize, 0.7, 1000, 0.9, 1, ChilledWater, , , 12.8, None, , , 10, 0.8, , None, , , 7.2, 0.8, , autosize, autosize, ProportionalMinimum, , NoEconomizer, NoLockout, , , , , , , DrawThrough, InletVaneDampers, StayOff, , None, 0.7, 0.65, None, None, None, , 60, None, , 0.000001, autosize, , 30, NonCoincident, No, 0.7, 500, 0.9, 1, InletVaneDampers;'
        ]
    elif sys_id == 28:
        objs = [
            'HVACTemplate:Plant:ChilledWaterLoop, CW_Loop, , Intermittent, Default, , , 7.22, ConstantPrimaryNoSecondary, 179352, 179352, Default, , , , 29.4, 179352, None, 12.2, 15.6, 6.7, 26.7, SinglePump, SinglePump, SinglePump, Yes, Yes, Yes, Yes, Water, 6.67, , SequentialLoad, SequentialLoad;',
            'HVACTemplate:Plant:Chiller, Chiller, DistrictChilledWater, autosize, 5, WaterCooled, , 1, , 1, 1, 0.25, 5;',
            'HVACTemplate:Plant:HotWaterLoop, HW_Loop, , Intermittent, Default, , , 82, ConstantFlow, 179352, None, 82.2, -6.7, 65.6, 10, SinglePump, Yes, Yes, Water, 11, , SequentialLoad;',
            'HVACTemplate:Plant:Boiler, Boiler, DistrictHotWater, autosize, 0.8, NaturalGas, , 1, , 1.1, 1, 100;',
            'HVACTemplate:System:VAV, VAV, , autosize, autosize, 0.7, 1000, 0.9, 1, ChilledWater, , , 12.8, HotWater, , , 10, 0.8, , None, , , 7.2, 0.8, , autosize, autosize, ProportionalMinimum, , NoEconomizer, NoLockout, , , , , , , DrawThrough, InletVaneDampers, StayOff, , None, 0.7, 0.65, None, None, None, , 60, None, , 0.000001, autosize, , 30, NonCoincident, No, 0.7, 500, 0.9, 1, InletVaneDampers;'
        ]
    elif sys_id == 29:
        objs = [
            'HVACTemplate:Plant:ChilledWaterLoop, CW_Loop, , Intermittent, Default, , , 7.22, ConstantPrimaryNoSecondary, 179352, 179352, Default, , , , 29.4, 179352, None, 12.2, 15.6, 6.7, 26.7, SinglePump, SinglePump, SinglePump, Yes, Yes, Yes, Yes, Water, 6.67, , SequentialLoad, SequentialLoad;',
            'HVACTemplate:Plant:Chiller, Chiller, DistrictChilledWater, autosize, 5, WaterCooled, , 1, , 1, 1, 0.25, 5;',
            'HVACTemplate:Plant:HotWaterLoop, HW_Loop, , Intermittent, Default, , , 82, ConstantFlow, 179352, None, 82.2, -6.7, 65.6, 10, SinglePump, Yes, Yes, Water, 11, , SequentialLoad;',
            'HVACTemplate:Plant:Boiler, Boiler, DistrictHotWater, autosize, 0.8, NaturalGas, , 1, , 1.1, 1, 100;',
            'HVACTemplate:System:VAV, VAV, , autosize, autosize, 0.7, 1000, 0.9, 1, ChilledWater, , , 12.8, HotWater, , , 10, 0.8, , None, , , 7.2, 0.8, , autosize, autosize, ProportionalMinimum, , NoEconomizer, NoLockout, , , , , , , DrawThrough, InletVaneDampers, StayOff, , None, 0.7, 0.65, None, None, None, , 60, None, , 0.000001, autosize, , 30, NonCoincident, No, 0.7, 500, 0.9, 1, InletVaneDampers;'
        ]
    elif sys_id == 30:
        objs = [f'HVACTemplate:System:UnitaryHeatPump:AirToAir, Main_Furnace, Always_On, {master_zone}, autosize, autosize, autosize, {fan_sch}, BlowThrough, 0.39975, 600, 0.615, 1, SingleSpeedDX, , 12.8, autosize, autosize, 3, SingleSpeedDXHeatPump, , 50, autosize, 2.75, -8, 5, ReverseCycle, Timed, 0.058333, Electric, , autosize, 21, 0.8, , autosize, autosize, , NoEconomizer, NoLockout, , , , , , , StayOff, , None, 0.7, 0.65, None, , 0.000001, autosize, , 30, No, 0.7, 500, 0.9, 1;']
    elif sys_id == 31:
        objs = [global_doas]
    elif sys_id == 32:
       objs = [
           global_doas,
            'HVACTemplate:Plant:MixedWaterLoop, Mixed_Loop, , Intermittent, Default, , , 33, , 20, ConstantFlow, 179352, SinglePump, Yes, Yes, Water, 5.6, SequentialLoad;',
            'HVACTemplate:Plant:Boiler, Boiler, DistrictHotWater, autosize, 0.8, NaturalGas, , 1, , 1.1, 1, 100, MixedWater;',
            'HVACTemplate:Plant:Tower, Tower, SingleSpeed, autosize, autosize, autosize, autosize, autosize, , 1, MixedWater;'
        ]
    elif sys_id == 33:
        objs = [
            global_doas,
            'HVACTemplate:System:VRF, VRF_System, , autosize, 3.3, -6, 43, autosize, 1, 3.4, -20, 16, 0.15, , LoadPriority, , No, 30, 10, 30, 33, 2, 0.5, 5, Resistive, Timed, 0.058333, autosize, 5, AirCooled, autosize, 0.9, autosize, , , 2, , Electricity, -15, 45;'
        ]
    elif sys_id == 34:
        objs = [
            global_doas,
            'HVACTemplate:System:VRF, VRF_System, , autosize, 3.3, -6, 43, autosize, 1, 3.4, -20, 16, 0.15, , LoadPriority, , No, 30, 10, 30, 33, 2, 0.5, 5, Resistive, Timed, 0.058333, autosize, 5, WaterCooled, autosize, 0.9, autosize, , , 2, , Electricity, -15, 45;',
            'HVACTemplate:Plant:MixedWaterLoop, Mixed_Loop, , Intermittent, Default, , , 33, , 20, ConstantFlow, 179352, SinglePump, Yes, Yes, Water, 5.6, SequentialLoad;',
            'HVACTemplate:Plant:Boiler, Boiler, DistrictHotWater, autosize, 0.8, Electricity, , 1, , 1.1, 1, 100, MixedWater;',
            'HVACTemplate:Plant:Tower, Tower, SingleSpeed, autosize, autosize, autosize, autosize, autosize, , 1, MixedWater;'
        ]
        
    return format_vertical(objs)

def get_thermostat_template(zone, heat, cool):
    raw = f'HVACTemplate:Thermostat, Thermostat_{zone}, {heat}, , {cool}, ;'
    return format_vertical([raw])

def get_zone_objects(sys_id, zone, oa, fan_sch):
    """Returns zone-level HVAC template objects based on system ID."""
    t_name = f'Thermostat_{zone}'
    doas_name = 'Main_DOAS'
    exhaust_fan_name = f'Exhaust_Fan_{zone}'
    exhaust_inlet_node = f'{zone}Exhaust Node'
    exhaust_outlet_node = f'{zone}Exhaust Outlet Node'
    
    oa_p = oa.get('oa_p', '0') or '0'
    oa_a = oa.get('oa_a', '0') or '0'
    oa_z = oa.get('oa_z', '0') or '0'
    method = oa.get('method', 'Flow/Person')

    objs = []
    if sys_id == 1:
        objs = [f'HVACTemplate:Zone:PTAC, {zone}, {t_name}, autosize, autosize, , , , {method}, {oa_p}, {oa_a}, {oa_z}, , {fan_sch}, DrawThrough, 0.39975, 75, 0.615, SingleSpeedDX, , autosize, autosize, 3, HotWater, , autosize, 0.8, , , SupplyAirTemperature, 12.8, 11.11, SupplyAirTemperature, 50, 30, , , None, , autosize, None;']
    elif sys_id == 2:
        objs = [f'HVACTemplate:Zone:Unitary, {zone}, Main_Furnace, {t_name}, autosize, , , {method}, {oa_p}, {oa_a}, {oa_z}, , , None, , autosize, SystemSupplyAirTemperature, 12.8, 11.11, SystemSupplyAirTemperature, 50, 30;']
    elif sys_id == 3:
        objs = [f'HVACTemplate:Zone:Unitary, {zone}, Main_Furnace, {t_name}, autosize, , , {method}, {oa_p}, {oa_a}, {oa_z}, , , None, , autosize, SystemSupplyAirTemperature, 12.8, 11.11, SystemSupplyAirTemperature, 50, 30;']
    elif sys_id == 4:
        objs = [f'HVACTemplate:Zone:ConstantVolume, {zone}, AHU_System, {t_name}, autosize, , , {method}, {oa_p}, {oa_a}, {oa_z}, , , None;']
    elif sys_id == 5:
        objs = [f'HVACTemplate:Zone:PTHP, {zone}, {t_name}, autosize, autosize, , , , {method}, {oa_p}, {oa_a}, {oa_z}, , {fan_sch}, DrawThrough, 0.39975, 75, 0.615, SingleSpeedDX, , autosize, autosize, 3, SingleSpeedDXHeatPump, , autosize, 2.75, -8, 5, ReverseCycle, Timed, 0.058333, Electric, , autosize, 21, 0.8, , , SupplyAirTemperature, 12.8, 11.11, SupplyAirTemperature, 50, 30, , , None, , autosize, None;']
    elif sys_id == 6:
        objs = [f'HVACTemplate:Zone:PTHP, {zone}, {t_name}, autosize, autosize, , , , {method}, {oa_p}, {oa_a}, {oa_z}, , {fan_sch}, DrawThrough, 0.39975, 75, 0.615, SingleSpeedDX, , autosize, autosize, 3, SingleSpeedDXHeatPump, , autosize, 2.75, -8, 5, ReverseCycle, Timed, 0.058333, HotWater, , autosize, 21, 0.8, , , SupplyAirTemperature, 12.8, 11.11, SupplyAirTemperature, 50, 30, , , None, , autosize, None;']
    elif sys_id == 7:
        objs = [
            f'HVACTemplate:System:UnitaryHeatPump:AirToAir, {zone}_SZHP, , {zone}, autosize, autosize, autosize, {fan_sch}, BlowThrough, 0.39975, 600, 0.615, 1, SingleSpeedDX, , 12.8, autosize, autosize, 3, SingleSpeedDXHeatPump, , 50, autosize, 2.75, -8, 5, ReverseCycle, Timed, 0.058333, Electric, , autosize, 21, 0.8, , autosize, autosize, , NoEconomizer, NoLockout, , , , , , , StayOff, , None, 0.7, 0.65, None, , 0.000001, autosize, , 30, No, 0.7, 500, 0.9, 1;',
            f'HVACTemplate:Zone:Unitary, {zone}, {zone}_SZHP, {t_name}, autosize, , , {method}, {oa_p}, {oa_a}, {oa_z}, , , None, , autosize, SystemSupplyAirTemperature, 12.8, 11.11, SystemSupplyAirTemperature, 50, 30;'
        ]
    elif sys_id == 8:
        objs = [f'HVACTemplate:Zone:WaterToAirHeatPump, {zone}, {t_name}, autosize, autosize, , , , {method}, {oa_p}, {oa_a}, {oa_z}, , {fan_sch}, DrawThrough, 0.39975, 75, 0.615, Coil:Cooling:WaterToAirHeatPump:EquationFit, autosize, autosize, 3.5, Coil:Heating:WaterToAirHeatPump:EquationFit, autosize, 4.2, , autosize, 2.5, 60, 60, {doas_name}, Electric, SupplyAirTemperature, 12.8, 11.11, SupplyAirTemperature, 50, 30, Cycling, , , None, , autosize;']
    elif sys_id == 9:
        objs = [f'HVACTemplate:Zone:VRF, {zone}, VRF_System, {t_name}, , , 1, autosize, autosize, autosize, autosize, autosize, autosize, autosize, {method}, {oa_p}, {oa_a}, {oa_z}, , , , {fan_sch}, BlowThrough, 0.39975, 75, 0.615, VariableRefrigerantFlowDX, , autosize, autosize, VariableRefrigerantFlowDX, , autosize, , , {doas_name}, SupplyAirTemperature, 12.8, 11.11, SupplyAirTemperature, 50, 30, HotWater, , autosize;']
    elif sys_id == 10:
        objs = [f'HVACTemplate:Zone:PTAC, {zone}, {t_name}, autosize, autosize, , , , {method}, {oa_p}, {oa_a}, {oa_z}, , {fan_sch}, DrawThrough, 0.39975, 75, 0.615, None, , , , , Gas, , autosize, 0.8, , , SupplyAirTemperature, 12.8, 11.11, SupplyAirTemperature, 50, 30, , , None, , autosize, None;']
    elif sys_id == 11:
        objs = [
            f'Fan:ZoneExhaust, {exhaust_fan_name}, Always_On, 0.7, 125, , {exhaust_inlet_node}, {exhaust_outlet_node}, General, {fan_sch};',
            f'HVACTemplate:Zone:PTAC, {zone}, {t_name}, autosize, autosize, , , , {method}, {oa_p}, {oa_a}, {oa_z}, , {fan_sch}, DrawThrough, 0.39975, 75, 0.615, None, , , , , Gas, , autosize, 0.8, , , SupplyAirTemperature, 12.8, 11.11, SupplyAirTemperature, 50, 30, , , None, , autosize, None;'
        ]
    elif sys_id == 12:
        objs = [
            f'Fan:ZoneExhaust, {exhaust_fan_name}, Always_On, 0.7, 125, , {exhaust_inlet_node}, {exhaust_outlet_node}, General, {fan_sch};',
            f'HVACTemplate:Zone:PTAC, {zone}, {t_name}, autosize, autosize, , , , {method}, {oa_p}, {oa_a}, {oa_z}, , {fan_sch}, DrawThrough, 0.39975, 75, 0.615, SingleSpeedDX, , autosize, , , Gas, , autosize, 0.8, , , SupplyAirTemperature, 12.8, 11.11, SupplyAirTemperature, 50, 30, , , None, , autosize, None;'
        ]
    elif sys_id == 13:
        objs = [f'HVACTemplate:Zone:VAV, {zone}, Main_Furnace, {t_name}, autosize, , , Constant, 0.2, , , {method}, {oa_p}, {oa_a}, {oa_z}, None, , Reverse, , , , , , , None, , autosize, SystemSupplyAirTemperature, 12.8, 11.11, SupplyAirTemperature, 50, 30, , ;']
    elif sys_id == 14:
        objs = [f'HVACTemplate:Zone:ConstantVolume, {zone}, Main_Furnace, {t_name}, autosize, , , {method}, {oa_p}, {oa_a}, {oa_z}, , , None, , , , , None, , autosize, SystemSupplyAirTemperature, 12.8, 11.11, SupplyAirTemperature, 50, 30;']
    elif sys_id == 15:
        objs = [f'HVACTemplate:Zone:VAV, {zone}, AHU_System, {t_name}, autosize, , , Constant, 0.2, , , {method}, {oa_p}, {oa_a}, {oa_z}, Electric, , Reverse, , , , , , , None, , autosize, SystemSupplyAirTemperature, 12.8, 11.11, SupplyAirTemperature, 50, 30, , ;']
    elif sys_id == 16:
        objs = [f'HVACTemplate:Zone:ConstantVolume, {zone}, Main_Furnace, {t_name}, autosize, , , {method}, {oa_p}, {oa_a}, {oa_z}, , , HotWater, , , , , None, , autosize, SystemSupplyAirTemperature, 12.8, 11.11, SupplyAirTemperature, 50, 30;']
    elif sys_id == 17:
        objs = [f'HVACTemplate:Zone:VAV, {zone}, AHU_System, {t_name}, autosize, , , Constant, 0.2, , , {method}, {oa_p}, {oa_a}, {oa_z}, HotWater, , Reverse, , , , , , , None, , autosize, SystemSupplyAirTemperature, 12.8, 11.11, SupplyAirTemperature, 50, 30, , ;']
    elif sys_id == 18:
        objs = [f'HVACTemplate:Zone:FanCoil, {zone}, {t_name}, autosize, , , {method}, {oa_p}, {oa_a}, {oa_z}, {fan_sch}, 0.39975, 75, 0.615, 1, ChilledWater, , 12.8, HotWater, , 50, , SupplyAirTemperature, 11.11, SupplyAirTemperature, 30, , , , 0.33, 0.66, , None, , autosize;']
    elif sys_id == 19:
        objs = [f'HVACTemplate:Zone:VAV:FanPowered, {zone}, AHU_System, {t_name}, autosize, , , autosize, autosize, Parallel, autosize, {method}, {oa_p}, {oa_a}, {oa_z}, HotWater, , 0.7, 1000, 0.9, , , None, , autosize, SystemSupplyAirTemperature, 12.8, 11.11, SupplyAirTemperature, 50, 30, , , ;']
    elif sys_id == 20:
        objs = [f'HVACTemplate:Zone:FanCoil, {zone}, {t_name}, autosize, , , {method}, {oa_p}, {oa_a}, {oa_z}, , 0.39975, 75, 0.615, 1, ChilledWater, , 12.8, HotWater, , 50, Main_DOAS, SupplyAirTemperature, 11.11, SupplyAirTemperature, 30, , , , 0.33, 0.66, , None, , autosize;']
    elif sys_id == 21:
        objs = [f'HVACTemplate:Zone:PTAC, {zone}, {t_name}, autosize, autosize, , , , {method}, {oa_p}, {oa_a}, {oa_z}, , {fan_sch}, DrawThrough, 0.39975, 75, 0.615, SingleSpeedDX, , autosize, autosize, 3, Electric, , 0, 0.8, , , SupplyAirTemperature, 12.8, 11.11, SupplyAirTemperature, 50, 30, , , Electric, , autosize, None;']
    elif sys_id == 22:
       objs = [
           f'HVACTemplate:Zone:PTAC, {zone}, {t_name}, autosize, autosize, , , , {method}, {oa_p}, {oa_a}, {oa_z}, , {fan_sch}, DrawThrough, 0.39975, 75, 0.615, SingleSpeedDX, , autosize, autosize, 3, Electric, , 0, 0.8, , , SupplyAirTemperature, 12.8, 11.11, SupplyAirTemperature, 50, 30, , , Electric, , autosize, None;',
           f'Fan:ZoneExhaust, {exhaust_fan_name}, Always_On, 0.7, 125, , {exhaust_inlet_node}, {exhaust_outlet_node}, General, {fan_sch};'
        ]
    elif sys_id == 23:
        objs = [f'HVACTemplate:Zone:PTAC, {zone}, {t_name}, autosize, autosize, , , , {method}, {oa_p}, {oa_a}, {oa_z}, , {fan_sch}, DrawThrough, 0.39975, 75, 0.615, SingleSpeedDX, , autosize, autosize, 3, Electric, , 0, 0.8, , , SupplyAirTemperature, 12.8, 11.11, SupplyAirTemperature, 50, 30, , , Electric, , autosize, None;']
    elif sys_id == 24:
        objs = [f'HVACTemplate:Zone:VAV, {zone}, VAV, {t_name}, autosize, , , Constant, 1, , , {method}, {oa_p}, {oa_a}, {oa_z}, HotWater, , Reverse, , , , , , , None, , autosize, SystemSupplyAirTemperature, 12.8, 11.11, SupplyAirTemperature, 50, 30;']
    elif sys_id == 25:
        objs = [f'HVACTemplate:Zone:VAV, {zone}, VAV, {t_name}, autosize, , , Constant, 1, , , {method}, {oa_p}, {oa_a}, {oa_z}, None, , Reverse, , , , , , , HotWater, , autosize, SystemSupplyAirTemperature, 12.8, 11.11, SupplyAirTemperature, 50, 30;']
    elif sys_id == 26:
        objs = [f'HVACTemplate:Zone:FanCoil, {zone}, {t_name}, autosize, , , {method}, {oa_p}, {oa_a}, {oa_z}, , 0.39975, 75, 0.615, 1, ChilledWater, , 12.8, HotWater, , 50, , SupplyAirTemperature, 11.11, SupplyAirTemperature, 30, , , , 0.33, 0.66, , None, , autosize;']
    elif sys_id == 27:
        objs = [f'HVACTemplate:Zone:VAV:FanPowered, {zone}, VAV, {t_name}, autosize, , , autosize, autosize, Parallel, autosize, {method}, {oa_p}, {oa_a}, {oa_z}, HotWater, , 0.39975, 1000, 0.615, , , None, , autosize, SystemSupplyAirTemperature, 12.8, 11.11, SupplyAirTemperature, 50, 30, ;']
    elif sys_id == 28:
        objs = [f'HVACTemplate:Zone:VAV, {zone}, VAV, {t_name}, autosize, , , Constant, 1, , , {method}, {oa_p}, {oa_a}, {oa_z}, HotWater, , Reverse, , , , , , , None, , autosize, SystemSupplyAirTemperature, 12.8, 11.11, SupplyAirTemperature, 50, 30;']
    elif sys_id == 29:
        objs = [f'HVACTemplate:Zone:VAV, {zone}, VAV, {t_name}, autosize, , , Constant, 0.3, , , {method}, {oa_p}, {oa_a}, {oa_z}, HotWater, , Reverse, , , , , , , None, , autosize, SystemSupplyAirTemperature, 12.8, 11.11, SupplyAirTemperature, 50, 30;']
    elif sys_id == 30:
        objs = [f'HVACTemplate:Zone:Unitary, {zone}, Main_Furnace, {t_name}, autosize, , , {method}, {oa_p}, {oa_a}, {oa_z}, , , None, , autosize, SystemSupplyAirTemperature, 12.8, 11.11, SystemSupplyAirTemperature, 50, 30;']
    elif sys_id == 31:
        objs = [f'HVACTemplate:Zone:PTHP, {zone}, {t_name}, autosize, autosize, , , , {method}, {oa_p}, {oa_a}, {oa_z}, , {fan_sch}, DrawThrough, 0.39975, 75, 0.615, SingleSpeedDX, , autosize, autosize, 3, SingleSpeedDXHeatPump, , autosize, 2.75, -8, 5, ReverseCycle, Timed, 0.058333, Electric, , autosize, 21, 0.8, , {doas_name}, SupplyAirTemperature, 12.8, 11.11, SupplyAirTemperature, 50, 30, , , None, , autosize, None;']
    elif sys_id == 32:
        objs = [f'HVACTemplate:Zone:WaterToAirHeatPump, {zone}, {t_name}, autosize, autosize, , , , {method}, {oa_p}, {oa_a}, {oa_z}, , {fan_sch}, DrawThrough, 0.39975, 75, 0.615, Coil:Cooling:WaterToAirHeatPump:EquationFit, autosize, autosize, 3.5, Coil:Heating:WaterToAirHeatPump:EquationFit, autosize, 4.2, , autosize, 2.5, 60, 60, {doas_name}, Electric, SupplyAirTemperature, 12.8, 11.11, SupplyAirTemperature, 50, 30, Cycling, , , None, , autosize;']
    elif sys_id == 33:
        objs = [f'HVACTemplate:Zone:VRF, {zone}, VRF_System, {t_name}, , , 1, autosize, autosize, autosize, autosize, autosize, autosize, autosize, {method}, {oa_p}, {oa_a}, {oa_z}, , , , {fan_sch}, BlowThrough, 0.39975, 75, 0.615, VariableRefrigerantFlowDX, , autosize, autosize, VariableRefrigerantFlowDX, , autosize, , , {doas_name}, SupplyAirTemperature, 12.8, 11.11, SupplyAirTemperature, 50, 30, Electric, , autosize;']
    elif sys_id == 34:
        objs = [f'HVACTemplate:Zone:VRF, {zone}, VRF_System, {t_name}, , , 1, autosize, autosize, autosize, autosize, autosize, autosize, autosize, {method}, {oa_p}, {oa_a}, {oa_z}, , , , {fan_sch}, BlowThrough, 0.39975, 75, 0.615, VariableRefrigerantFlowDX, , autosize, autosize, VariableRefrigerantFlowDX, , autosize, , , {doas_name}, SupplyAirTemperature, 12.8, 11.11, SupplyAirTemperature, 50, 30, None, , autosize;']
            
    return format_vertical(objs)

def generate_system(sys_id, base_filename, hvac_zones, zone_schedules, zone_oa, water_equip, output_prefix, fan_sch):
    """Generates the specific system file by appending templates to the base IDF."""
    sys_filename = f"{output_prefix}_System_{sys_id}.idf" if output_prefix else f"System_{sys_id}.idf"
    
    shutil.copyfile(base_filename, sys_filename)
    
    master_zone = hvac_zones[1] if len(hvac_zones) > 1 else (hvac_zones[0] if hvac_zones else 'Unknown_Zone')
    
    with open(sys_filename, 'a') as fid:
        fid.write(f"\n! === COMMON DHW OBJECTS ===\n{get_common_dhw(water_equip, master_zone)}")
        fid.write(f"\n! === SYSTEM {sys_id} GLOBAL OBJECTS ===\n{get_global_objects(sys_id, master_zone, fan_sch)}")
        fid.write(f"\n! === SYSTEM {sys_id} ZONE OBJECTS ===\n")
        
        for zone in hvac_zones:
            sch = zone_schedules.get(zone, {'heat': 'NECB-A-Thermostat Setpoint-Heating', 'cool': 'NECB-A-Thermostat Setpoint-Cooling'})
            fid.write(get_thermostat_template(zone, sch['heat'], sch['cool']))
            fid.write(get_zone_objects(sys_id, zone, zone_oa.get(zone, {}), fan_sch))

def generate_parametric_idfs(input_filename, output_prefix="", hvac_list=None):
    """Main dispatch function to process an IDF and generate selected HVAC system variants."""
    if hvac_list is None:
        hvac_list = list(range(1, 17))

    if not os.path.exists(input_filename):
        print(f"Error: Could not find {input_filename}")
        return

    with open(input_filename, 'r', encoding='utf-8', errors='ignore') as f:
        raw_idf_text = f.read()

    shortened_idf_text = shorten_idf_names(raw_idf_text)

    shortened_filename = "temp_shortened.idf"
    with open(shortened_filename, 'w', encoding='utf-8') as f:
        f.write(shortened_idf_text)

    hvac_zones, zone_schedules, zone_oa, water_equip, fan_sch = extract_hvac_and_thermostats(shortened_filename)

    if not hvac_zones:
        print("Error: No thermal zones found in the IDF.")
        if os.path.exists(shortened_filename): 
            os.remove(shortened_filename)
        return

    base_cleaned_filename = "temp_base_cleaned.idf"
    clean_idf_hvac(shortened_filename, base_cleaned_filename)
    
    for sys_id in hvac_list:
        generate_system(sys_id, base_cleaned_filename, hvac_zones, zone_schedules, zone_oa, water_equip, output_prefix, fan_sch)
        
    if os.path.exists(shortened_filename): os.remove(shortened_filename)
    if os.path.exists(base_cleaned_filename): os.remove(base_cleaned_filename)
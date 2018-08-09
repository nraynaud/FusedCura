import json
import os
from collections import namedtuple, OrderedDict
from configparser import ConfigParser
from pathlib import Path

from adsk.core import DropDownStyles, ValueInput
from .lib.appdirs import user_config_dir

fdmprinterfile = os.path.join(os.path.dirname(__file__), 'fdmprinter.def.json')
fdmextruderfile = os.path.join(os.path.dirname(__file__), 'fdmextruder.def.json')

useless_settings = {'machine_steps_per_mm_x', 'machine_steps_per_mm_y', 'machine_steps_per_mm_z',
                    'machine_steps_per_mm_e', 'machine_endstop_positive_direction_x',
                    'machine_endstop_positive_direction_y', 'machine_endstop_positive_direction_z',
                    'machine_heat_zone_length', 'machine_show_variants'}

config_dir = user_config_dir('FusedCura', 'nraynaud')
machine_preference_file_path = os.path.join(config_dir, 'machine.ini')
visibility_preference_file_path = os.path.join(config_dir, 'visibility.ini')
general_configuration_file_path = os.path.join(config_dir, 'fusedcura.ini')
print('config_dir', config_dir)
print('machine_preference_file_path', machine_preference_file_path)
print('visibility_preference_file_path', visibility_preference_file_path)
print('general_configuration_file_path', general_configuration_file_path)


def get_extruder_file_path(index):
    return os.path.join(config_dir, 'extuder%s.ini' % index)


def setting_tree_to_dict_and_default(settings):
    def get_settings_dict(node, dictionary):
        for k, val in node.items():
            if val['type'] != 'category':
                dictionary[k] = val
            if val.get('children'):
                get_settings_dict(val['children'], dictionary)

    setting_dict = dict()
    get_settings_dict(settings, setting_dict)
    defaults = {
        k: setting_types[v['type']].from_str(v['default_value']) if setting_types.get(v['type']) and v.get(
            'default_value') else v.get('default_value') for (k, v) in setting_dict.items()}
    return setting_dict, defaults


def remove_categories(settings):
    result = []
    for k, v in settings.items():
        if v['type'] != 'category':
            result.append((k, v))
        else:
            result.extend(remove_categories(v['children']))
    return result


def save_machine_config(changed_settings, setting_definitions):
    config = ConfigParser()
    config['machine'] = {k: setting_types[setting_definitions[k]['type']].to_str(v) for (k, v) in
                         changed_settings.items()}
    os.makedirs(config_dir, exist_ok=True)
    with open(machine_preference_file_path, 'w') as configfile:
        config.write(configfile)


def read_machine_settings(global_settings_definitions, global_settings_defaults):
    machine_settings = {}
    try:
        machine_config_parser = ConfigParser(interpolation=None, comment_prefixes=())
        with open(machine_preference_file_path) as f:
            machine_config_parser.read_file(f)
        machine_config_parser = machine_config_parser['machine']
        for (k, s) in machine_config_parser.items():
            value = setting_types[global_settings_definitions[k]['type']].from_str(s)
            collect_changed_setting_if_different_from_parent(k, value, [global_settings_defaults], machine_settings)
    except OSError:
        pass
    return machine_settings


def save_extruder_config(index, changed_settings, setting_definitions):
    config = ConfigParser()
    config['extruder'] = {k: setting_types[setting_definitions[k]['type']].to_str(v) for (k, v) in
                          changed_settings.items()}
    os.makedirs(config_dir, exist_ok=True)
    with open(get_extruder_file_path(index), 'w') as configfile:
        config.write(configfile)


def read_extruder_config(index, global_settings_definitions=None, global_settings_defaults=None):
    if global_settings_definitions is None:
        global_settings_definitions = setting_tree_to_dict_and_default(get_config(fdmextruderfile, useless_settings))[0]
    extruder_settings = {}
    try:
        print('***global_settings_definitions', global_settings_definitions)
        print('***setting_types', setting_types)
        extruder_settings_parser = ConfigParser(interpolation=None, comment_prefixes=())
        with open(get_extruder_file_path(index)) as f:
            extruder_settings_parser.read_file(f)
        extruder_settings_parser = extruder_settings_parser['extruder']
        for (k, s) in extruder_settings_parser.items():
            value = setting_types[global_settings_definitions[k]['type']].from_str(s)
            if global_settings_defaults is not None:
                collect_changed_setting_if_different_from_parent(k, value, [global_settings_defaults],
                                                                 extruder_settings)
            else:
                extruder_settings[k] = value
    except OSError:
        pass
    return extruder_settings


def save_visibility(visibilities):
    config = ConfigParser()
    config['visibilities'] = visibilities
    os.makedirs(config_dir, exist_ok=True)
    with open(visibility_preference_file_path, 'w') as configfile:
        config.write(configfile)


def read_visibility():
    visibility = {k: True for k in defaut_visible_settings}
    visibility_config = ConfigParser(comment_prefixes=())
    try:
        with open(visibility_preference_file_path) as f:
            visibility_config.read_file(f)
        visibility.update({k: bool(v) for k, v in visibility_config['visibilities'].items()})
    except OSError:
        pass
    return visibility


def save_configuration(configuration):
    config = ConfigParser()
    config['configuration'] = configuration
    os.makedirs(config_dir, exist_ok=True)
    with open(general_configuration_file_path, 'w') as configfile:
        config.write(configfile)


def read_configuration():
    configuration = ConfigParser(comment_prefixes=())
    try:
        with open(general_configuration_file_path) as f:
            configuration.read_file(f)
        return configuration['configuration']
    except OSError:
        pass
    return None


def add_enum_input(key, node, _inputs, value):
    new_input = _inputs.addDropDownCommandInput(key, node['label'], DropDownStyles.TextListDropDownStyle)
    for (opk, op) in node['options'].items():
        item = new_input.listItems.add(op, opk == value)
        item.id = opk
    return new_input


def collect_changed_setting_if_different_from_parent(key, value, stack_of_dict, collection_dict):
    for parent_dict in reversed(stack_of_dict):
        if key in parent_dict:
            parent_val = parent_dict[key]
            if parent_val == value:
                if key in collection_dict:
                    del collection_dict[key]
            else:
                collection_dict[key] = value
            break


def find_setting_in_stack(key, stack_of_dict):
    for parent_dict in reversed(stack_of_dict):
        if key in parent_dict:
            return parent_dict[key]


def get_config(file_name, useless_set=set()):
    preferred_order = ['resolution', 'shell', 'infill', 'material', 'speed', 'cooling', 'support', 'travel',
                       'machine_settings', 'experimental', 'platform_adhesion']
    file_content = Path(file_name).read_text()
    loaded = json.JSONDecoder(object_pairs_hook=OrderedDict).decode(file_content)['settings']
    other_keys = [k for k in loaded.keys() if k not in set(preferred_order)]
    re_ordered_dict = OrderedDict([(k, loaded[k]) for k in preferred_order + other_keys if k in loaded])

    def filter_useless(node):
        if node.get('children'):
            filtered_children = OrderedDict(
                [(k, filter_useless(v)) for k, v in node['children'].items() if k not in useless_set])
            return {**{k: v for k, v in node.items() if k != 'children'}, 'children': filtered_children}
        return node

    return OrderedDict([(k, filter_useless(v)) for (k, v) in re_ordered_dict.items()])


SettingType = namedtuple('SettingType', ['to_input', 'from_input', 'to_str', 'from_str'])

setting_types = {
    'bool': SettingType(
        to_input=lambda k, desc, inp, v: inp.addBoolValueInput(k, desc['label'], True, '', bool(v)),
        to_str=lambda v: str(v).lower(), from_str=bool, from_input=lambda i, node: i.value),
    'float': SettingType(
        to_input=lambda k, desc, inp, v: inp.addValueInput(k, desc['label'], '',
                                                           ValueInput.createByReal(float(v) if v else 0), ),
        to_str=str, from_str=float, from_input=lambda i, node: i.value),
    'int': SettingType(
        to_input=lambda k, desc, inp, v: inp.addIntegerSpinnerCommandInput(k, desc['label'], 0, 300000, 1,
                                                                           int(v) if v else 0),
        to_str=str, from_str=int, from_input=lambda i, node: i.value),
    'str': SettingType(
        to_input=lambda k, desc, inp, v: inp.addStringValueInput(k, desc['label'], v if v else ''),
        to_str=lambda v: v, from_str=lambda v: v, from_input=lambda i, node: i.value),
    'enum': SettingType(to_input=add_enum_input, to_str=str, from_str=str,
                        from_input=lambda i, node:
                        [k for (k, v) in node['options'].items() if v == i.selectedItem.name][0]),
    'optional_extruder': SettingType(
        to_input=lambda k, desc, inp, v: inp.addIntegerSpinnerCommandInput(k, desc['label'], -1, 16,
                                                                           1, int(v) if v else 0),
        to_str=str, from_str=int, from_input=lambda i, node: i.value),
    'extruder': SettingType(
        to_input=lambda k, desc, inp, v: inp.addIntegerSpinnerCommandInput(k, desc['label'], 0, 16, 1,
                                                                           int(v) if v else 0),
        to_str=str, from_str=int, from_input=lambda i, node: i.value),
    '[int]': SettingType(
        to_input=lambda k, desc, inp, v: inp.addStringValueInput(k, desc['label'], v if v else ''),
        to_str=str, from_str=str, from_input=lambda i, node: i.value),
}

defaut_visible_settings = {'layer_height', 'layer_height_0', 'line_width', 'wall_line_width', 'wall_line_width_0',
                           'wall_line_width_x', 'skin_line_width', 'infill_line_width',
                           'initial_layer_line_width_factor', 'wall_extruder_nr', 'wall_0_extruder_nr',
                           'wall_x_extruder_nr', 'wall_thickness', 'wall_line_count', 'top_bottom_extruder_nr',
                           'top_bottom_thickness', 'top_thickness', 'top_layers', 'bottom_thickness', 'bottom_layers',
                           'optimize_wall_printing_order', 'fill_perimeter_gaps', 'xy_offset', 'ironing_enabled',
                           'infill_extruder_nr', 'infill_sparse_density', 'infill_line_distance', 'infill_pattern',
                           'infill_overlap', 'infill_sparse_thickness', 'gradual_infill_steps',
                           'material_print_temperature', 'material_print_temperature_layer_0',
                           'material_initial_print_temperature', 'material_final_print_temperature',
                           'material_bed_temperature', 'material_bed_temperature_layer_0', 'retraction_enable',
                           'retract_at_layer_change', 'retraction_amount', 'retraction_speed',
                           'material_standby_temperature', 'speed_print', 'speed_infill', 'speed_wall', 'speed_wall_0',
                           'speed_wall_x', 'speed_topbottom', 'speed_support', 'speed_prime_tower', 'speed_travel',
                           'speed_layer_0', 'skirt_brim_speed', 'acceleration_enabled', 'jerk_enabled',
                           'retraction_combing', 'travel_avoid_other_parts', 'travel_avoid_supports',
                           'travel_avoid_distance', 'retraction_hop_enabled', 'retraction_hop_only_when_collides',
                           'retraction_hop', 'retraction_hop_after_extruder_switch', 'cool_fan_enabled',
                           'cool_fan_speed', 'cool_fan_speed_min', 'cool_fan_speed_max',
                           'cool_min_layer_time_fan_speed_max', 'cool_fan_speed_0', 'cool_fan_full_at_height',
                           'cool_fan_full_layer', 'cool_min_layer_time', 'cool_min_speed', 'cool_lift_head',
                           'support_enable', 'support_extruder_nr', 'support_infill_extruder_nr',
                           'support_extruder_nr_layer_0', 'support_interface_extruder_nr', 'support_type',
                           'support_angle', 'support_pattern', 'support_infill_rate', 'support_offset',
                           'support_infill_sparse_thickness', 'gradual_support_infill_steps',
                           'gradual_support_infill_step_height', 'support_interface_enable', 'support_roof_enable',
                           'support_bottom_enable', 'prime_blob_enable', 'adhesion_type', 'adhesion_extruder_nr',
                           'skirt_line_count', 'brim_width', 'brim_line_count', 'brim_outside_only',
                           'prime_tower_enable', 'prime_tower_position_x', 'prime_tower_position_y',
                           'prime_tower_purge_volume', 'print_sequence', 'magic_mesh_surface_mode', 'magic_spiralize',
                           'smooth_spiralized_contours', 'conical_overhang_enabled', 'support_conical_enabled',
                           'adaptive_layer_height_enabled'}

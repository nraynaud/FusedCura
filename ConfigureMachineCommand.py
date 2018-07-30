from collections import OrderedDict

from adsk.core import Command, CommandInputs
from .Fusion360Utilities.Fusion360CommandBase import Fusion360CommandBase
from .Fusion360Utilities.Fusion360Utilities import AppObjects
from .curaengine import get_config
from .settings import setting_types, collect_changed_setting_if_different_from_parent, setting_tree_to_dict_and_default, \
    useless_settings, save_machine_config, find_setting_in_stack, \
    read_machine_settings, read_configuration
from .util import recursive_inputs

machine_settings_order = ['machine_name', 'machine_gcode_flavor', 'machine_width', 'machine_depth', 'machine_height',
                          'machine_heated_bed', 'machine_nozzle_size']

time_estimate_settings = ['machine_minimum_feedrate', 'machine_max_feedrate_x', 'machine_max_feedrate_y',
                          'machine_max_feedrate_z', 'machine_max_feedrate_e', 'machine_max_acceleration_x',
                          'machine_max_acceleration_y', 'machine_max_acceleration_z', 'machine_max_acceleration_e',
                          'machine_acceleration', 'machine_max_jerk_xy', 'machine_max_jerk_z', 'machine_max_jerk_e']


class ConfigureMachineCommand(Fusion360CommandBase):

    def on_input_changed(self, command: Command, inputs: CommandInputs, changed_input, input_values):
        setting_key = changed_input.id
        if setting_key.endswith('_machine'):
            setting_key = setting_key[:-len('_machine')]
            node = self.global_settings_definitions[setting_key]
            node_type = setting_types[node['type']]
            if setting_key in {'machine_start_gcode', 'machine_end_gcode'}:
                value = changed_input.text
            else:
                value = node_type.from_input(changed_input, node)
            collect_changed_setting_if_different_from_parent(setting_key, value, [self.global_settings_defaults],
                                                             self.changed_machine_settings)

    def on_execute(self, command: Command, inputs: CommandInputs, args, input_values):
        save_machine_config(self.changed_machine_settings, self.global_settings_definitions)

    def on_create(self, command: Command, inputs: CommandInputs):
        configuration = read_configuration()
        if not configuration:
            AppObjects().ui.commandDefinitions.itemById('ConfigureFusedCuraCmd').execute()
        settings = get_config(configuration, useless_settings)
        (self.global_settings_definitions, self.global_settings_defaults) = setting_tree_to_dict_and_default(settings)
        self.changed_machine_settings = read_machine_settings(self.global_settings_definitions,
                                                              self.global_settings_defaults)
        self.machine_inputs = dict()

        def machine_type_creator(k, node, _inputs):
            if node['type'] in setting_types:
                value = find_setting_in_stack(k, [self.global_settings_defaults, self.changed_machine_settings])
                input = setting_types[node['type']].to_input(k + '_machine', node, _inputs, value)
                self.machine_inputs[k] = input
                return input

        machine_settings = settings['machine_settings']['children']
        machine_keys = machine_settings_order + [k for k in machine_settings.keys() if k not in machine_settings_order]
        ordered_machine_settings = OrderedDict(
            [(k, machine_settings[k]) for k in machine_keys if
             k not in time_estimate_settings + ['machine_start_gcode', 'machine_end_gcode']])
        ordered_machine_settings['time_estimate'] = {'type': 'category', 'label': 'Time Estimation',
                                                     'description': 'Settings used for time estimate only',
                                                     'children': OrderedDict(
                                                         [(k, machine_settings[k]) for k in time_estimate_settings])}
        general_tab = inputs.addTabCommandInput('general_tab', 'General', '')
        recursive_inputs(ordered_machine_settings, general_tab.children, machine_type_creator)
        general_tab.children.itemById('time_estimate').isExpanded = False
        start_gcode_tab = inputs.addTabCommandInput('start_tab', 'Start GCode', '')
        warning_text = 'Please set your temperatures here. Ex:\nM109 S{material_print_temperature}\nM190 S{material_bed_temperature}'
        start_gcode_warning = start_gcode_tab.children.addTextBoxCommandInput('lol1', 'lol', warning_text, 3, True)
        start_gcode_warning.isFullWidth = True
        start_gcode_initial_value = find_setting_in_stack('machine_start_gcode', [self.global_settings_defaults,
                                                                                  self.changed_machine_settings])
        start_gcode_input = start_gcode_tab.children.addTextBoxCommandInput('machine_start_gcode_machine',
                                                                            'Start GCode',
                                                                            start_gcode_initial_value, 20, False)
        start_gcode_input.isFullWidth = True
        end_gcode_tab = inputs.addTabCommandInput('end_tab', 'End GCode', '')
        end_gcode_initial_value = find_setting_in_stack('machine_end_gcode', [self.global_settings_defaults,
                                                                              self.changed_machine_settings])
        end_gcode_input = end_gcode_tab.children.addTextBoxCommandInput('machine_end_gcode_machine', 'End GCode',
                                                                        end_gcode_initial_value, 20, False)
        end_gcode_input.isFullWidth = True

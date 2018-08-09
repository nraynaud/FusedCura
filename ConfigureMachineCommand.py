from collections import OrderedDict, defaultdict
from itertools import zip_longest
from uuid import uuid4

from adsk.core import Command, CommandInputs
from .Fusion360Utilities.Fusion360CommandBase import Fusion360CommandBase
from .Fusion360Utilities.Fusion360Utilities import AppObjects
from .settings import setting_types, collect_changed_setting_if_different_from_parent, setting_tree_to_dict_and_default, \
    useless_settings, save_machine_config, find_setting_in_stack, \
    read_machine_settings, fdmprinterfile, fdmextruderfile, save_extruder_config, read_extruder_config, \
    remove_categories, get_config
from .util import recursive_inputs, display_machine

machine_settings_order = ['machine_name', 'machine_gcode_flavor', 'machine_width', 'machine_depth', 'machine_height',
                          'machine_heated_bed', 'machine_nozzle_size']

time_estimate_settings = ['machine_minimum_feedrate', 'machine_max_feedrate_x', 'machine_max_feedrate_y',
                          'machine_max_feedrate_z', 'machine_max_feedrate_e', 'machine_max_acceleration_x',
                          'machine_max_acceleration_y', 'machine_max_acceleration_z', 'machine_max_acceleration_e',
                          'machine_acceleration', 'machine_max_jerk_xy', 'machine_max_jerk_z', 'machine_max_jerk_e']


class ConfigureMachineCommand(Fusion360CommandBase):

    def on_preview(self, command: Command, inputs: CommandInputs, args, input_values):
        ao = AppObjects()
        graphics = ao.root_comp.customGraphicsGroups.add()
        max_x = find_setting_in_stack('machine_width', self.settings_stack) / 10
        max_y = find_setting_in_stack('machine_depth', self.settings_stack) / 10
        max_z = find_setting_in_stack('machine_height', self.settings_stack) / 10
        center_is_zero = find_setting_in_stack('machine_center_is_zero', self.settings_stack)
        display_machine(graphics, max_x, max_y, max_z, center_is_zero)

    def on_input_changed(self, command: Command, inputs: CommandInputs, changed_input, input_values):
        setting_key = changed_input.id
        if setting_key.endswith('_extruder'):
            setting_key = setting_key[:-len('_extruder')]
            underscore_pos = setting_key.rfind('_')
            index = int(setting_key[underscore_pos + 1:])
            setting_key = setting_key[:underscore_pos]
            node = self.extruder_settings_definitions[setting_key]
            node_type = setting_types[node['type']]
            value = node_type.from_input(changed_input, node)
            collect_changed_setting_if_different_from_parent(setting_key, value, [self.global_settings_defaults],
                                                             self.changed_extruder_settings[index])
        elif setting_key.endswith('_machine'):
            setting_key = setting_key[:-len('_machine')]
            node = self.global_settings_definitions[setting_key]
            node_type = setting_types[node['type']]
            if setting_key in {'machine_start_gcode', 'machine_end_gcode'}:
                value = changed_input.text
            else:
                value = node_type.from_input(changed_input, node)
            collect_changed_setting_if_different_from_parent(setting_key, value, [self.global_settings_defaults],
                                                             self.changed_machine_settings)
        if setting_key == 'machine_extruder_count':
            self.update_rows()

    def on_execute(self, command: Command, inputs: CommandInputs, args, input_values):
        save_machine_config(self.changed_machine_settings, self.global_settings_definitions)
        for i in range(find_setting_in_stack('machine_extruder_count', self.settings_stack)):
            save_extruder_config(i, self.changed_extruder_settings[i], self.extruder_settings_definitions)

    def on_create(self, command: Command, inputs: CommandInputs):
        settings = get_config(fdmprinterfile, useless_settings)
        (self.global_settings_definitions, self.global_settings_defaults) = setting_tree_to_dict_and_default(settings)
        self.changed_machine_settings = read_machine_settings(self.global_settings_definitions,
                                                              self.global_settings_defaults)
        self.machine_inputs = dict()
        self.settings_stack = [self.global_settings_defaults, self.changed_machine_settings]

        def create_creator(id_suffix, stack):
            def machine_type_creator(k, node, _inputs):
                if node['type'] in setting_types:
                    value = find_setting_in_stack(k, stack)
                    input = setting_types[node['type']].to_input(k + id_suffix, node, _inputs, value)
                    self.machine_inputs[k] = input
                    return input

            return machine_type_creator

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
        recursive_inputs(ordered_machine_settings, general_tab.children,
                         create_creator('_machine', self.settings_stack))
        general_tab.children.itemById('time_estimate').isExpanded = False
        start_gcode_tab = inputs.addTabCommandInput('start_tab', 'Start GCode', '')
        warning_text = 'Please set your temperatures here. Ex:\nM109 S{material_print_temperature}\n'
        warning_text += 'M190 S{material_bed_temperature}'
        start_gcode_warning = start_gcode_tab.children.addTextBoxCommandInput('lol1', 'lol', warning_text, 3, True)
        start_gcode_warning.isFullWidth = True
        start_gcode_initial_value = find_setting_in_stack('machine_start_gcode', self.settings_stack)
        start_gcode_input = start_gcode_tab.children.addTextBoxCommandInput('machine_start_gcode_machine',
                                                                            'Start GCode',
                                                                            start_gcode_initial_value, 20, False)
        start_gcode_input.isFullWidth = True
        end_gcode_tab = inputs.addTabCommandInput('end_tab', 'End GCode', '')
        end_gcode_initial_value = find_setting_in_stack('machine_end_gcode', self.settings_stack)
        end_gcode_input = end_gcode_tab.children.addTextBoxCommandInput('machine_end_gcode_machine', 'End GCode',
                                                                        end_gcode_initial_value, 20, False)
        end_gcode_input.isFullWidth = True
        self.extruder_settings = get_config(fdmextruderfile, useless_settings)
        (self.extruder_settings_definitions, self.extruder_settings_defaults) = setting_tree_to_dict_and_default(
            self.extruder_settings)
        extruder_count = find_setting_in_stack('machine_extruder_count', self.settings_stack)
        self.changed_extruder_settings = defaultdict(dict)
        for index in range(extruder_count):
            extruder_conf = read_extruder_config(index, self.extruder_settings_definitions,
                                                 self.extruder_settings_defaults)
            self.changed_extruder_settings[index] = extruder_conf
        self.extruder_tabs = []
        extruder_tab = inputs.addTabCommandInput('extruder_tab', 'Extruders', '')
        self.extruder_table = extruder_tab.children.addTableCommandInput('table', 'Table', 2, '1')
        self.extruder_inputs = []
        self.update_rows()

    def update_rows(self):
        new_extuder_count = find_setting_in_stack('machine_extruder_count', self.settings_stack)
        table = self.extruder_table
        inputs = table.commandInputs
        self.table_command_inputs = inputs
        flat_settings = OrderedDict(remove_categories(self.extruder_settings))
        remove_rows = []
        add_rows = []
        for index, extruder_inputs_index in zip_longest(range(new_extuder_count), range(len(self.extruder_inputs))):
            if index is None:
                remove_rows.append(extruder_inputs_index)
            elif extruder_inputs_index is None:
                add_rows.append(index)
        for extruder_inputs_index in reversed(remove_rows):
            extruder_inputs = self.extruder_inputs[extruder_inputs_index]
            for i in extruder_inputs:
                (returnValue, row, column, rowSpan, columnSpan) = table.getPosition(i)
                table.deleteRow(row)
            del self.extruder_inputs[extruder_inputs_index]
        for index in add_rows:
            next_table_row = table.rowCount
            extruder_inputs = []
            self.extruder_inputs.append(extruder_inputs)

            def create_label(text):
                new_input = inputs.addStringValueInput('a' + str(uuid4()), '', text)
                new_input.isReadOnly = True
                return new_input

            label = create_label('Extruder ' + str(index))
            extruder_inputs.append(label)
            table.addCommandInput(label, next_table_row, 0)
            table.addCommandInput(create_label('======='), next_table_row, 1)
            extruder_conf = self.changed_extruder_settings[index]
            extruder_conf['extruder_nr'] = index
            stack = [*self.settings_stack, extruder_conf]

            def extruder_type_creator(k, node, _inputs):
                if node['type'] in setting_types:
                    value = find_setting_in_stack(k, stack)
                    input = setting_types[node['type']].to_input('%s_%s_extruder' % (k, str(index)), node, _inputs,
                                                                 value)
                    extruder_inputs.append(input)
                    next_table_row = table.rowCount
                    table.addCommandInput(create_label(node['label']), next_table_row, 0)
                    table.addCommandInput(input, next_table_row, 1)
                    return input

            recursive_inputs(flat_settings, inputs, extruder_type_creator)

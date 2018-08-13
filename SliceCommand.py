import array
import itertools
import json
import shutil
import tempfile
import threading
import traceback
from collections import defaultdict, Mapping
from copy import deepcopy
from string import Formatter
from time import time

from adsk.core import Command, Vector3D, CommandInputs, DialogResults, CustomEventArgs, CustomEventHandler, \
    TableCommandInput, Line3D, Point3D
from adsk.fusion import BRepBody, CustomGraphicsCoordinates, TemporaryBRepManager
from .Fusion360Utilities.Fusion360CommandBase import Fusion360CommandBase
from .Fusion360Utilities.Fusion360Utilities import AppObjects
from .curaengine import run_engine, parse_segment
from .messages import Slice, dict_to_setting_list, ObjectList, Object, LineType, Extruder
from .settings import setting_types, collect_changed_setting_if_different_from_parent, \
    setting_tree_to_dict_and_default, useless_settings, \
    find_setting_in_stack, save_visibility, read_visibility, read_machine_settings, read_configuration, fdmprinterfile, \
    read_extruder_config, get_config
from .util import event, recursive_inputs, display_machine, create_visibility_checkboxes

# https://gist.github.com/mRB0/740c25fdae3dc0b0ee7a


ao = AppObjects()

engine_event_id = 'ENGINE_CUSTOM_EVENT'


class CancelException(Exception):
    pass


def run_engine_in_other_thread(message, endpoint):
    def fire_if_not_canceled(info):
        handle_cancel()
        AppObjects().app.fireCustomEvent(engine_event_id, info)

    def handle_cancel():
        if endpoint.get('canceled'):
            raise CancelException

    previous_time = int(time() / 2)
    prefix = None
    with tempfile.TemporaryFile() as gcode_collector:
        def on_message(raw_received, received_type):
            nonlocal previous_time, prefix
            new_time = int(time() / 5)
            if previous_time != new_time:
                fire_if_not_canceled(received_type.symbol)
                previous_time = new_time
            handle_cancel()
            print(received_type.symbol)
            if received_type.symbol == 'cura.proto.PrintTimeMaterialEstimates':
                endpoint['estimates'] = received_type.loads(raw_received)
                complete_gcode = tempfile.NamedTemporaryFile()
                complete_gcode.write(prefix)
                gcode_collector.seek(0)
                shutil.copyfileobj(gcode_collector, complete_gcode)
                endpoint['gcode_file'] = complete_gcode
                complete_gcode.seek(0)
            if received_type.symbol == 'cura.proto.GCodePrefix':
                prefix = received_type.loads(raw_received).data
            if received_type.symbol == 'cura.proto.GCodeLayer':
                data = received_type.loads(raw_received).data
                gcode_collector.write(data)
            if received_type.symbol == 'cura.proto.SlicingFinished':
                endpoint['done'] = True
                fire_if_not_canceled('done')
            if received_type.symbol == 'cura.proto.LayerOptimized':
                line_strips_per_type = defaultdict(list)
                layer = received_type.loads(raw_received)
                for segment in layer.path_segment:
                    coord_iterator = iter(parse_segment(segment, layer.height))
                    current_list = []
                    current_type = None
                    for type, point_x in zip(segment.line_type, coord_iterator):
                        point = point_x / 10, next(coord_iterator) / 10, next(coord_iterator) / 10
                        if len(current_list):
                            current_list.extend(point)
                        if type != current_type:
                            current_list = []
                            current_list.extend(point)
                            current_type = type
                            line_strips_per_type[current_type].append(current_list)
                endpoint['layers'][layer.id] = {'height': layer.height, 'thickness': layer.thickness, 'by_type': {}}
                for type, strips in line_strips_per_type.items():
                    endpoint['layers'][layer.id]['by_type'][type] = {
                        'strip_lengths': [len(strip) // 3 for strip in strips],
                        'giant_strip': [coord for strip in strips for coord in strip]
                    }
                fire_if_not_canceled('layer|' + str(layer.id))

        try:
            run_engine(message, on_message, handle_cancel)
        except CancelException:
            print('CANCEL')
            return
        except:
            fire_if_not_canceled('exception')
            endpoint['exception'] = traceback.format_exc()
            print('exception', traceback.format_exc())
            traceback.print_exc()


def get_message_and_mesh_for_engine(selected_bodies, settings, quality, extruder_count):
    slice_msg = Slice()
    coords_collector = []
    meshes = []
    for selected_body in selected_bodies:
        calculator = selected_body.meshManager.createMeshCalculator()
        calculator.setQuality(quality)
        mesh = calculator.calculate()
        meshes.append(mesh)
        coords = mesh.nodeCoordinatesAsFloat
        coords_collector += [coords[mi * 3 + pi] * 10 for (mi, pi) in itertools.product(mesh.nodeIndices, [0, 1, 2])]
    slice_msg.global_settings = settings
    extruders = []
    for i in range(extruder_count):
        extruder = Extruder()
        extruder.id = i
        extruder.settings = dict_to_setting_list(read_extruder_config(i))
        extruders.append(extruder)
    slice_msg.extruders = extruders
    object_list = ObjectList()
    obj = Object()
    obj.id = 1
    obj.vertices = array.array('f', coords_collector).tobytes()
    object_list.objects = [obj]
    slice_msg.object_lists = [object_list]
    return slice_msg, meshes


class GCodeFormatter(Formatter):
    def __init__(self):
        self.prepend_dict = {}

    def check_unused_args(self, used_args, args, kwargs):
        material_temp_set = {"material_print_temperature", "material_print_temperature_layer_0",
                             "default_material_print_temperature", "material_initial_print_temperature",
                             "material_final_print_temperature", "material_standby_temperature"}
        self.prepend_dict['material_print_temp_prepend'] = not (material_temp_set & used_args)
        bed_temp_set = {"material_bed_temperature", "material_bed_temperature_layer_0"}
        self.prepend_dict['material_bed_temp_prepend'] = not (bed_temp_set & used_args)


def compute_layer_type_preview(layer, layer_id, type, precomputed_layers):
    manager = TemporaryBRepManager.get()
    data = layer['by_type'][type]
    if type not in precomputed_layers[layer_id]:
        index = 0
        bodies = []
        lines = []
        for strip_len in data['strip_lengths']:
            current_poly = data['giant_strip'][index * 3:(index + strip_len) * 3]
            index += strip_len
            iterator = iter(current_poly)
            points = [Point3D.create(x, next(iterator), next(iterator)) for x in iterator]
            previous_point = None
            for point in points:
                if previous_point:
                    lines.append(Line3D.create(previous_point, point))
                previous_point = point
        if len(lines):
            bodies.append(manager.createWireFromCurves(lines, True)[0])
        precomputed_layers[layer_id][type] = bodies


class SliceCommand(Fusion360CommandBase):

    def cancel_engine(self):
        if self.engine_endpoint:
            self.engine_endpoint['canceled'] = True
            self.engine_event.remove(self.engine_endpoint['handler'])

    def on_preview(self, command: Command, inputs: CommandInputs, args, input_values):
        stack = self.settings_stack
        max_x = find_setting_in_stack('machine_width', stack) / 10
        max_y = find_setting_in_stack('machine_depth', stack) / 10
        max_z = find_setting_in_stack('machine_height', stack) / 10
        center_is_zero = find_setting_in_stack('machine_center_is_zero', stack)
        display_machine(self.graphics, max_x, max_y, max_z, center_is_zero)
        stacked_dict = {**self.global_settings_defaults, **self.computed_values, **self.changed_machine_settings,
                        **self.changed_settings}
        interpolated_end_gcode = Formatter().vformat(stacked_dict['machine_end_gcode'], [], kwargs=stacked_dict)
        f = GCodeFormatter()
        interpolated_start_gcode = f.vformat(stacked_dict['machine_start_gcode'], [], kwargs=stacked_dict)
        last_minute_swaps = {'machine_start_gcode': interpolated_start_gcode,
                             'machine_end_gcode': interpolated_end_gcode, **f.prepend_dict}
        settings = deepcopy({**self.computed_values, **self.changed_machine_settings, **self.changed_settings,
                             **last_minute_swaps})
        bodies = [BRepBody.cast(b) for b in input_values['selection']]
        slider = self.layer_slider
        if settings == self.running_settings and self.running_models == bodies:
            if self.engine_endpoint and self.engine_endpoint['done']:
                layer_keys = self.engine_endpoint['layers'].keys()
                slider.minimumValue = min(layer_keys)
                slider.maximumValue = max(layer_keys)
                linework_group = self.graphics.addGroup()
                if not find_setting_in_stack('machine_center_is_zero', stack):
                    transform = linework_group.transform
                    transform.translation = Vector3D.create(-find_setting_in_stack('machine_width', stack) / 20,
                                                            -find_setting_in_stack('machine_depth', stack) / 20, 0)
                    linework_group.transform = transform
                for body in bodies:
                    body.isVisible = False
                for mesh in self.engine_endpoint['mesh']:
                    self.graphics.addMesh(CustomGraphicsCoordinates.create(mesh.nodeCoordinatesAsDouble),
                                          mesh.nodeIndices, [], []).setOpacity(0.2, True)
                cached_layers = self.engine_endpoint['precomputed_layers']
                layer_range = set(range(slider.valueOne, slider.valueTwo))
                line_types = {v.value for v in LineType if
                              v in self.layer_type_inputs and self.layer_type_inputs[v].value}
                for id in layer_range.intersection(self.engine_endpoint['layers'].keys()):
                    cached_layer = cached_layers[id]
                    original_layer = self.engine_endpoint['layers'][id]
                    for type in line_types.intersection(original_layer['by_type'].keys()):
                        compute_layer_type_preview(original_layer, id, type, cached_layers)
                        for body in cached_layer[type]:
                            new_line = linework_group.addBRepBody(body)
                            new_line.depthPriority = 2

                AppObjects().app.activeViewport.refresh()
                self.info_box.text = 'preview visible'
            return
        self.running_settings = settings
        print('setting', settings)
        self.running_models = bodies
        for body in bodies:
            body.isVisible = False
        extruder_count = find_setting_in_stack('machine_extruder_count', stack)
        (slice_msg, meshes) = get_message_and_mesh_for_engine(bodies, dict_to_setting_list(settings), 15,
                                                              extruder_count)

        for mesh in meshes:
            self.graphics.addMesh(CustomGraphicsCoordinates.create(mesh.nodeCoordinatesAsDouble), mesh.nodeIndices, [],
                                  [])

        def on_engine(args: CustomEventArgs):
            layer_keys = self.engine_endpoint['layers'].keys()
            if len(layer_keys):
                slider.minimumValue = min(layer_keys)
                slider.maximumValue = max(layer_keys)
            if args.additionalInfo == 'done':
                self.cancel_engine()
                command.doExecutePreview()
            if args.additionalInfo == 'exception':
                AppObjects().ui.messageBox(repr(endpoint['exception']))

        handler = event(CustomEventHandler, on_engine)
        endpoint = dict(handler=handler, canceled=False, done=False, estimates={}, layers={}, gcode_file=None,
                        exception=None, mesh=meshes, precomputed_layers=defaultdict(dict))
        self.cancel_engine()
        self.engine_event.add(handler)
        self.engine_endpoint = endpoint
        self.info_box.text = 'computing preview ...'
        threading.Thread(target=run_engine_in_other_thread, args=[slice_msg, endpoint]).start()

    def on_destroy(self, command: Command, inputs: CommandInputs, reason, input_values):
        AppObjects().app.unregisterCustomEvent(engine_event_id)
        try:
            self.cancel_engine()
            save_visibility(self.visibilities)
        except AttributeError:
            pass

    def on_input_changed(self, command: Command, inputs: CommandInputs, changed_input, input_values):
        if self.file_input.id == changed_input.id:
            dialog = AppObjects().ui.createFileDialog()
            dialog.title = 'Save GCode file'
            dialog.filter = 'GCode files (*.gcode)'
            dialog.initialFilename = 'out'
            accessible = dialog.showSave()
            if accessible == DialogResults.DialogOK:
                self.file_input.text = dialog.filename
                self.gcode_file = dialog.filename
        else:
            setting_key = changed_input.id
            if setting_key in self.global_settings_definitions:
                node = self.global_settings_definitions[setting_key]
                node_type = setting_types[node['type']]
                value = node_type.from_input(changed_input, node)
                collect_changed_setting_if_different_from_parent(setting_key, value, [self.global_settings_defaults,
                                                                                      self.changed_machine_settings],
                                                                 self.changed_settings)

                def get_transitive_dependants(key):
                    direct = self.global_settings_definitions[key]['dependants']
                    indirects = {v for sub_key in direct for v in get_transitive_dependants(sub_key)}
                    return {*direct, *indirects}

                def input_value(k):
                    node = self.global_settings_definitions[k]
                    return setting_types[node['type']].from_input(self.input_dict[k], node)

                dependants = get_transitive_dependants(setting_key)
                changes = {k: (input_value(k), find_setting_in_stack(k, self.settings_stack)) for k in dependants if
                           k in self.input_dict}
                for k, v in changes.items():
                    if v[0] != v[1] and k not in self.changed_machine_settings:
                        node = self.global_settings_definitions[k]
                        setting_types[node['type']].set_value(self.input_dict[k], v[1], node)
            if setting_key.endswith('_vis'):
                vis_key = setting_key[:-len('_vis')]
                component = self.input_dict.get(vis_key)
                if component:
                    component.isVisible = changed_input.value
                    self.visibilities[vis_key] = changed_input.value

    def on_execute(self, command: Command, inputs: CommandInputs, args, input_values):
        attributes = AppObjects().app.activeDocument.attributes
        attributes.add('FusedCura', 'settings', json.dumps(self.changed_settings))
        # noinspection PyArgumentList
        for attr in AppObjects().design.findAttributes('FusedCura', 'selected_for_printing'):
            if attr.value == 'True' and attr.parent not in input_values['selection']:
                attr.deleteMe()
        for entity in input_values['selection']:
            entity.attributes.add('FusedCura', 'selected_for_printing', 'True')
        if self.gcode_file is not None and self.engine_endpoint and self.engine_endpoint['done']:
            with open(self.gcode_file, 'wb') as out:
                shutil.copyfileobj(self.engine_endpoint['gcode_file'], out)

    def on_create(self, command: Command, inputs: CommandInputs):
        command.isExecutedWhenPreEmpted = False
        command.isAutoExecute = False
        self.engine_event = AppObjects().app.registerCustomEvent(engine_event_id)
        self.engine_endpoint = None
        configuration = read_configuration()
        if not configuration:
            AppObjects().ui.commandDefinitions.itemById('ConfigureFusedCuraCmd').execute()
            return
        self.changed_settings = {}
        self.running_settings = {}
        self.running_models = None
        self.graphics = AppObjects().root_comp.customGraphicsGroups.add()
        self.visibilities = read_visibility()
        self.gcode_file = None

        settings_attribute = AppObjects().app.activeDocument.attributes.itemByName('FusedCura', 'settings')
        if settings_attribute is not None:
            self.changed_settings = json.loads(settings_attribute.value)

        tab_models = inputs.addTabCommandInput('tab_models', 'Models', '')
        tab_settings = inputs.addTabCommandInput('tab_settings', 'Settings', '')
        tab_setting_vis = inputs.addTabCommandInput('tab_settings_visibility', 'Visibility', '')

        tab_child = CommandInputs.cast(tab_models.children)
        selection_input = tab_child.addSelectionInput('selection', 'Body', 'Select the body to slice')
        selection_input.addSelectionFilter('Bodies')
        selection_input.setSelectionLimits(1, 0)
        # noinspection PyArgumentList
        for attr in AppObjects().design.findAttributes('FusedCura', 'selected_for_printing'):
            if attr.value == 'True':
                selection_input.addSelection(attr.parent)
        self.file_input = tab_child.addBoolValueInput('selectFile', 'gcode file', False, '', True)
        self.file_input.text = 'click'
        self.file_input.tooltip = 'Click to change file'
        self.info_box = tab_child.addTextBoxCommandInput('info_box', 'string', 'info', 1, True)
        self.info_box.isFullWidth = True
        self.layer_slider = tab_child.addIntegerSliderCommandInput('layer_slider', 'Layers', 0, 20, True)
        self.layer_slider.valueOne = 0
        self.layer_slider.valueTwo = 10
        table = TableCommandInput.cast(tab_child.addTableCommandInput('lt_table', 'table', 6, '1:7:1:7:1:7'))
        table.isFullWidth = True
        default_linetypes = {LineType.Inset0Type}
        self.layer_type_inputs = {
            t: tab_child.addBoolValueInput('lt_' + t.name, t.name, True, '', t in default_linetypes) for t in LineType
            if t is not LineType.NoneType}
        for k, v in self.layer_type_inputs.items():
            label = tab_child.addStringValueInput('label_' + k.name, 'lol', ' ' + k.name)
            label.isReadOnly = True
            table.addCommandInput(label, (k.value - 1) // 3, ((k.value - 1) % 3) * 2 + 1)
            table.addCommandInput(v, (k.value - 1) // 3, ((k.value - 1) % 3) * 2)

        tab_settings.isEnabled = False
        settings = get_config(fdmprinterfile, useless_settings)

        (self.global_settings_definitions, self.global_settings_defaults) = setting_tree_to_dict_and_default(settings)
        self.changed_machine_settings = read_machine_settings(self.global_settings_definitions,
                                                              self.global_settings_defaults)
        unknown_types = set()
        self.input_dict = dict()
        computed_properties = {k: v for k, v in self.global_settings_definitions.items() if 'value' in v}

        class CustomDict(dict):

            def __getitem__(_, k):
                return find_setting_in_stack(k, self.settings_stack)

        locals_vars = CustomDict()
        extra_functions = {
            'resolveOrValue': lambda x: locals_vars[x],
            # TODO: implement
            'extruderValue': lambda i, var: locals_vars[var],
            'extruderValues': lambda var: [locals_vars[var]],
            'defaultExtruderPosition': lambda: 0
        }

        class ComputedDict(Mapping):

            def __getitem__(_, k):
                node = computed_properties[k]
                code = node['compiled']
                import math
                return eval(code, {**globals(), **extra_functions, 'math': math}, locals_vars)

            def __iter__(self):
                return computed_properties.__iter__()

            def __len__(self):
                return len(computed_properties)

        self.computed_values = ComputedDict()
        self.settings_stack = [self.global_settings_defaults, self.computed_values, self.changed_machine_settings,
                               self.changed_settings]

        def type_creator(k, node, inputs):
            creator = setting_types.get(node['type'])
            if creator:
                value = find_setting_in_stack(k, self.settings_stack)
                new_input = creator.to_input(k, node, inputs, value)
                self.input_dict[k] = new_input
                new_input.isVisible = self.visibilities.get(k, False)
                return new_input
            else:
                unknown_types.add(node['type'])

        recursive_inputs(settings, tab_settings.children, type_creator)
        print('unknown config types:', unknown_types)
        create_visibility_checkboxes(self.visibilities, settings, tab_setting_vis.children, 0)

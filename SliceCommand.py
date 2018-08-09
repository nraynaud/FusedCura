import array
import itertools
import json
import shutil
import tempfile
import threading
import traceback
from collections import defaultdict
from copy import deepcopy
from string import Formatter
from time import time

from adsk.core import Command, Color, Vector3D, CommandInputs, DialogResults, CustomEventArgs, CustomEventHandler, \
    TableCommandInput, Line3D, Point3D
from adsk.fusion import BRepBody, CustomGraphicsCoordinates, CustomGraphicsSolidColorEffect, TemporaryBRepManager, Path
from .Fusion360Utilities.Fusion360CommandBase import Fusion360CommandBase
from .Fusion360Utilities.Fusion360Utilities import AppObjects
from .curaengine import run_engine, parse_segment, get_config
from .messages import Slice, dict_to_setting_list, ObjectList, Object, LineType
from .settings import setting_types, collect_changed_setting_if_different_from_parent, \
    setting_tree_to_dict_and_default, useless_settings, \
    find_setting_in_stack, save_visibility, read_visibility, read_machine_settings, read_configuration, fdmprinterfile
from .util import event, recursive_inputs

# https://gist.github.com/mRB0/740c25fdae3dc0b0ee7a

solid_red = CustomGraphicsSolidColorEffect.create(Color.create(255, 0, 0, 255))
solid_green = CustomGraphicsSolidColorEffect.create(Color.create(0, 255, 0, 255))
solid_blue = CustomGraphicsSolidColorEffect.create(Color.create(0, 0, 255, 255))
solid_yellow = CustomGraphicsSolidColorEffect.create(Color.create(255, 255, 0, 255))
solid_black = CustomGraphicsSolidColorEffect.create(Color.create(0, 0, 0, 255))
solid_aqua = CustomGraphicsSolidColorEffect.create(Color.create(0, 255, 255, 255))
solid_teal = CustomGraphicsSolidColorEffect.create(Color.create(0, 128, 128, 255))
solid_fuchsia = CustomGraphicsSolidColorEffect.create(Color.create(255, 0, 255, 255))
solid_olive = CustomGraphicsSolidColorEffect.create(Color.create(128, 128, 0, 255))
solid_maroon = CustomGraphicsSolidColorEffect.create(Color.create(128, 0, 0, 255))

color_list = [solid_red, solid_green, solid_blue, solid_yellow, solid_black, solid_aqua, solid_teal, solid_fuchsia,
              solid_olive, solid_olive]

ao = AppObjects()

engine_event_id = 'ENGINE_CUSTOM_EVENT'


def _create_visibility_checkboxes(defaut_visible_settings, node, inputs, depth):
    for (k, val) in node.items():
        visible = k in defaut_visible_settings
        id = k + '_vis'
        if val.get('children'):
            group_input = inputs.addGroupCommandInput(k + '_vis_group', (' ' * depth) + val['label'])
            ndepth = depth + 1
            if val['type'] != 'category':
                new_input = group_input.children.addBoolValueInput(id, ('-' * ndepth) + val['label'], True, '', visible)
                new_input.tooltipDescription = val['description']
                new_input.tooltip = k
            _create_visibility_checkboxes(defaut_visible_settings, val['children'], group_input.children, ndepth)
        else:
            new_input = inputs.addBoolValueInput(id, ('-' * depth) + val['label'], True, '', visible)
            new_input.tooltipDescription = val['description']
            new_input.tooltip = k


class CancelException(Exception):
    pass


def run_engine_in_other_thread(message, endpoint):
    def fire_if_not_canceled(info):
        handle_cancel()
        print('firing ', info)
        AppObjects().app.fireCustomEvent(engine_event_id, info)

    def handle_cancel():
        if endpoint.get('canceled'):
            raise CancelException

    previous_time = int(time() / 2)
    with tempfile.TemporaryFile() as gcode_collector:
        def on_message(raw_received, received_type):
            nonlocal previous_time
            new_time = int(time() / 5)
            if previous_time != new_time:
                fire_if_not_canceled(received_type.symbol)
                previous_time = new_time
            handle_cancel()

            if received_type.symbol == 'cura.proto.PrintTimeMaterialEstimates':
                endpoint['estimates'] = received_type.loads(raw_received)
            if received_type.symbol == 'cura.proto.GCodePrefix':
                complete_gcode = tempfile.NamedTemporaryFile()
                complete_gcode.write(received_type.loads(raw_received).data)
                gcode_collector.seek(0)
                shutil.copyfileobj(gcode_collector, complete_gcode)
                endpoint['gcode_file'] = complete_gcode
                complete_gcode.seek(0)
            if received_type.symbol == 'cura.proto.GCodeLayer':
                data = received_type.loads(raw_received).data
                gcode_collector.write(data)
            if received_type.symbol == 'cura.proto.SlicingFinished':
                endpoint['done'] = True
                fire_if_not_canceled('done')
            if received_type.symbol == 'cura.proto.LayerOptimized':
                line_strips_per_type = defaultdict(list)
                layer = received_type.loads(raw_received)
                points_per_type = defaultdict(set)
                for segment in layer.path_segment:
                    coord_iterator = iter(parse_segment(segment, layer.height))
                    current_list = []
                    current_type = None
                    for type, point_x in zip(segment.line_type, coord_iterator):
                        point = point_x / 10, next(coord_iterator) / 10, next(coord_iterator) / 10
                        points_per_type[type].add(point)
                        if len(current_list):
                            current_list.extend(point)
                        if type != current_type:
                            if len(current_list):
                                line_strips_per_type[current_type].append(current_list)
                            current_list = []
                            current_list.extend(point)
                            current_type = type
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


def get_message_and_mesh_for_engine(selected_bodies, settings, quality):
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


def compute_layer_preview(layer, layer_id, precomputed_layers):
    for type, data in layer['by_type'].items():
        if type not in precomputed_layers[layer_id]:
            index = 0
            lines = []
            for strip_len in data['strip_lengths']:
                current_poly = data['giant_strip'][index * 3:(index + strip_len) * 3]
                index += strip_len
                iterator = iter(current_poly)
                points = [(x, next(iterator), next(iterator)) for x in iterator]
                previous_point = None
                for point in points:
                    new_point = Point3D.create(*point)
                    if previous_point:
                        lines.append(Line3D.create(previous_point, new_point))
                    previous_point = new_point
            precomputed_layers[layer_id][type] = lines


def compute_layers_preview(engine_endpoint):
    layers = engine_endpoint['layers']
    precomputed_layers = engine_endpoint['precomputed_layers']
    for id, layer in layers.items():
        if id not in precomputed_layers:
            compute_layer_preview(layer, id, precomputed_layers)


class SliceCommand(Fusion360CommandBase):

    def cancel_engine(self):
        if self.engine_endpoint:
            self.engine_endpoint['canceled'] = True
            self.engine_event.remove(self.engine_endpoint['handler'])

    def on_preview(self, command: Command, inputs: CommandInputs, args, input_values):
        stacked_dict = {**self.global_settings_defaults, **self.changed_machine_settings, **self.changed_settings}
        interpolated_end_gcode = Formatter().vformat(stacked_dict['machine_end_gcode'], [], kwargs=stacked_dict)
        f = GCodeFormatter()
        interpolated_start_gcode = f.vformat(stacked_dict['machine_start_gcode'], [], kwargs=stacked_dict)
        last_minute_swaps = {'machine_start_gcode': interpolated_start_gcode,
                             'machine_end_gcode': interpolated_end_gcode, **f.prepend_dict}
        settings = deepcopy({**self.changed_machine_settings, **self.changed_settings, **last_minute_swaps})
        bodies = [BRepBody.cast(b) for b in input_values['selection']]
        slider = self.layer_slider
        if settings == self.running_settings and self.running_models == bodies:
            if self.engine_endpoint and self.engine_endpoint['done']:
                layer_keys = self.engine_endpoint['layers'].keys()
                slider.minimumValue = min(layer_keys)
                slider.maximumValue = max(layer_keys)
                slider.valueTwo = slider.maximumValue
                slider.isEnabled = True
                linework_group = self.graphics.addGroup()
                stack = [self.global_settings_defaults, self.changed_machine_settings, self.changed_settings]
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
                layers = self.engine_endpoint['precomputed_layers']
                layer_range = set(range(slider.valueOne, slider.valueTwo))
                line_types = {v.value for v in LineType if
                              v in self.layer_type_inputs and self.layer_type_inputs[v].value}
                compute_layers_preview(self.engine_endpoint)
                for id in layer_range.intersection(layers.keys()):
                    layer = layers[id]
                    for type in line_types.intersection(layer.keys()):
                        lines = layer[type]
                        if len(lines):
                            brepBody, edges = TemporaryBRepManager.get().createWireFromCurves(lines, True)
                            new_line = linework_group.addBRepBody(brepBody)
                            new_line.color = color_list[type % len(color_list)]
                            new_line.depthPriority = 2
                            new_line.weight = 2

                AppObjects().app.activeViewport.refresh()
                self.info_box.text = 'preview visible'
            return
        self.running_settings = settings
        self.running_models = bodies
        for body in bodies:
            body.isVisible = False
        (slice_msg, meshes) = get_message_and_mesh_for_engine(bodies, dict_to_setting_list(settings), 15)

        for mesh in meshes:
            self.graphics.addMesh(CustomGraphicsCoordinates.create(mesh.nodeCoordinatesAsDouble), mesh.nodeIndices, [],
                                  [])

        def on_engine(args: CustomEventArgs):
            layer_keys = self.engine_endpoint['layers'].keys()
            if len(layer_keys):
                slider.minimumValue = min(layer_keys)
                slider.maximumValue = max(layer_keys)
                slider.isEnabled = True
            else:
                slider.isEnabled = False
            if args.additionalInfo == 'done':
                self.cancel_engine()
                command.doExecutePreview()
            if args.additionalInfo == 'exception':
                AppObjects().ui.messageBox(repr(endpoint['exception']))
            if args.additionalInfo.startswith('layer|'):
                layer_id = int(args.additionalInfo[len('layer|'):])
                compute_layer_preview(self.engine_endpoint['layers'][layer_id], layer_id,
                                      self.engine_endpoint['precomputed_layers'])

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
            dialog.filter = 'GCode files (*.nc)'
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
            if setting_key.endswith('_vis'):
                vis_key = setting_key[:-len('_vis')]
                component = self.input_dict.get(vis_key)
                if component:
                    component.isVisible = changed_input.value
                    self.visibilities[vis_key] = changed_input.value

    def on_execute(self, command: Command, inputs: CommandInputs, args, input_values):
        attributes = AppObjects().app.activeDocument.attributes
        attributes.add('FusedCura', 'settings', json.dumps(self.changed_settings))
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
        for attr in AppObjects().design.findAttributes('FusedCura', 'selected_for_printing'):
            if attr.value == 'True':
                selection_input.addSelection(attr.parent)
        self.file_input = tab_child.addBoolValueInput('selectFile', 'gcode file', False, '', True)
        self.file_input.text = 'click'
        self.file_input.tooltip = 'Click to change file'
        self.info_box = tab_child.addTextBoxCommandInput('info_box', 'string', 'info', 1, True)
        self.info_box.isFullWidth = True
        self.layer_slider = tab_child.addIntegerSliderCommandInput('layer_slider', 'Layers', 0, 2, True)
        self.layer_slider.isEnabled = False
        self.layer_slider.valueOne = 0
        self.layer_slider.valueTwo = 1
        table = TableCommandInput.cast(tab_child.addTableCommandInput('lt_table', 'table', 6, '1:7:1:7:1:7'))
        table.isFullWidth = True
        default_linetypes = {LineType.SkirtType, LineType.Inset0Type}
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

        def type_creator(k, node, inputs):
            creator = setting_types.get(node['type'])
            if creator:
                value = find_setting_in_stack(k, [self.global_settings_defaults, self.changed_settings])
                new_input = creator.to_input(k, node, inputs, value)
                self.input_dict[k] = new_input
                new_input.isVisible = self.visibilities.get(k, False)
                return new_input
            else:
                unknown_types.add(node['type'])

        recursive_inputs(settings, tab_settings.children, type_creator)
        print('unknown config types:', unknown_types)
        _create_visibility_checkboxes(self.visibilities, settings, tab_setting_vis.children, 0)

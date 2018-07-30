from enum import Enum

from .lib.protobuf import *


class LineType(Enum):
    NoneType = 0
    Inset0Type = 1
    InsetXType = 2
    SkinType = 3
    SupportType = 4
    SkirtType = 5
    InfillType = 6
    SupportInfillType = 7
    MoveCombingType = 8
    MoveRetractionType = 9
    SupportInterfaceType = 10


Setting = MessageType()
Setting.add_field(1, 'name', Unicode)
Setting.add_field(2, 'value', Bytes)
Object = MessageType()
Object.add_field(1, 'id', Varint)
Object.add_field(2, 'vertices', Bytes)
Object.add_field(3, 'normals', Bytes)
Object.add_field(4, 'indices', Bytes)
Object.add_field(5, 'settings', EmbeddedMessage(Setting), flags=Flags.REPEATED)
ObjectList = MessageType()
ObjectList.add_field(1, 'objects', EmbeddedMessage(Object), flags=Flags.REPEATED)
ObjectList.add_field(2, 'settings', EmbeddedMessage(Setting), flags=Flags.REPEATED)
SettingList = MessageType()
SettingList.add_field(1, 'settings', EmbeddedMessage(Setting), flags=Flags.REPEATED)
Extruder = MessageType()
Extruder.add_field(1, 'id', UVarint)
Extruder.add_field(2, 'settings', EmbeddedMessage(SettingList))

SettingExtruder = MessageType()
SettingExtruder.add_field(1, 'name', Unicode)
SettingExtruder.add_field(2, 'extruder', Varint)
Slice = MessageType()
Slice.add_field(1, 'object_lists', EmbeddedMessage(ObjectList), flags=Flags.REPEATED)
Slice.add_field(2, 'global_settings', EmbeddedMessage(SettingList))
Slice.add_field(3, 'extruders', EmbeddedMessage(Extruder), flags=Flags.REPEATED)
Slice.add_field(4, 'limit_to_extruder', EmbeddedMessage(SettingExtruder), flags=Flags.REPEATED)
Progress = MessageType()
Progress.add_field(1, 'amount', Float32)

PathSegment = MessageType()
PathSegment.add_field(1, 'extruder', Int32)
PathSegment.add_field(2, 'point_type', UVarint)
PathSegment.add_field(3, 'points', Bytes)
PathSegment.add_field(4, 'line_type', Bytes)
PathSegment.add_field(5, 'line_width', Bytes)
PathSegment.add_field(6, 'line_thickness', Bytes)
PathSegment.add_field(7, 'line_feedrate', Bytes)
LayerOptimized = MessageType()
LayerOptimized.add_field(1, 'id', UVarint)
LayerOptimized.add_field(2, 'height', Float32)
LayerOptimized.add_field(3, 'thickness', Float32)
LayerOptimized.add_field(4, 'path_segment', EmbeddedMessage(PathSegment), flags=Flags.REPEATED)

GCodeLayer = MessageType()
GCodeLayer.add_field(2, 'data', Bytes)
Layer = MessageType()
GCodePrefix = MessageType()
GCodePrefix.add_field(2, 'data', Bytes)
MaterialEstimates = MessageType()
MaterialEstimates.add_field(1, 'id', Int64)
MaterialEstimates.add_field(2, 'material_amount', Float32)

PrintTimeMaterialEstimates = MessageType()
PrintTimeMaterialEstimates.add_field(1, 'time_none', Float32)
PrintTimeMaterialEstimates.add_field(2, 'time_inset_0', Float32)
PrintTimeMaterialEstimates.add_field(3, 'time_inset_x', Float32)
PrintTimeMaterialEstimates.add_field(4, 'time_skin', Float32)
PrintTimeMaterialEstimates.add_field(5, 'time_support', Float32)
PrintTimeMaterialEstimates.add_field(6, 'time_skirt', Float32)
PrintTimeMaterialEstimates.add_field(7, 'time_infill', Float32)
PrintTimeMaterialEstimates.add_field(8, 'time_support_infill', Float32)
PrintTimeMaterialEstimates.add_field(9, 'time_travel', Float32)
PrintTimeMaterialEstimates.add_field(10, 'time_retract', Float32)
PrintTimeMaterialEstimates.add_field(11, 'time_support_interface', Float32)
PrintTimeMaterialEstimates.add_field(12, 'materialEstimates', EmbeddedMessage(MaterialEstimates), flags=Flags.REPEATED)
SlicingFinished = MessageType()


def _fnv32a(value):
    hval = 2166136261
    fnv_32_prime = 16777619
    uint32_max = 2 ** 32
    for s in value:
        hval = hval ^ ord(s)
        hval = (hval * fnv_32_prime) % uint32_max
    return hval


symbol_message_dict = {'cura.proto.' + k: v for (k, v) in {
    'Slice': Slice, 'Layer': Layer, 'LayerOptimized': LayerOptimized,
    'Progress': Progress, 'GCodeLayer': GCodeLayer, 'GCodePrefix': GCodePrefix,
    'PrintTimeMaterialEstimates': PrintTimeMaterialEstimates, 'SlicingFinished': SlicingFinished
}.items()}
for (k, v) in symbol_message_dict.items():
    v.symbol = k
    v.hash = _fnv32a(k)

hash_message_dict = {v.hash: v for (k, v) in symbol_message_dict.items()}


def settings_to_dict(setting_list_message):
    return {s.name: s.value for s in setting_list_message.settings}


def dict_to_setting_list(dictionary):
    def create_setting(k, v):
        s = Setting()
        s.name = k
        s.value = str(v).encode('utf-8')
        return s

    sl = SettingList()
    sl.settings = [create_setting(k, v) for (k, v) in dictionary.items()]
    return sl

import array
import json
import os
import socket
import struct
from collections import OrderedDict
from contextlib import closing
from datetime import datetime
from os.path import dirname
from pathlib import Path
from subprocess import Popen, PIPE

from .lib.appdirs import user_log_dir
from .messages import hash_message_dict, symbol_message_dict, Slice
from .settings import read_configuration

# _exec_file = '/Applications/Ultimaker Cura.app/Contents/MacOS/CuraEngine'
# _settings_file = '/Applications/Ultimaker Cura.app/Contents/MacOS/resources/definitions/fdmprinter.def.json'

engine_log_file = os.path.join(user_log_dir('FusedCura', 'nraynaud'), 'engine.log')
os.makedirs(dirname(engine_log_file), exist_ok=True)
print(engine_log_file)

_SIGNATURE = 0x2BAD << 16 | 1 << 8
_CLOSE_SOCKET = 0xf0f0f0f0


def run_engine(slice_message: Slice, event_handler, keep_alive_handler=None):
    with open(engine_log_file, 'a+') as log_file:
        print(datetime.now(), file=log_file, flush=True)
        encoded_message = Slice.dumps(slice_message)
        config = read_configuration()
        print(dict(config), file=log_file, flush=True)
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as server_socket:
            server_socket.bind(('127.0.0.1', 0))
            server_socket.listen(5)
            name = server_socket.getsockname()
            child_process = Popen(
                [config['curaengine'], 'connect', "%s:%s" % name, '-j', config['fdmprinterfile']],
                stdout=log_file, stderr=log_file)
            try:
                print(child_process, file=log_file, flush=True)
                print(child_process.poll(), file=log_file, flush=True)
                (client_socket, address) = server_socket.accept()
                client_socket.send(struct.pack("I", socket.htonl(_SIGNATURE)))
                client_socket.send(struct.pack("!I", len(encoded_message)))
                client_socket.send(struct.pack("!I", symbol_message_dict['cura.proto.Slice'].hash))
                client_socket.send(encoded_message)
                while 1:
                    process = client_socket.recv(4, socket.MSG_WAITALL)
                    if len(process) == 4:
                        unpacked = struct.unpack('>I', process)[0]
                        if unpacked == 0:
                            if keep_alive_handler:
                                keep_alive_handler()
                            continue
                        if unpacked == _CLOSE_SOCKET:
                            print('_CLOSE_SOCKET')
                            return
                        if unpacked == _SIGNATURE:
                            size = struct.unpack('>I', client_socket.recv(4, socket.MSG_WAITALL))[0]
                            type_id = struct.unpack('>I', client_socket.recv(4, socket.MSG_WAITALL))[0]
                            type_def = hash_message_dict[type_id]
                            res3 = client_socket.recv(size, socket.MSG_WAITALL) if size else b''
                            event_handler(res3, type_def)
                            continue
                        break
                    else:
                        break
            finally:
                print(child_process.communicate(), file=log_file, flush=True)


def _2_to_3(point2d_array, height):
    for i in range(len(point2d_array) // 2 * 3):
        remainder = i % 3
        if remainder == 2:
            yield (height)
        else:
            yield (point2d_array[i // 3 * 2 + remainder])


def parse_segment(segment, height):
    floats = array.array('f', segment.points)
    if segment.point_type == 0:
        return _2_to_3(floats, height / 1000)
    else:
        return floats


def get_config(fusedcura_config, useless_set=set()):
    preferred_order = ['resolution', 'shell', 'infill', 'material', 'speed', 'cooling', 'support', 'travel',
                       'machine_settings', 'experimental', 'platform_adhesion']
    file_content = Path(fusedcura_config.get('fdmprinterfile')).read_text()
    loaded = json.JSONDecoder(object_pairs_hook=OrderedDict).decode(file_content)['settings']
    other_keys = [k for k in loaded.keys() if k not in set(preferred_order)]
    re_ordered_dict = OrderedDict([(k, loaded[k]) for k in preferred_order + other_keys])

    def filter_useless(node):
        if node.get('children'):
            filtered_children = OrderedDict(
                [(k, filter_useless(v)) for k, v in node['children'].items() if k not in useless_set])
            return {**{k: v for k, v in node.items() if k != 'children'}, 'children': filtered_children}
        return node

    return OrderedDict([(k, filter_useless(v)) for (k, v) in re_ordered_dict.items()])

import sys
import traceback

from adsk.core import MessageBoxIconTypes, MessageBoxButtonTypes
from .Fusion360Utilities.Fusion360Utilities import AppObjects

handlers = []


def report_exc(fun):
    def wrap(*args, **kwargs):
        try:
            return fun(*args, **kwargs)
        except:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            message = 'Error:\n{}\n--\n{}'.format(
                ''.join(traceback.format_exception_only(exc_type, exc_value)),
                '\n'.join(traceback.format_tb(exc_traceback)))
            print(message)
            print(message, file=sys.stderr)
            AppObjects().ui.messageBox(message, 'An error occured', MessageBoxButtonTypes.OKButtonType,
                                       MessageBoxIconTypes.CriticalIconType)

    return wrap


def event(clazz, handler):
    class Handler(clazz):
        @report_exc
        def notify(self, args):
            handler(args)

    handler_instance = Handler()
    handlers.append(handler_instance)
    return handler_instance


def register_on(clazz, obj):
    def wrapper(func):
        handler = event(clazz, func)
        obj.add(handler)

    return wrapper


def recursive_inputs(node, inputs, type_creator):
    for (k, val) in node.items():
        if val['type'] == 'category':
            new_input = inputs.addGroupCommandInput(k, val['label'])
            local_inputs = new_input.children
        else:
            new_input = type_creator(k, val, inputs)
            if not new_input:
                continue
            local_inputs = inputs
        new_input.tooltipDescription = val['description']
        new_input.tooltip = k
        if val.get('children'):
            recursive_inputs(val.get('children'), local_inputs, type_creator)

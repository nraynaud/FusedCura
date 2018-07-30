from .ConfigureFusedCuraCommand import ConfigureFusedCuraCommand
from .ConfigureMachineCommand import ConfigureMachineCommand
from .Fusion360Utilities.Fusion360Utilities import AppObjects
from .InfoCommand import InfoCommand
from .SliceCommand import SliceCommand

commands = []

command_definitions = [
    {
        'cmd_name': 'Slice',
        'cmd_description': 'Cura Engine Slicer',
        'cmd_id': 'FusedCuraCmd',
        'cmd_resources': './resources',
        'workspace': 'FusionSolidEnvironment',
        'toolbar_panel_id': 'Slice',
        'command_promoted': True,
        'class': SliceCommand
    },
    {
        'cmd_name': 'Machine Configuration',
        'cmd_description': 'Machine Configuration',
        'cmd_id': 'ConfigureMachineCmd',
        'cmd_resources': '',
        'workspace': 'FusionSolidEnvironment',
        'toolbar_panel_id': 'Slice',
        'command_promoted': False,
        'class': ConfigureMachineCommand
    },
    {
        'cmd_name': 'FusedCura Configuration',
        'cmd_description': 'General Configuration',
        'cmd_id': 'ConfigureFusedCuraCmd',
        'cmd_resources': '',
        'workspace': 'FusionSolidEnvironment',
        'toolbar_panel_id': 'Slice',
        'command_promoted': False,
        'class': ConfigureFusedCuraCommand
    },
    {
        'cmd_name': 'About',
        'cmd_description': 'About FusedCura',
        'cmd_id': 'InfoCmd',
        'cmd_resources': '',
        'workspace': 'FusionSolidEnvironment',
        'toolbar_panel_id': 'Slice',
        'command_promoted': False,
        'class': InfoCommand
    }
]

debug = False

# allows reloading during development
if AppObjects().ui.activeCommand in {definition['cmd_id'] for definition in command_definitions}:
    AppObjects().ui.terminateActiveCommand()

# Don't change anything below here:
for cmd_def in command_definitions:
    command = cmd_def['class'](cmd_def, debug)
    commands.append(command)


def run(context):
    for run_command in commands:
        run_command.on_run()


def stop(context):
    for stop_command in commands:
        stop_command.on_stop()

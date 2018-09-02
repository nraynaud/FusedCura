from .ConfigureFusedCuraCommand import ConfigureFusedCuraCommand
from .ConfigureMachineCommand import ConfigureMachineCommand
from .Fusion360Utilities.Fusion360Utilities import AppObjects
from .InfoCommand import InfoCommand
from .ShowLogsCommand import ShowLogsCommand
from .SliceCommand import SliceCommand
from .ThreeDView import DemoPaletteShowCommand

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
    },
    {
        'cmd_name': 'Logs',
        'cmd_description': 'Engine Logs',
        'cmd_id': 'LogCmd',
        'cmd_resources': '',
        'workspace': 'FusionSolidEnvironment',
        'toolbar_panel_id': 'Slice',
        'command_promoted': False,
        'class': ShowLogsCommand
    },
    {
        'cmd_name': 'Fusion Palette Demo Command',
        'cmd_description': 'Fusion Demo Palette Description',
        'cmd_id': 'cmdID_palette_demo',
        'workspace': 'FusionSolidEnvironment',
        'toolbar_panel_id': 'Slice',
        'command_visible': True,
        'command_promoted': False,
        'palette_id': 'demo_palette_id',
        'palette_name': 'Demo Palette Name',
        'palette_html_file_url': 'http://madebyevan.com/webgl-water/',
        'palette_is_visible': True,
        'palette_show_close_button': True,
        'palette_is_resizable': True,
        'palette_width': 500,
        'palette_height': 600,
        'class': DemoPaletteShowCommand
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

from adsk.core import Command, CommandInputs
from .Fusion360Utilities.Fusion360CommandBase import Fusion360CommandBase
from .Fusion360Utilities.Fusion360Utilities import AppObjects


class InfoCommand(Fusion360CommandBase):
    def on_create(self, command: Command, inputs: CommandInputs):
        AppObjects().ui.commandDefinitions.itemById('ConfigureFusedCuraCmd').execute()

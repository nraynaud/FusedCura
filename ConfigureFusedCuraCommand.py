from adsk.core import Command, CommandInputs, DialogResults
from .Fusion360Utilities.Fusion360CommandBase import Fusion360CommandBase
from .Fusion360Utilities.Fusion360Utilities import AppObjects
from .settings import read_configuration, save_configuration


class ConfigureFusedCuraCommand(Fusion360CommandBase):

    def on_input_changed(self, command: Command, inputs: CommandInputs, changed_input, input_values):
        dialog = AppObjects().ui.createFileDialog()
        if self.curaengine_input.id == changed_input.id:
            dialog.title = 'Select CuraEngine Executable'
            dialog.filename = self.configuration.get('curaengine', 'CuraEngine')
            dialog.initialDirectory = '/Applications/Ultimaker Cura.app/Contents/MacOS'
            accessible = dialog.showOpen()
            if accessible == DialogResults.DialogOK:
                self.curaengine_input.text = dialog.filename
                self.configuration['curaengine'] = dialog.filename
                self.curaengine_input.tooltipDescription = dialog.filename
        if self.fdmprinter_input.id == changed_input.id:
            dialog.title = 'Select fdmprinter.def.json file'
            dialog.filename = self.configuration.get('fdmprinterfile', 'fdmprinter.def.json')
            dialog.initialDirectory = '/Applications/Ultimaker Cura.app/Contents/MacOS/resources/definitions/'
            accessible = dialog.showOpen()
            if accessible == DialogResults.DialogOK:
                self.fdmprinter_input.text = dialog.filename
                self.configuration['fdmprinterfile'] = dialog.filename
                self.fdmprinter_input.tooltipDescription = dialog.filename

    def on_execute(self, command: Command, inputs: CommandInputs, args, input_values):
        save_configuration(self.configuration)

    def on_create(self, command: Command, inputs: CommandInputs):
        txt = '<b>Fused Cura</b><br>A Connection between Fusion 360 and Cura Engine by Nicolas Raynaud<br>'
        txt += '<p>You will need to configure the path to your curaengine executable and your fdmprinter.def.json file before using.</p>'
        text_box = inputs.addTextBoxCommandInput('text_box', 'Info', txt, 10, True)
        text_box.isFullWidth = True
        self.configuration = read_configuration()
        if not self.configuration:
            self.configuration = {}
        self.curaengine_input = inputs.addBoolValueInput('curaengine_file', 'CuraEngine executable', False, '', True)
        self.curaengine_input.text = self.configuration.get('curaengine', 'click to set')
        self.curaengine_input.tooltip = 'Click to select the CuraEngine executable file'
        self.curaengine_input.tooltipDescription = self.curaengine_input.text
        self.fdmprinter_input = inputs.addBoolValueInput('fdmprinter_file', 'fdmprinter.def.json file', False, '', True)
        self.fdmprinter_input.text = self.configuration.get('fdmprinterfile', 'click to set')
        self.fdmprinter_input.tooltip = 'Click to select the fdmprinter.def.json file'
        self.fdmprinter_input.tooltipDescription = self.fdmprinter_input.text

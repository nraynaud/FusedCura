from adsk.core import Command, CommandInputs
from .Fusion360Utilities.Fusion360CommandBase import Fusion360CommandBase
from .curaengine import engine_log_file


class ShowLogsCommand(Fusion360CommandBase):

    def on_input_changed(self, command: Command, inputs: CommandInputs, changed_input, input_values):
        if changed_input == self.delete_button:
            self.text_box.text = ''
            open(engine_log_file, 'w').close()

    def on_create(self, command: Command, inputs: CommandInputs):
        content = ''
        try:
            with open(engine_log_file) as f:
                content = f.read()
        except OSError:
            pass
        self.delete_button = inputs.addBoolValueInput('delete_button', 'Clear', False)
        self.delete_button.text = 'Clear Logs'
        self.delete_button.isFullWidth = True
        self.file_box = inputs.addTextBoxCommandInput('file_box', 'Log file', engine_log_file, 2, False)
        self.text_box = inputs.addTextBoxCommandInput('text_box', 'Logs', content, 15, False)
        self.text_box.isFullWidth = True

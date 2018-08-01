from adsk.core import Command, CommandInputs
from .Fusion360Utilities.Fusion360CommandBase import Fusion360CommandBase
from .curaengine import engine_log_file


class ShowLogsCommand(Fusion360CommandBase):

    def on_create(self, command: Command, inputs: CommandInputs):
        content = ''
        try:
            with open(engine_log_file) as f:
                content = f.read()
                print(content)
        except OSError:
            pass
        text_box = inputs.addTextBoxCommandInput('text_box', 'Logs', content, 15, False)
        text_box.isFullWidth = True

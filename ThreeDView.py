import json

from adsk.core import Palette, HTMLEventArgs, CameraEventHandler, CameraEventArgs, PaletteDockingStates
from .Fusion360Utilities.Fusion360CommandBase import Fusion360PaletteCommandBase
from .Fusion360Utilities.Fusion360Utilities import AppObjects
from .util import event

handlers = []


class DemoPaletteShowCommand(Fusion360PaletteCommandBase):

    def on_palette_execute(self, palette: Palette):
        if palette.dockingState == PaletteDockingStates.PaletteDockStateFloating:
            palette.dockingState = PaletteDockingStates.PaletteDockStateRight

        def on_camera(args: CameraEventArgs):
            camera = args.viewport.camera

        # palette.sendInfoToHTML('camera',
        #                         json.dumps({'eye': camera.eye.asArray(), 'target': camera.target.asArray(),
        #                                    'fov': camera.perspectiveAngle, 'up': camera.upVector.asArray()}))

        self.camera_handler = event(CameraEventHandler, on_camera)
        handlers.append(self.camera_handler)
        AppObjects().app.cameraChanged.add(self.camera_handler)

    def on_html_event(self, html_args: HTMLEventArgs):
        # reverse action is  palette.sendInfoToHTML('send', message)
        data = json.loads(html_args.data)
        pass

    def on_palette_close(self):
        AppObjects().app.cameraChanged.remove(self.camera_handler)
        pass

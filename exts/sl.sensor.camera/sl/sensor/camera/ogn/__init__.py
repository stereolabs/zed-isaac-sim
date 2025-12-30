import omni.ext
from isaacsim.core.utils.stage import get_current_stage
from pxr import Sdf
import carb


# Any class derived from `omni.ext.IExt` in a top level module (defined in `python.modules` of `extension.toml`) will be
# instantiated when the extension is enabled and `on_startup(ext_id)` will be called. Later when extension gets disabled
# on_shutdown() will be called.
class SlSensorCameraExtension(omni.ext.IExt):
    # ext_id is the current extension id. It can be used with the extension manager to query additional information,
    # such as where this extension is located in the filesystem.
    def on_startup(self, ext_id):
        print("[sl.sensor.camera] SlSensorCameraExtension startup", flush=True)
        self._startup_event_sub = (
            omni.usd.get_context()
            .get_stage_event_stream()
            .create_subscription_to_pop_by_type(int(omni.usd.StageEventType.OPENED), self._on_stage_open_event)
        )

    def on_shutdown(self):
        print("[sl.sensor.camera] SlSensorCameraExtension shutdown", flush=True)
        self._startup_event_sub = None
        self.timeline_play_sub = None

    def _on_stage_open_event(self, event):
        # Workaround for issue where an opened stage can contain a dirty /Render path
        stage = get_current_stage()
        path = "/Render"
        try:
            # delete any deltas on the root layer
            from omni.kit.usd.layers import RemovePrimSpecCommand
            RemovePrimSpecCommand(layer_identifier=stage.GetRootLayer().realPath, prim_spec_path=[Sdf.Path(path)]).do()
        except:
            pass

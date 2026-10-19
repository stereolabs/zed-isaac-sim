"""Experimental, diagnostic surface illuminance probe. It does not change any camera setting.

The dedicated render product uses PathTracing independently of other products.
Native renderer capture supplies a frame with its render metadata, also when the
timeline is paused. The RGBA-to-lux convention is qualified for Kit 110.1.2 and
the default linear Rec.709 rendering space, not arbitrary colour configurations.
"""
import asyncio
import ctypes
import time
import uuid
from dataclasses import dataclass

import numpy as np


def decode_illuminance(rgba):
    """Empirically qualified native PtIlluminance conversion; missing != zero."""
    values = np.asarray(rgba)
    if values.ndim != 3 or values.shape[2] != 4 or not np.isfinite(values).all():
        raise ValueError("Illuminance buffer is unavailable or invalid")
    return np.maximum(0., values[..., :3] @ np.array([.2126, .7152, .0722]) - 1.)


def pixel_region(center, radius, width, height):
    x, y = center
    if not all(np.isfinite([x, y, radius])) or not (0 <= x <= 1 and 0 <= y <= 1 and 0 < radius <= .15):
        raise ValueError("Select a valid region inside the probe image")
    half = max(2, round(radius * min(width, height)))
    cx, cy = min(width-1, round(x*width)), min(height-1, round(y*height))
    return max(0,cx-half), max(0,cy-half), min(width,cx+half), min(height,cy+half)


@dataclass
class LightingMeasurement:
    lux: float
    camera_path: str
    surface_path: str
    center: tuple
    region: tuple
    captured_at: float
    elapsed_ms: float
    frame_number: int
    samples: int
    revision: int
    camera_signature: tuple
    global_renderer: str
    probe_renderer: str


class LightingProbe:
    """One reusable probe; idle products are disabled and close releases resources."""
    _aov_users = 0
    _aov_initial = None

    def __init__(self, width=480, height=300, samples=64, bounces=4, keep_resident=False):
        import carb
        import omni.usd
        from pxr import Tf, Usd
        self.width, self.height = width, height
        self.samples, self.bounces = samples, bounces
        # Experimental periodic mode: avoid destroying/recreating a Hydra view
        # between reads. The AOV lease is still released after each acquisition.
        # A resident view may render after scene changes; it is not zero GPU work.
        self.keep_resident = keep_resident
        self.context = omni.usd.get_context()
        self.settings = carb.settings.get_settings()
        self.state, self.message = 'idle', 'Select a camera and measure a surface.'
        self.result = None
        self.preview = None
        self.field = None
        self.revision = 0
        self._stage = self.context.get_stage()
        self._product = None
        self._camera = None
        self._camera_path = ''
        self._configured_signature = None
        self._last_frame = -1
        self._root = '/Render/ZedLightingMeter_' + uuid.uuid4().hex[:10]
        self._task = None
        self._closed = False
        self._previous_aov = None
        self._aov_acquired = False
        self._notice = Tf.Notice.Register(Usd.Notice.ObjectsChanged, self._changed, self._stage) if self._stage else None
        self._stage_sub = self.context.get_stage_event_stream().create_subscription_to_pop(self._stage_event)

    @property
    def busy(self):
        return self._task is not None and not self._task.done()

    @property
    def product_path(self):
        return self._product.path if self._product else None

    def _stage_event(self, event):
        import omni.usd
        if event.type in (int(omni.usd.StageEventType.CLOSING), int(omni.usd.StageEventType.OPENED)):
            self.invalidate('Scene changed. Select a camera in the current stage.')
            self._release_product()
            if self._notice:
                self._notice.Revoke()
                self._notice = None
            self._stage = self.context.get_stage()
            if self._stage:
                from pxr import Tf, Usd
                self._notice = Tf.Notice.Register(Usd.Notice.ObjectsChanged, self._changed, self._stage)

    def _changed(self, notice, stage):
        paths = list(notice.GetResyncedPaths()) + list(notice.GetChangedInfoOnlyPaths())
        # Render products and our private camera are implementation details;
        # world geometry, lighting, materials and the source camera invalidate.
        if any(not str(p).startswith('/Render') for p in paths):
            self.invalidate('Scene changed; measure again.')

    def invalidate(self, message='Measurement region changed; measure again.'):
        self.revision += 1
        # USD notices cover camera fields beyond the inexpensive pose signature.
        # Re-copy the full camera after any invalidation, including region edits.
        self._configured_signature = None
        self.state = 'stale' if self.result else 'idle'
        self.message = message
        if self.busy:
            self._task.cancel()

    def camera_signature(self, path):
        from pxr import UsdGeom, Usd
        import omni.timeline
        stage = self.context.get_stage()
        if not stage: raise ValueError('No scene is open')
        camera = UsdGeom.Camera(stage.GetPrimAtPath(path))
        if not camera: raise ValueError('Select a USD camera')
        tc = Usd.TimeCode(omni.timeline.get_timeline_interface().get_current_time()*stage.GetTimeCodesPerSecond())
        c = camera.GetCamera(tc)
        return tuple(float(v) for row in c.transform for v in row) + (
            float(c.focalLength),float(c.horizontalAperture),float(c.verticalAperture),
            float(c.horizontalApertureOffset),float(c.verticalApertureOffset),
            float(c.clippingRange.min),float(c.clippingRange.max),float(c.fStop),float(c.focusDistance))

    def check_freshness(self):
        if self.result and self.state == 'valid':
            try:
                self._check_environment()
                if self.camera_signature(self.result.camera_path) != self.result.camera_signature:
                    self.invalidate('Camera moved; measure again.')
            except ValueError as exc:
                self.invalidate(str(exc))
                self.state = 'unavailable'

    def _check_environment(self):
        import omni.kit.app
        build = omni.kit.app.get_app().get_build_version()
        if build.split('+', 1)[0] != '110.1.2':
            raise ValueError('Lux conversion is only qualified for Kit 110.1.2')
        if self.settings.get('/rtx/renderingColorSpace') != 'lin_rec709_scene':
            raise ValueError('Lux conversion requires the qualified linear Rec.709 rendering space')
        if self.settings.get('/rtx/pathtracing/spectral/enabled'):
            raise ValueError('Spectral rendering has not been qualified for this lighting meter')

    def start(self, camera_path, center=(.5,.5), radius=.03):
        if self._closed: raise RuntimeError('Lighting meter is closed')
        if self.busy: return self._task
        pixel_region(center, radius, self.width, self.height)
        self._task = asyncio.ensure_future(self._measure(camera_path, center, radius))
        return self._task

    async def _tick(self, count=1):
        import omni.kit.app
        for _ in range(count):
            await omni.kit.app.get_app().next_update_async()

    def _acquire_aov(self):
        if self._aov_acquired:
            return
        cls = type(self)
        if cls._aov_users == 0:
            cls._aov_initial = self.settings.get('/rtx/pathtracing/illuminanceAOV')
            self.settings.set('/rtx/pathtracing/illuminanceAOV', True)
        self._previous_aov = cls._aov_initial
        cls._aov_users += 1
        self._aov_acquired = True

    def _release_aov(self):
        if not self._aov_acquired:
            return
        cls = type(self)
        cls._aov_users -= 1
        self._aov_acquired = False
        if cls._aov_users == 0:
            if self.settings.get('/rtx/pathtracing/illuminanceAOV') is True:
                if cls._aov_initial is None:
                    self.settings.destroy_item('/rtx/pathtracing/illuminanceAOV')
                else:
                    self.settings.set('/rtx/pathtracing/illuminanceAOV', cls._aov_initial)
            cls._aov_initial = None

    def _configure(self, path):
        import omni.replicator.core as rep
        import omni.timeline
        from pxr import Usd, UsdGeom, Sdf
        stage = self.context.get_stage()
        if not stage: raise ValueError('No scene is open')
        source = UsdGeom.Camera(stage.GetPrimAtPath(path))
        if not source: raise ValueError('Select a USD camera')
        if source.GetProjectionAttr().Get() != 'perspective':
            raise ValueError('This prototype supports perspective cameras')
        new = not self._product or path != self._camera_path or stage != self._stage
        if new:
            self._release_product()
            self._stage = stage
        self._acquire_aov()
        signature = self.camera_signature(path)
        if not new and signature == self._configured_signature:
            # Reusing an unchanged camera must not author scene edits. Even edits
            # to a private camera can disturb other products' temporal history.
            self._product.hydra_texture.set_updates_enabled(True)
            return False
        tc = Usd.TimeCode(omni.timeline.get_timeline_interface().get_current_time()*stage.GetTimeCodesPerSecond())
        with Usd.EditContext(stage, stage.GetSessionLayer()):
            if new:
                self._camera = UsdGeom.Camera.Define(stage, self._root+'/Camera')
            self._camera.SetFromCamera(source.GetCamera(tc))
            if new:
                self._product = rep.create.render_product(str(self._camera.GetPath()),(self.width,self.height),
                    name=self._root.rsplit('/',1)[-1])
            prim = stage.GetPrimAtPath(self._product.path)
            targets=[]
            for name in ('LdrColor','PtIlluminance'):
                var=stage.DefinePrim(self._root+'/Vars/'+name,'RenderVar')
                var.CreateAttribute('sourceName',Sdf.ValueTypeNames.String).Set(name)
                targets.append(var.GetPath())
            prim.GetRelationship('orderedVars').SetTargets(targets)
            for name,value,kind in [
                ('omni:rtx:rendermode','PathTracing',Sdf.ValueTypeNames.Token),
                ('omni:rtx:pt:samplesPerPixel',self.samples,Sdf.ValueTypeNames.UInt),
                ('omni:rtx:pt:samplesPerIteration',4,Sdf.ValueTypeNames.Int),
                ('omni:rtx:pt:limits:maxBounces',self.bounces,Sdf.ValueTypeNames.UInt),
                ('omni:rtx:pt:denoising:enabled',False,Sdf.ValueTypeNames.Bool),
                ('omni:rtx:pt:fireflyFilter:enabled',False,Sdf.ValueTypeNames.Bool),
            ]:
                prim.CreateAttribute(name,kind).Set(value)
        self._camera_path = path
        self._configured_signature = signature
        self._product.hydra_texture.set_updates_enabled(True)
        return new

    @staticmethod
    def _copy_capture(capsule, size, width, height, fmt):
        formats={'TextureFormat.RGBA32_SFLOAT':np.float32,'TextureFormat.RGBA8_UNORM':np.uint8,'TextureFormat.RGBA8_SRGB':np.uint8}
        if str(fmt) not in formats: raise ValueError('Unsupported capture format: '+str(fmt))
        dtype=formats[str(fmt)]
        if size != width*height*4*np.dtype(dtype).itemsize:
            raise ValueError('Unexpected capture dimensions or row stride')
        get_pointer=ctypes.pythonapi.PyCapsule_GetPointer
        get_pointer.restype=ctypes.c_void_p
        get_pointer.argtypes=[ctypes.py_object,ctypes.c_char_p]
        pointer=get_pointer(capsule,None)
        return np.frombuffer(ctypes.string_at(pointer,size),dtype=dtype).reshape(height,width,4).copy()

    async def _capture(self, after_frame=-1):
        import omni.kit.hydra_texture
        import omni.kit.renderer.capture
        from carb.eventdispatcher import get_eventdispatcher
        loop=asyncio.get_running_loop()
        future=loop.create_future()
        texture=self._product.hydra_texture
        capture=omni.kit.renderer.capture.acquire_renderer_capture_interface()
        requested=False
        outputs={}
        diagnostics={'events':0}
        def done(name, metadata, capsule, size, width, height, fmt):
            if future.done(): return
            try:
                outputs[name]=self._copy_capture(capsule,size,width,height,fmt)
                if len(outputs)==2:
                    self._last_frame=int(metadata.get('frame_number',-1))
                    future.set_result((outputs,metadata))
            except Exception as exc: future.set_exception(exc)
        def frame(event):
            nonlocal requested
            if requested or future.done(): return
            handle=event['result_handle']
            info=texture.get_frame_info(handle)
            diagnostics.update(events=diagnostics['events']+1,progression=info.get('progression'),frame=info.get('frame_number'))
            if info.get('frame_number',-1) <= after_frame or info.get('progression',0) < self.samples: return
            resources={r['name']:r.get('texture',{}) for r in texture.get_aov_info(handle,include_texture=True)}
            diagnostics['resources']={n:(str(r.get('format')),bool(r.get('rp_resource'))) for n,r in resources.items()}
            diagnostics['aov_enabled']=self.settings.get('/rtx/pathtracing/illuminanceAOV')
            if not all(resources.get(n,{}).get('rp_resource') for n in ('LdrColor','PtIlluminance')): return
            requested=True
            diagnostics['requested']=True
            for name in ('LdrColor','PtIlluminance'):
                capture.capture_next_frame_rp_resource_callback(
                    lambda *args,n=name,m=info: done(n,m,*args),resources[name]['rp_resource'])
        subscription=get_eventdispatcher().observe_event(observer_name='ZED lighting capture '+self._root,
            event_name=omni.kit.hydra_texture.GLOBAL_EVENT_DRAWABLE_CHANGED,
            filter=texture.get_event_key(),on_event=frame)
        try:
            return await asyncio.wait_for(future,timeout=15.)
        except asyncio.TimeoutError:
            diagnostics['received']=list(outputs)
            diagnostics['enabled']=texture.get_updates_enabled()
            diagnostics['mode']=self._stage.GetPrimAtPath(self._product.path).GetAttribute('omni:rtx:rendermode').Get()
            raise RuntimeError('Capture timeout: '+str(diagnostics)) from None
        finally:
            subscription=None

    async def _surface(self, center):
        import carb
        future=asyncio.get_running_loop().create_future()
        def found(path, position, pixel):
            if not future.done(): future.set_result(str(path))
        accepted=self._product.hydra_texture.request_query(
            carb.Uint2(min(self.width-1,int(center[0]*self.width)),min(self.height-1,int(center[1]*self.height))),
            callback=found,add_outline=False,query_name='ZedLightingSurface')
        if not accepted: raise ValueError('Surface query is unavailable')
        path=await asyncio.wait_for(future,timeout=5.)
        if not path: raise ValueError('The selected region points at the background; select a surface')
        return path

    async def _measure(self, path, center, radius):
        from pxr import Usd
        self.state,self.message='measuring','Preparing the lighting probe...'
        start=time.monotonic()
        try:
            self._check_environment()
            signature=self.camera_signature(path)
            # Native frame info is only safe inside the drawable callback.
            previous_frame=self._last_frame
            new=self._configure(path)
            revision=self.revision
            # Initial material/light setup can contaminate the first accumulation.
            # Recreated views need the retained warm-up/reset sequence. Only a
            # resident view can safely omit subsequent artificial focal resets.
            if new or not self.keep_resident:
                await self._tick(35 if new else 2)
                focal=self._camera.GetFocalLengthAttr().Get()
                with Usd.EditContext(self._stage,self._stage.GetSessionLayer()):
                    self._camera.GetFocalLengthAttr().Set(focal*1.0001)
                await self._tick(2)
                with Usd.EditContext(self._stage,self._stage.GetSessionLayer()):
                    self._camera.GetFocalLengthAttr().Set(focal)
            # Scene edits invalidate accumulation on a resident view. Wait for
            # USD updates, then require a newly delivered completed frame.
            await self._tick(3)
            self.message='Measuring incident light on the selected surface...'
            outputs,metadata=await self._capture(-1 if new else previous_frame)
            self.preview=outputs['LdrColor']
            surface=await self._surface(center)
            self._check_environment()
            if revision != self.revision or signature != self.camera_signature(path):
                raise ValueError('Scene or camera changed during measurement; measure again')
            rgba=outputs['PtIlluminance']
            if rgba.shape != (self.height,self.width,4): raise ValueError('Illuminance buffer resolution is invalid')
            mode=self._stage.GetPrimAtPath(self._product.path).GetAttribute('omni:rtx:rendermode').Get()
            if mode != 'PathTracing': raise ValueError('Probe is not using Path Tracing')
            region=pixel_region(center,radius,self.width,self.height)
            x0,y0,x1,y1=region
            field=decode_illuminance(rgba)
            self.result=LightingMeasurement(float(np.mean(field[y0:y1,x0:x1])),path,surface,tuple(center),region,
                time.time(),(time.monotonic()-start)*1000,int(metadata.get('frame_number',-1)),
                int(metadata.get('progression',0)),revision,signature,str(self.settings.get('/rtx/rendermode')),mode)
            self.field=field
            self.state,self.message='valid','Measured. Camera settings are unchanged.'
            return self.result
        except asyncio.CancelledError:
            self.state='stale' if self.result else 'idle'
            return None
        except Exception as exc:
            self.state,self.message='unavailable',str(exc) or type(exc).__name__
            return None
        finally:
            if self._product and not self.keep_resident: self._product.hydra_texture.set_updates_enabled(False)
            self._release_aov()

    def _release_product(self):
        if self._product:
            self._product.hydra_texture.set_updates_enabled(False)
            self._product.destroy()
            self._product=None
        if self._camera and self._stage:
            from pxr import Usd
            with Usd.EditContext(self._stage,self._stage.GetSessionLayer()): self._stage.RemovePrim(self._root)
        self._camera=None
        self._configured_signature=None
        self._last_frame=-1
        self._release_aov()

    def close(self):
        self._closed=True
        if self.busy: self._task.cancel()
        if self._notice: self._notice.Revoke(); self._notice=None
        self._stage_sub=None
        self._release_product()

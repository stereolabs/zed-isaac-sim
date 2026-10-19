# Changelog

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.1.1]
### Fixed
- **Virtual stereo calibrations of rigs that are not perfectly parallel were wrong.** The relative rotation was exported inverted, so the ZED SDK doubled a toe-in or tilt instead of correcting it; the depth offset (TZ) had the wrong sign; the vertical and depth offsets (TY, TZ) were written in meters where the SDK reads millimeters; and selecting the `Camera` prims instead of the ZED X One assets swapped the vertical and depth axes. A side-by-side, parallel pair was unaffected. Re-export the calibration of any other rig.
- The baseline no longer scales with an asset's scale, and follows the stage's units instead of assuming meters.
- **The exported camera model was sometimes the previous one.** Switching between two models that offer the same lens (for example ZED X One UHD to GS, both Wide) kept the first model in the file, so the ZED SDK used that camera's defaults.
- **The rotation between the two cameras is now also exported for 4K.** A ZED X One UHD pair streamed at HD4K was read with no rotation at all.
- **Only serial numbers from 110000001 to 119999999 are accepted.** Other values could replace the calibration file of a real ZED in the same folder; they are now refused with an error. A file that cannot be written is reported too.
- Disabling and re-enabling the exporter no longer leaves a second entry in the **Stereolabs** menu.

### Changed
- The exporter reads its camera models from the **Stereolabs ZED Camera** extension (`sl.sensor.camera`). Enabling the exporter now also enables it.

## [1.1.0]
### Changed
- Split the camera selection into two dropdowns: **Camera model** (base model) and **Lens type**, with the lens list filtered to the lenses available for the selected model.

## [1.0.1] - 2025-10-23
### Changed
- Update extension description and add extension-specific test settings.

## [0.1.0] - 2025-09-11
### Added
- Initial version of the ZED virtual stereo camera calibration exporter extension.

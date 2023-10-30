# zed-isaac-sim
ISAAC Sim integration for ZED SDK.

All the ZED Isaac extensions are still under development. This repo will remain private until release versions are reached.

## Structure
The structure of this repository is created in such a way to allow easier integration with Isaac Sim and a better development experience.
The ZEDBot Playground will serve as an example of an extension when getting started with Extensions in Isaac.

The main branch will contain all the extensions that have reached an "internal release" version.

Sub branches will contain extensions that are being actively changed/developed.


## Creating an extension
Simply copy the sl.zedbot.playground extension and modify everything.

## Adding robots
Since Omniverse Nucleus is not stable, to add a new robot it is preferred for now to create a new extension just for this robot that has a single button that loads the robots and shows relevant info. That way, ROS can be easilly rigged and the resulting robot can then be copied into a specific workstation.

**N.B.** This also prepares ROS configuration using code.
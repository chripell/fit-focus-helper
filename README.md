**This is not an officially supported Google product**

# fit-image-helper

`fit-image-helper` is a set of tool for image processing. It is also a
quick fits image browser and supports streaming from ZWO ASI Cams and
controlling a Telescope via INDI.

## Focusing and Collimation

`fit-image-helper` can help to achieve better focus and collimation
while doing astronomical imaging. It can measure various parameters of
stars in the field (sharpness, roundness, half flux
radius). `fit-image-helper` doesn't acquire images, but waits for them
to appear in a directory (it periodically polls its contents, right
now it doesn't use smarter methods like inotify). The tool is
tested/used with the ASI1600MC and ASI178MM. 

## dependencies

You need to have the following Python libraries installed:

* `pip install numpy`, Numeric Python, for various image operations.

* `pip install opencv-python`, OpenCV, for debayering, color space
  conversion and scaling.

* `pip install astropy`, Astropy, for handling fits files and image
  processing.

* `pip install pycairo`, Cairo, for drawing annotations on images.

* `pip install PyGObject`, PyGObjects bindings for Gtk3, GLib and Gdk.

* `pip install photutils`, photutils, for the source detection
  routines.

* `pip install scipy`, SciPy, dependency for photutils.

* [PyIndi client](https://github.com/chripell/pyindi-client) with
  fixed support for INDI 1.9.x.

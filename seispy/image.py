# -*- coding: utf-8 -*-
"""
- image.py -

Module to handle WPP and SW4 images of Maps or Cross-Sections

By: Omri Volk & Shahar Shani-Kadmiel, June 2015, kadmiel@post.bgu.ac.il

"""
import glob
import os
import subprocess
import warnings
from StringIO import StringIO

import numpy as np
import matplotlib.pyplot as plt
from matplotlib import patheffects as path_effects
from mpl_toolkits.axes_grid1 import make_axes_locatable
from obspy.core.util import AttribDict
try:
    from obspy.imaging.cm import obspy_divergent as cmap_divergent
    from obspy.imaging.cm import obspy_divergent_r as cmap_divergent_r
    from obspy.imaging.cm import obspy_sequential as cmap_sequential
    from obspy.imaging.cm import obspy_sequential_r as cmap_sequential_r
except ImportError:
    cmap_divergent = None
    cmap_divergent_r = None
    cmap_sequential = None
    cmap_sequential_r = None

from seispy.config import read_input_file
from seispy.header import (
    SW4_IMAGE_HEADER_DTYPE, SW4_PATCH_HEADER_DTYPE, SW4_IMAGE_PLANE,
    SW4_IMAGE_MODE_DISPLACEMENT, SW4_IMAGE_MODE_VELOCITY, SW4_IMAGE_PRECISION,
    SW4_SOURCE_TIME_FUNCTION_TYPE)
from seispy.plotting import set_matplotlib_rc_params


set_matplotlib_rc_params()


class Image(object):
    """
    A class to hold WPP or SW4 image files
    """
    CMAP = {"divergent": cmap_divergent,
            "divergent_r": cmap_divergent_r,
            "sequential": cmap_sequential,
            "sequential_r": cmap_sequential_r}
    MPL_SCATTER_PROPERTIES = {
        "source": {"s": 200, "marker": "*", "edgecolors": "k",
                   "facecolors": "", "alpha": 1, "linewidths": 1.5},
        "rec": {"s": 200, "marker": "v", "edgecolors": "k",
                "facecolors": "", "alpha": 1, "linewidths": 1.5},
        }
    MPL_SCATTER_PATH_EFFECTS = [
        path_effects.Stroke(linewidth=1.5+0.7, foreground='w'),
        path_effects.Normal()]

    def __init__(self, config=None, source_time_function_type=None):
        self.patches = []
        if config is not None and not isinstance(config, AttribDict):
            config = read_input_file(config)
        self._config = config
        if config:
            source_time_function_type_ = self.source_time_function_type
            if source_time_function_type and source_time_function_type_ and \
                    source_time_function_type != source_time_function_type_:
                msg = ("Overriding user specified source time function "
                       "type ({}) with the one found in configuration file "
                       "({}).").format(source_time_function_type,
                                       source_time_function_type_)
                warnings.warn(msg)
            source_time_function_type = source_time_function_type_
        # set mode code mapping, depending on the type of source time function
        if source_time_function_type == "displacement":
            self._mode_dict = SW4_IMAGE_MODE_DISPLACEMENT
        elif source_time_function_type == "velocity":
            self._mode_dict = SW4_IMAGE_MODE_VELOCITY
        else:
            msg = ("Unrecognized 'source_time_function_type': '{}'")
            msg = msg.format(source_time_function_type)
            raise ValueError(msg)
        self.filename = None
        self._precision = None
        self._number_of_patches = None
        self.time = None
        self._plane = None
        self.coordinate = None
        self._mode = None
        self.gridinfo = None
        self.creation_time = None

    def _read_header(self, f):
        """
        Read SW4 header information and store it in an Image object
        """
        header = np.fromfile(f, SW4_IMAGE_HEADER_DTYPE, 1)[0]
        (self._precision,
         self._number_of_patches,
         self.time,
         self._plane,
         self.coordinate,
         self._mode,
         self.gridinfo,
         self.creation_time) = header

    def _read_patches(self, f):
        """
        Read SW4 patch data and store it in a list of Patch objects
        under Image.patches
        """
        patch_info = np.fromfile(f,SW4_PATCH_HEADER_DTYPE,self._number_of_patches)
        for i, header in enumerate(patch_info):
            patch = Patch(number=i, image=self)
            patch._set_header(header)
            data = np.fromfile(f, self.precision, patch.ni*patch.nj)
            data = data.reshape(patch.nj, patch.ni)
            patch._set_data(data)
            self.patches.append(patch)

    def plot(self, patches=None, *args, **kwargs):
        """
        Plot all (or specific) patches in Image.

        >>> my_image.plot()  # plots all patches
        >>> my_image.plot(patches=[0, 2])  # plots first and third patch
        """
        if patches is None:
            for patch in self.patches:
                patch.plot(*args, **kwargs)
        else:
            for i in patches:
                self.patches[i].plot(*args, **kwargs)

    def _get_plot_coordinates_from_config(self, key):
        """
        Gets coordinates for config keys that have x, y, z values (e.g.
        'source', 'rec') in plotting coordinates for use in :meth:`plot`.
        """
        if not self._config:
            return None
        items = self._config.get(key, [])
        if not items:
            return None
        x = []
        y = []
        for item in items:
            if self._plane == 0:
                x_ = item.y
                y_ = item.z
            elif self._plane == 1:
                x_ = item.x
                y_ = item.z
            elif self._plane == 2:
                x_ = item.y
                y_ = item.x
            x.append(x_)
            y.append(y_)
        if not x:
            return None
        return x, y

    def get_source_coordinates(self):
        return self._get_plot_coordinates_from_config("source")

    @property
    def is_cross_section(self):
        if self._plane in (0, 1):
            return True
        elif self._plane == 2:
            return False

    @property
    def is_divergent(self):
        if self._cmap_type in ("divergent", "divergent_r"):
            return True
        return False

    @property
    def source_time_function_type(self):
        if not self._config:
            return None
        stf_type = SW4_SOURCE_TIME_FUNCTION_TYPE[self._config.source[0].type]
        return {0: "displacement", 1: "velocity"}.get(stf_type, None)

    @property
    def _cmap_type(self):
        return self._mode_dict[self._mode]['cmap_type']

    @property
    def number_of_patches(self):
        return len(self.patches)

    @property
    def precision(self):
        return SW4_IMAGE_PRECISION[self._precision]

    @property
    def plane(self):
        return SW4_IMAGE_PLANE[self._plane]

    @property
    def type(self):
        if self.is_cross_section:
            return 'cross-section'
        else:
            return 'map'

    @property
    def quantity_name(self):
        return self._mode_dict[self._mode]['name']

    @property
    def quantity_symbol(self):
        return self._mode_dict[self._mode]['symbol']

    @property
    def quantity_unit(self):
        return self._mode_dict[self._mode]['unit']


class Patch(object):
    """
    A class to hold WPP or SW4 patch data
    """

    def __init__(self, number=None, image=None):
        self.number = number
        self._image = image  # link back to the image this patch belongs to
        self.h = None
        self.zmin = None
        self.ib = None
        self.ni = None
        self.jb = None
        self.nj = None
        self.data = None
        self.extent = None

    def _set_header(self, header):
        """
        Set SW4 patch header information
        """
        (self.h,
         self.zmin,
         self.ib,
         self.ni,
         self.jb,
         self.nj) = header

    def _set_data(self, data):
        self.data = data
        if self._image.is_cross_section:
            self.extent = (
                0 - (self.h / 2.0),
                (self.ni - 1) * self.h + (self.h / 2.0),
                self.zmin - (self.h / 2.0),
                self.zmin + (self.nj - 1) * self.h + (self.h / 2.0))
        else:
            self.data = self.data.T
            self.extent = (
                0 - (self.h / 2.0),
                (self.nj - 1) * self.h + (self.h / 2.0),
                0 - (self.h / 2.0),
                (self.ni - 1) * self.h + (self.h / 2.0))
        self.min = data.min()
        self.max = data.max()
        self.std = data.std()
        self.rms = np.sqrt(np.mean(data**2))

    def plot(self, ax=None, vmin=None, vmax=None, colorbar=True,
             colorbar_label=None, cmap=None, **kwargs):

        if ax is None:
            fig, ax = plt.subplots()

        if cmap is None:
            cmap = self._image.CMAP[self._image._cmap_type]

        ax.set_aspect(1)

        # center colormap around zero if image's data is divergent
        if self._image.is_divergent:
            if vmin is None and vmax is None:
                abs_max = max(abs(self.min), abs(self.max))
                vmax = abs_max
                vmin = -abs_max

        if (vmin is not None and self.min < vmin) and \
                (vmax is not None and self.max > vmax):
            extend = 'both'
        elif vmin is not None and self.min < vmin:
            extend = 'min'
        elif vmax is not None and self.max > vmax:
            extend = 'max'
        else:
            extend = 'neither'

        im = ax.imshow(self.data, extent=self.extent, vmin=vmin, vmax=vmax,
                       origin="lower", interpolation="nearest", cmap=cmap,
                       **kwargs)
        # plot receiver, source etc.
        if self._image._config:
            for key, kwargs in self._image.MPL_SCATTER_PROPERTIES.items():
                coordinates = \
                    self._image._get_plot_coordinates_from_config(key)
                if not coordinates:
                    continue
                x, y = coordinates
                collection = ax.scatter(
                    x, y, **kwargs)
                collection.set_path_effects(
                    self._image.MPL_SCATTER_PATH_EFFECTS)
            # reset axes limits to data, they sometimes get changed by the
            # scatter plot
            ax.set_xlim(*self.extent[:2])
            ax.set_ylim(*self.extent[2:])

        # invert Z axis if not a map view
        if self._image.is_cross_section:
            ax.invert_yaxis()
        if colorbar:
            divider = make_axes_locatable(ax)
            cax = divider.append_axes("right", size="3%", pad=0.1)
            if not colorbar_label:
                colorbar_label = "{name} [{unit}]".format(
                    name=self._image.quantity_name,
                    unit=self._image.quantity_unit)
            cb = plt.colorbar(im, cax=cax, extend=extend, label=colorbar_label)
            # invert Z axis for cross-section plots and certain quantities that
            # usually increase with depths
            if self._image.is_cross_section and \
                    self._image._mode in (4, 7, 8):
                cax.invert_yaxis()
        else:
            cb = None

        if self._image._plane == 0:
            xlabel = "Y"
            ylabel = "Z"
        elif self._image._plane == 1:
            xlabel = "X"
            ylabel = "Z"
        elif self._image._plane == 2:
            xlabel = "Y"
            ylabel = "X"
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)

        fig.suptitle("{}\n{}={}  t={:.2f} seconds".format(
            self._image.filename, self._image.plane, self._image.coordinate,
            self._image.time))

        try:
            return fig, ax, cb
        except NameError:
            return cb


def read_SW4_image(filename='random', config=None,
                   source_time_function_type="displacement", verbose=False):
    """
    Read image data, cross-section or map into a SeisPy Image object.

    Params:
    --------

    filename : if no filename is passed, by default, a random image is generated
        if filename is None, an empty Image object is returned.

    verbose : if True, print some information while reading the file.

    Returns:
    ---------

    an Image object with a list of Patch objects
    """
    image = Image(source_time_function_type=source_time_function_type,
                  config=config)
    image.filename = filename

    if filename is 'random':  # generate random data and populate the objects
        image = _create_random_SW4_image(
            source_time_function_type=source_time_function_type)
    elif filename is None:
        pass
    else:
        if not filename.endswith('.sw4img'):
            msg = ("Using 'read_SW4_image()' on file with uncommon file "
                   "extension: '{}'.").format(filename)
            warnings.warn(msg)
        with open(image.filename, 'rb') as f:
            image._read_header(f)
            image._read_patches(f)
    return image


def _create_random_SW4_image(source_time_function_type="displacement"):
    """
    """
    image = Image(source_time_function_type=source_time_function_type)
    image.filename = None
    image._number_of_patches = 1
    image._precision = 4
    image.cycle = 0
    image.time = 0
    image.min = 0
    image.max = 0
    image.std = 0
    image.rms = 0
    image.patches = [_create_random_SW4_patch()]
    return image


def _create_random_SW4_patch():
    patch = Patch()
    patch.ni = 100
    patch.nj = 200
    patch.data = 2 * (np.random.rand(patch.ni, patch.nj) - 0.5)
    patch.number = 0
    patch.h = 100.0
    patch.zmin = 0
    patch.extent = (0, patch.nj * patch.h, patch.zmin + patch.ni * patch.h,
                    patch.zmin)
    patch.min = patch.data.min()
    patch.max = patch.data.max()
    patch.std = patch.data.std()
    patch.rms = np.sqrt(np.mean(patch.data**2))
    patch.ib = 1
    patch.jb = 1
    return patch


def image_files_to_movie(
        input_files, output_filename, config=None,
        source_time_function_type=None, patch_number=0, frames_per_second=5,
        overwrite=False, global_colorlimits=True, debug=False, **plot_kwargs):
    """
    Convert SW4 images to an mp4 movie using command line ffmpeg.

    :type input_files: str or list
    :param input_files: Wildcarded filename pattern or list of individual
        filenames.
    """
    if not output_filename.endswith(".mp4"):
        output_filename += ".mp4"
    if os.path.exists(output_filename):
        if overwrite:
            os.remove(output_filename)
    if os.path.exists(output_filename):
        msg = ("Output path '{}' exists.").format(output_filename)
        raise IOError(msg)

    if isinstance(input_files, str):
        files = sorted(glob.glob(input_files))
    else:
        files = input_files

    # parse all files to determine global value range extrema before doing
    # the plotting
    if global_colorlimits:
        global_min = np.inf
        global_max = -np.inf
        for file_ in files:
            image = read_SW4_image(
                file_, config=config,
                source_time_function_type=source_time_function_type)
            patch = image.patches[patch_number]
            global_min = min(global_min, patch.min)
            global_max = max(global_max, patch.max)
        if image.is_divergent:
            abs_max = max(abs(global_min), abs(global_max))
            plot_kwargs["vmin"] = -abs_max
            plot_kwargs["vmax"] = abs_max
        else:
            plot_kwargs["vmin"] = global_min
            plot_kwargs["vmax"] = global_max

    cmdstring = (
        'ffmpeg', '-r', '%d' % frames_per_second, '-f', 'image2pipe',
        '-vcodec', 'png', '-i', 'pipe:', '-vcodec', 'libx264', '-pass', '1',
        '-vb', '6M', '-pix_fmt', 'yuv420p', output_filename)

    string_io = StringIO()
    backend = plt.get_backend()
    try:
        plt.switch_backend('AGG')
        # plot all images and pipe the pngs to ffmpeg
        for file_ in files:
            image = read_SW4_image(
                file_, source_time_function_type=source_time_function_type,
                config=config)
            patch = image.patches[patch_number]
            fig, _, _ = patch.plot(**plot_kwargs)
            fig.savefig(string_io, format='png')
            plt.close(fig)
        string_io.seek(0)
        png_data = string_io.read()
        string_io.close()
        sub = subprocess.Popen(cmdstring, stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = sub.communicate(png_data)
        if debug:
            print("###### ffmpeg stdout")
            print(stdout)
            print("###### ffmpeg stderr")
            print(stderr)
        sub.wait()
    finally:
        plt.switch_backend(backend)

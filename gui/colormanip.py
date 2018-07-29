# This file is part of MyPaint.
# Copyright (C) 2018 by the Mypaint Development Team
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or


"""Modes for manipulating colors by dragging on the canvas"""


## Imports
from __future__ import print_function

import gui.mode
from gui.colorpicker import ColorPickPreviewOverlay

import math

from gettext import gettext as _


## Class defs

class ColorAdjustMode(gui.mode.OneshotDragMode):
    """Base class for on-canvas color adjustment modes -
    display centered color indicator overlay while adjusting the color
    """

    def __init__(self, ignore_modifiers=False, **kwds):
        super(ColorAdjustMode, self).__init__(**kwds)
        self._overlay = None
        self._started_from_key_press = ignore_modifiers
        self._start_drag_on_next_motion_event = False

    def enter(self, doc, **kwds):
        """Enters the mode, arranging for necessary grabs ASAP"""
        super(ColorAdjustMode, self).enter(doc, **kwds)

    def leave(self, **kwds):
        self._remove_overlay()
        super(ColorAdjustMode, self).leave(**kwds)

    def drag_update_cb(self, tdw, event, dx, dy):
        self._place_overlay(tdw, event.x, event.y)

    def _place_overlay(self, tdw, x, y):
        if self._overlay is None:
            cx, cy = tdw.get_center()
            # Consistency with color picker preview
            self._overlay = ColorPickPreviewOverlay(
                self.doc, tdw, cx, cy - ColorPickPreviewOverlay.PREVIEW_SIZE
            )

    def _remove_overlay(self):
        if self._overlay is None:
            return
        self._overlay.cleanup()
        self._overlay = None

    def get_options_widget(self):
        return None


class HueAdjustMode(ColorAdjustMode):
    """A mode for changing the hue directly by dragging"""

    ACTION_NAME = 'HueAdjustMode'

    pointer_behavior = gui.mode.Behavior.EDIT_OBJECTS
    supports_button_switching = True

    permitted_switch_actions = set(
        ['HueSatValAdjustMode'] + gui.mode.BUTTON_BINDING_ACTIONS
    )

    @classmethod
    def get_name(cls):
        return _(u"Drag-adjust hue")

    def get_usage(self):
        return _(u"Change the hue of the current color by dragging")

    @property
    def inactive_cursor(self):
        return None

    @property
    def active_cursor(self):
        return None

    def drag_update_cb(self, tdw, event, dx, dy):
        x, y = event.x, event.y
        cx, cy = tdw.get_center()
        x, y = x - cx, y - cy
        phi2 = math.atan2(y, x)
        x, y = x - dx, y - dy
        phi1 = math.atan2(y, x)
        ds = ((phi2 - phi1) / (2 * math.pi))
        self.doc.offset_brush_hue(ds)
        super(HueAdjustMode, self).drag_update_cb(tdw, event, dx, dy)


class HueSatValAdjustMode(ColorAdjustMode):
    """Mode for adjusting hue, saturation and value by
    clicking and dragging on canvas
    """

    ACTION_NAME = 'HueSatValAdjustMode'

    pointer_behavior = gui.mode.Behavior.EDIT_OBJECTS
    supports_button_switching = True

    permitted_switch_actions = set(
        ['HueAdjustMode'] + gui.mode.BUTTON_BINDING_ACTIONS
    )

    @classmethod
    def get_name(cls):
        return _(u"Drag-adjust color")

    def get_usage(self):
        return _(
            u"Adjust brightness, saturation and hue of current color by "
            "dragging vertically, horizontally and diagonally on the canvas"
        )

    @property
    def inactive_cursor(self):
        return None

    @property
    def active_cursor(self):
        return None

    def drag_update_cb(self, tdw, event, dx, dy):
        ratioLim = 1.8

        if dx == 0 or abs(dy / dx) > ratioLim:  # Up/Down - Brightness
            self.doc.offset_brush_brightness(dy/-500)
        elif dy == 0 or abs(dx / dy) > ratioLim:  # Right/Left - Saturation
            self.doc.offset_brush_saturation(dx/700)
        else:  # Diagonals - Hue
            d = math.copysign(math.sqrt(dx**2+dy**2), dy)
            self.doc.offset_brush_hue(-(d / 1000))
        super(HueSatValAdjustMode, self).drag_update_cb(tdw, event, dx, dy)

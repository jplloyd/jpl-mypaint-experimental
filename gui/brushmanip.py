# This file is part of MyPaint.
# Copyright (C) 2018 by the Mypaint Development Team
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or

"""Modes for manipulating brushes/colors"""

## Imports
from __future__ import print_function

import gui.mode
import gui.freehand
import math

from gi.repository import Gdk

from gettext import gettext as _

import gui.overlays


## Class defs

class BrushSizeOverlay(gui.overlays.Overlay):
    """Indicate the radius of the brush by a circular outline"""

    def __init__(self, doc, tdw, x, y, radius, handle_x, handle_y):
        super(BrushSizeOverlay, self).__init__()
        self._doc = doc
        self._tdw = tdw
        self._x = int(x)
        self._y = int(y)
        self._hx = handle_x
        self._hy = handle_y
        self._radius = radius
        self._oldradius = 0
        prefs = doc.app.preferences
        self.line_width_inner = float(
            prefs.get("cursor.freehand.inner_line_width", 1.25)
        )
        self.line_width_outer = float(
            prefs.get("cursor.freehand.outer_line_width", 1.25)
        )
        self.col_fg = tuple(
            prefs.get("cursor.freehand.outer_line_color", (0, 0, 0, 1))
        )
        self.col_bg = tuple(
            prefs.get("cursor.freehand.inner_line_color", (1, 1, 1, 0.75))
        )
        self.inset = int(prefs.get("cursor.freehand.inner_line_inset", 2))
        tdw.display_overlays.append(self)
        self._queue_tdw_redraw()

    def cleanup(self):
        self._tdw.display_overlays.remove(self)
        self._queue_tdw_redraw()

    def _queue_tdw_redraw(self):
        area = self._get_area()
        self._tdw.queue_draw_area(*area)

    def _get_area(self):
        r = math.exp(max(self._radius, self._oldradius)) * self._tdw.scale + 5
        linew = self.line_width_outer
        x = self._x - r - 2 * linew - 20
        y = self._y - r - 2 * linew - 20
        size = 2 * (r + 2 * linew + 20)
        return (x, y, size, size + 20)

    def update(self, radius, handle_x, handle_y):
        self._oldradius = self._radius
        self._radius = radius
        self._hx = handle_x
        self._hy = handle_y
        self._queue_tdw_redraw()

    def paint(self, cr):
        cx = self._x
        cy = self._y

        r0 = math.exp(self._radius) * self._tdw.scale
        r = r0 - self.line_width_outer / 2.0
        cr.set_source_rgba(*self.col_fg)
        cr.set_line_width(self.line_width_outer)
        cr.arc(cx, cy, r, 0, math.pi*2)
        cr.stroke()

        r = r0 - self.inset + self.line_width_inner / 2.0
        cr.set_source_rgba(*self.col_bg)
        cr.set_line_width(self.line_width_inner)
        cr.arc(cx, cy, r, 0, math.pi*2)
        cr.stroke()

        cr.set_source_rgba(*self.col_fg)
        cr.arc(self._hx, self._hy, 3, 0, 2 * math.pi)
        cr.fill()
        cr.set_source_rgba(*self.col_bg)
        cr.arc(self._hx, self._hy, 2, 0, 2 * math.pi)
        cr.fill()


class BrushResizeMode(gui.mode.OneshotDragMode):
    """A mode for changing the size of the active brush by dragging on the canvas
    """

    ACTION_NAME = 'BrushResizeMode'

    pointer_behavior = gui.mode.Behavior.EDIT_OBJECTS
    supports_button_switching = True

    permitted_switch_actions = set([] + gui.mode.BUTTON_BINDING_ACTIONS)

    @classmethod
    def get_name(cls):
        return _(u"Drag-resize brush")

    def get_usage(self):
        return _(u"Change brush size by dragging on the canvas")

    @property
    def inactive_cursor(self):
        return None

    @property
    def active_cursor(self):
        ctype = Gdk.CursorType.BLANK_CURSOR
        return Gdk.Cursor.new(ctype)

    def enter(self, doc, **kwds):
        super(BrushResizeMode, self).enter(doc, **kwds)
        tdw = doc.tdw
        x, y = self.current_position()
        cx, cy = tdw.get_center()
        radius = tdw.doc.brush.brushinfo.get_base_value('radius_logarithmic')
        radius_px = math.exp(radius) * tdw.scale
        self.x_orig = x
        self.y_orig = y
        self.x_offs = math.copysign(radius_px, cx - x)
        self.y_offs = 0
        self.handle_x = x + self.x_offs
        self.handle_y = y + self.y_offs
        self.overlay = BrushSizeOverlay(
            doc, doc.tdw, x, y, radius, self.handle_x, self.handle_y
        )

    def leave(self, **kwds):
        self.overlay.cleanup()
        self.overlay = None

    def drag_update_cb(self, tdw, event, dx, dy):
        adj = tdw.app.brush_adjustment['radius_logarithmic']

        self.handle_x += dx * 0.5
        self.handle_y += dy * 0.5

        dx = self.handle_x - self.x_orig
        dy = self.handle_y - self.y_orig

        dst = math.sqrt(dx**2 + dy**2) * (1 / tdw.scale)
        newradius = math.log(dst)
        adj.set_value(newradius)
        self.overlay.update(newradius, self.handle_x, self.handle_y)

        return super(BrushResizeMode, self).drag_update_cb(tdw, event, dx, dy)

    def get_options_widget(self):
        """Get the (class singleton) options widget"""
        cls = self.__class__
        if cls._OPTIONS_WIDGET is None:
            widget = gui.freehand.FreehandOptionsWidget()
            cls._OPTIONS_WIDGET = widget
        return cls._OPTIONS_WIDGET

# This file is part of MyPaint.
# Copyright (C) 2014 by Andrew Chadwick <a.t.chadwick@gmail.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or


"""Modes for quickly switching between brushes"""


## Imports
from __future__ import print_function

import gui.mode
import math

from gettext import gettext as _


##### Overlay imports

from gi.repository import Gdk
from gi.repository import GdkPixbuf
import cairo

import gui.overlays


## Class defs

class BrushSelectOverlay(gui.overlays.Overlay):
    """Selection overlay showing brush choices"""

    RADIUS_INNER = 50
    RADIUS_OUTER = 100
    OUTLINE_WIDTH_ACTIVE = 5
    OUTLINE_WIDTH_INACTIVE = 2
    RADIUS_FULL = RADIUS_INNER + RADIUS_OUTER + OUTLINE_WIDTH_ACTIVE

    def __init__(self, doc, tdw, x, y, selected, history):
        super(BrushSelectOverlay, self).__init__()
        self._tdw = tdw
        self._x = x
        self._y = y
        w = self.RADIUS_INNER * 2
        self._selBuffer = selected.copy().scale_simple(
            w, w, GdkPixbuf.InterpType.BILINEAR
        )
        self._historyBuffers = []
        self.numHist = len(history)
        for i in history:
            hw = self.RADIUS_OUTER
            self._historyBuffers.append(
                i.copy().scale_simple(hw, hw, GdkPixbuf.InterpType.BILINEAR)
            )
        tdw.display_overlays.append(self)
        self._active = None
        self._queue_tdw_redraw()

    def cleanup(self):
        self._tdw.display_overlays.remove(self)
        self._queue_tdw_redraw()

    def _get_area(self):
        r_full = self.RADIUS_FULL
        return (self._x - r_full, self._y - r_full, r_full * 2, r_full * 2)

    def _queue_tdw_redraw(self):
        area = self._get_area()
        self._tdw.queue_draw_area(*area)

    def set_active(self, active):
        self._active = active
        self._queue_tdw_redraw()

    def any_selected(self, x, y):
        dst = math.sqrt((x - self._x)**2 + (y - self._y)**2)
        return (dst > self.RADIUS_INNER and
                dst < self.RADIUS_INNER + self.RADIUS_OUTER)

    def paint(self, cr):
        angle = 2 * math.pi / self.numHist
        for i, hbuf in zip(range(0, self.numHist), self._historyBuffers):
            self.paint_slice(
                cr, i * angle, (i+1) * angle, hbuf, i == self._active
            )

        def_active = self._active is None

        radInner = self.RADIUS_INNER
        mask_grad = cairo.RadialGradient(
            self._x, self._y, radInner * 0.6,
            self._x, self._y, radInner * 0.9
        )
        mask_grad.add_color_stop_rgba(0, 1, 1, 1, 1)
        mask_grad.add_color_stop_rgba(1, 1, 1, 1, 0)

        cr.push_group()
        if def_active:
            cr.set_source_rgb(1, 1, 1)
        else:
            cr.set_source_rgb(0.9, 0.9, 0.9)
        cr.arc(self._x, self._y, self.RADIUS_INNER, 0, math.pi * 2)
        cr.fill()
        Gdk.cairo_set_source_pixbuf(
            cr, self._selBuffer,
            self._x - self.RADIUS_INNER,
            self._y - self.RADIUS_INNER
        )
        cr.mask(mask_grad)
        cr.pop_group_to_source()
        cr.paint_with_alpha(1 if def_active else 0.75)

    def paint_slice(self, cr, angle_s, angle_e, prevImg, active):
        x = self._x
        y = self._y
        mid_angle = angle_s + (angle_e - angle_s)/2
        cx = x + math.cos(mid_angle)*(self.RADIUS_INNER + self.RADIUS_OUTER/2)
        cy = y + math.sin(mid_angle)*(self.RADIUS_INNER + self.RADIUS_OUTER/2)
        outerhalf = self.RADIUS_OUTER / 2

        mask_grad = cairo.RadialGradient(
            cx, cy, outerhalf * 0.6, cx, cy, outerhalf * 0.9
        )
        mask_grad.add_color_stop_rgba(0, 1, 1, 1, 1)
        mask_grad.add_color_stop_rgba(1, 1, 1, 1, 0)

        cr.push_group()
        if active:
            cr.set_source_rgb(1, 1, 1)
        else:
            cr.set_source_rgb(0.9, 0.9, 0.9)
        cr.arc(x, y, self.RADIUS_INNER, angle_s, angle_e)
        cr.arc_negative(
            x, y, self.RADIUS_INNER + self.RADIUS_OUTER, angle_e, angle_s
        )
        cr.close_path()
        cr.fill_preserve()
        cr.clip()

        Gdk.cairo_set_source_pixbuf(
            cr, prevImg, cx - outerhalf, cy - outerhalf
        )
        cr.mask(mask_grad)
        cr.reset_clip()
        cr.pop_group_to_source()
        cr.paint_with_alpha(0.75 if not active else 1)


# Base classes up for debate here, I think ODM works fine.
class BrushSelectMode(gui.mode.OneshotDragMode):
    """A mode enabling quick switching between recent brushes"""

    ACTION_NAME = 'BrushSelectMode'

    pointer_behavior = gui.mode.Behavior.EDIT_OBJECTS
    scroll_behavior = gui.mode.Behavior.EDIT_OBJECTS
    supports_button_switching = False

    @classmethod
    def get_name(cls):
        return _(u"Choose Recent Brush")

    @property
    def inactive_cursor(self):
        return None

    @property
    def active_cursor(self):
        return None

    def get_options_widget(self):
        return None

    # Button release will exit mode even if mod key(s) still pressed
    def button_release_cb(self, tdw, event):
        modestack = self.app.doc.modes
        while self in modestack:
            modestack.pop()
        return super(BrushSelectMode, self).button_release_cb(tdw, event)

    def enter(self, doc, **kwds):
        super(BrushSelectMode, self).enter(doc, **kwds)
        self.app = app = doc.app
        self.bm = bm = app.brushmanager
        currentBrush = bm.selected_brush
        cBrushName = currentBrush.get_display_name()
        self.history = filter(
            lambda mb: mb.get_display_name() != cBrushName,
            bm.history
        )
        self.histLength = len(self.history)
        self.x, self.y = self.current_position()
        self.selected = None
        sel_prev = currentBrush.preview
        hist_prevs = list(map(lambda mb: mb.preview, self.history))
        self._overlay = BrushSelectOverlay(
            doc, doc.tdw, self.x, self.y, sel_prev, hist_prevs
        )

    def leave(self):
        self._overlay.cleanup()
        self._overlay = None
        if self.selected is not None:
            self.bm.select_brush(self.selected)

    def drag_update_cb(self, tdw, event, dx, dy):
        if (self._overlay.any_selected(event.x, event.y)):
            # Pointer is inside the outer overlay circle
            angle = math.atan2(event.y - self.y, event.x - self.x)
            slice_radians = (2 * math.pi) / self.histLength
            idx = (angle // slice_radians) % self.histLength
            selected = self.history[int(idx)]
            if self.selected != selected:
                self.selected = selected
                self._overlay.set_active(idx)
        elif self.selected is not None:
            # Only update when a new brush is selected
            self.selected = None
            self._overlay.set_active(None)
        return super(BrushSelectMode, self).drag_update_cb(tdw, event, dx, dy)

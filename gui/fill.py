# This file is part of MyPaint.
# Copyright (C) 2018 by the Mypaint Development Team
# Copyright (C) 2013 by Andrew Chadwick <a.t.chadwick@gmail.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.

"""Flood fill tool"""

## Imports
from __future__ import division, print_function

import weakref
from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import Pango
from gettext import gettext as _
from lib.gettext import C_

import gui.mode
import gui.cursor
import gui.blendmodehandler

import lib.floodfill
import lib.mypaintlib
import lib.layer


## Class defs

class FloodFillMode (gui.mode.ScrollableModeMixin,
                     gui.mode.SingleClickMode):
    """Mode for flood-filling with the current brush color"""

    ## Class constants

    ACTION_NAME = "FloodFillMode"
    GC_ACTION_NAME = "FloodFillGCMode"

    permitted_switch_actions = set([
        'RotateViewMode', 'ZoomViewMode', 'PanViewMode',
        'ColorPickMode', 'ShowPopupMenu',
        ])

    _BLEND_MODES = None
    _OPTIONS_WIDGET = None
    _CURSOR_FILL_NORMAL = gui.cursor.Name.CROSSHAIR_OPEN_PRECISE
    _CURSOR_FILL_ERASER = gui.cursor.Name.ERASER
    _CURSOR_FILL_ALPHA_LOCKED = gui.cursor.Name.ALPHA_LOCK
    _CURSOR_FILL_FORBIDDEN = gui.cursor.Name.ARROW_FORBIDDEN

    ## Instance vars (and defaults)

    pointer_behavior = gui.mode.Behavior.PAINT_NOBRUSH
    scroll_behavior = gui.mode.Behavior.CHANGE_VIEW

    _current_cursor = (False, _CURSOR_FILL_NORMAL)
    _tdws = None
    _fill_permitted = True
    _x = None
    _y = None

    @property
    def cursor(self):
        gc_on, name = self._current_cursor
        from gui.application import get_app
        app = get_app()
        action_name = self.GC_ACTION_NAME if gc_on else self.ACTION_NAME
        return app.cursors.get_action_cursor(action_name, name)

    def get_current_cursor(self):
        if self.bm.eraser_mode.active:
            return self._CURSOR_FILL_ERASER
        elif self.bm.lock_alpha_mode.active:
            return self._CURSOR_FILL_ALPHA_LOCKED
        else:
            return self._CURSOR_FILL_NORMAL

    ## Method defs

    def enter(self, doc, **kwds):
        super(FloodFillMode, self).enter(doc, **kwds)
        self._tdws = set([self.doc.tdw])
        self.app.blendmodemanager.register(self.bm)
        rootstack = self.doc.model.layer_stack
        rootstack.current_path_updated += self._update_ui
        rootstack.layer_properties_changed += self._update_ui
        self._update_ui()

    def leave(self, **kwds):
        self.app.blendmodemanager.deregister(self.bm)
        rootstack = self.doc.model.layer_stack
        rootstack.current_path_updated -= self._update_ui
        rootstack.layer_properties_changed -= self._update_ui
        return super(FloodFillMode, self).leave(**kwds)

    @classmethod
    def get_name(cls):
        return _(u'Flood Fill')

    def get_usage(self):
        return _(u"Fill areas with color")

    def __init__(self, ignore_modifiers=False, **kwds):
        super(FloodFillMode, self).__init__(**kwds)
        opts = self.get_options_widget()
        self._current_cursor = (opts.gap_closing, self._CURSOR_FILL_NORMAL)
        from gui.application import get_app
        self.app = get_app()
        self.bm = self.get_blend_modes()
        self.bm.mode_changed += self.update_blendmode
        self._prev_release = (0, None)

    def update_blendmode(self, bm, old, new):
        if(old is not new):
            self._update_ui()

    def clicked_cb(self, tdw, event):
        """Flood-fill with the current settings where clicked

        If the current layer is not fillable, a new layer will always be
        created for the fill.
        """
        if not self._fill_permitted:
            return
        try:
            self.EOTF = self.app.preferences['display.colorspace_EOTF']
        except: 
            self.EOTF = 2.2
        x, y = tdw.display_to_model(event.x, event.y)
        self._x = x
        self._y = y
        self._tdws.add(tdw)
        self._update_ui()
        color = self.doc.app.brush_color_manager.get_color()
        opts = self.get_options_widget()
        make_new_layer = opts.make_new_layer
        rootstack = tdw.doc.layer_stack
        if not rootstack.current.get_fillable():
            make_new_layer = True
        rgb = color.get_rgb()
        rgb = (rgb[0]**self.EOTF, rgb[1]**self.EOTF, rgb[2]**self.EOTF)
        tdw.doc.flood_fill(x, y, rgb,
                           tolerance=opts.tolerance,
                           offset=opts.offset, feather=opts.feather,
                           gap_closing_options=opts.gap_closing_options,
                           mode=self.bm.active_mode.mode_type,
                           sample_merged=opts.sample_merged,
                           src_path=opts.src_path,
                           make_new_layer=make_new_layer)
        opts.make_new_layer = False
        return False

    def key_press_cb(self, win, tdw, event):
        timeout = 500
        t = event.time
        (old_t, k) = self._prev_release
        if t - old_t < timeout and k == event.keyval:
            if k == Gdk.KEY_Shift_L:
                self.get_options_widget().flip_gap_closing()
            elif k == Gdk.KEY_Control_L:
                self.get_options_widget().flip_use_src_layer()
            self._update_ui()
            t -= 500
        self._prev_release = (t, event.keyval)

    def motion_notify_cb(self, tdw, event):
        """Track position, and update cursor"""
        x, y = tdw.display_to_model(event.x, event.y)
        self._x = x
        self._y = y
        self._tdws.add(tdw)
        self._update_ui()
        return super(FloodFillMode, self).motion_notify_cb(tdw, event)

    def _update_ui(self, *_ignored):
        """Updates the UI from the model"""
        x, y = self._x, self._y
        if None in (x, y):
            x, y = self.current_position()
        model = self.doc.model

        # Determine which layer will receive the fill based on the options
        opts = self.get_options_widget()
        target_layer = model.layer_stack.current
        if opts.make_new_layer:
            target_layer = None

        # Determine whether the target layer can be filled
        permitted = True
        if target_layer is not None:
            permitted = target_layer.visible and not target_layer.locked
        if permitted and model.frame_enabled:
            fx1, fy1, fw, fh = model.get_frame()
            fx2, fy2 = fx1+fw, fy1+fh
            permitted = x >= fx1 and y >= fy1 and x < fx2 and y < fy2
        self._fill_permitted = permitted

        # Update cursor of any TDWs we've crossed
        if self._fill_permitted:
            cursor = (opts.gap_closing, self.get_current_cursor())
        else:
            cursor = (opts.gap_closing, self._CURSOR_FILL_FORBIDDEN)

        if cursor != self._current_cursor:
            self._current_cursor = cursor
            for tdw in self._tdws:
                tdw.set_override_cursor(self.cursor)

    ## Fill blend modes
    def get_blend_modes(self):
        """Get the (class singleton) blend modes manager"""
        cls = self.__class__
        if cls._BLEND_MODES is None:
            bm = gui.blendmodehandler.BlendModes()
            bm.normal_mode.mode_type = lib.mypaintlib.CombineNormal
            bm.eraser_mode.mode_type = lib.mypaintlib.CombineDestinationOut
            bm.lock_alpha_mode.mode_type = lib.mypaintlib.CombineSourceAtop
            bm.colorize_mode.enabled = False
            cls._BLEND_MODES = bm
        return cls._BLEND_MODES

    ## Mode options

    def get_options_widget(self):
        """Get the (class singleton) options widget"""
        cls = self.__class__
        if cls._OPTIONS_WIDGET is None:
            widget = FloodFillOptionsWidget()
            cls._OPTIONS_WIDGET = widget
        return cls._OPTIONS_WIDGET


class FloodFillOptionsWidget (Gtk.Grid):
    """Configuration widget for the flood fill tool"""

    TOLERANCE_PREF = 'flood_fill.tolerance'
    SAMPLE_MERGED_PREF = 'flood_fill.sample_merged'
    OFFSET_PREF = 'flood_fill.offset'
    FEATHER_PREF = 'flood_fill.feather'

    # Gap closing related parameters
    GAP_CLOSING_PREF = 'flood_fill.gap_closing'
    GAP_SIZE_PREF = 'flood_fill.gap_size'
    RETRACT_SEEPS_PREF = 'flood_fill.retract_seeps'
    # "make new layer" is a temportary toggle, and is not saved to prefs

    DEFAULT_TOLERANCE = 0.05
    DEFAULT_SAMPLE_MERGED = False
    DEFAULT_MAKE_NEW_LAYER = False
    DEFAULT_OFFSET = 0
    DEFAULT_FEATHER = 0

    # Gap closing related defaults
    DEFAULT_GAP_CLOSING = False
    DEFAULT_GAP_SIZE = 5
    DEFAULT_RETRACT_SEEPS = True

    def __init__(self):
        Gtk.Grid.__init__(self)

        self.set_row_spacing(6)
        self.set_column_spacing(6)
        from gui.application import get_app
        self.app = get_app()
        prefs = self.app.preferences

        row = 0
        label = Gtk.Label()
        label.set_markup(_("Tolerance:"))
        label.set_tooltip_text(
            _("How much pixel colors are allowed to vary from the start\n"
              "before Flood Fill will refuse to fill them"))
        label.set_alignment(1.0, 0.5)
        label.set_hexpand(False)
        self.attach(label, 0, row, 1, 1)
        value = prefs.get(self.TOLERANCE_PREF, self.DEFAULT_TOLERANCE)
        value = float(value)
        adj = Gtk.Adjustment(value=value, lower=0.0, upper=1.0,
                             step_increment=0.05, page_increment=0.05,
                             page_size=0)
        adj.connect("value-changed", self._tolerance_changed_cb)
        self._tolerance_adj = adj
        scale = Gtk.Scale()
        scale.set_hexpand(True)
        scale.set_adjustment(adj)
        scale.set_draw_value(False)
        self.attach(scale, 1, row, 1, 1)

        row += 1
        label = Gtk.Label()
        label.set_markup(_("Source:"))
        label.set_tooltip_text(_("Which visible layers should be filled"))
        label.set_alignment(1.0, 0.5)
        label.set_hexpand(False)
        self.attach(label, 0, row, 1, 1)

        # Selection independent fill-basis

        root = self.app.doc.model.layer_stack
        src_list = FlatLayerList(root)
        self.src_list = src_list
        combo = Gtk.ComboBox.new_with_model(src_list)
        cell = Gtk.CellRendererText()
        cell.set_property("ellipsize", Pango.EllipsizeMode.END)
        combo.pack_start(cell, True)

        def layer_name_render(_, name_cell, model, it):
            """
            Display layer groups in italics and child layers
            indented with two spaces per level
            """
            name, path, layer = model[it][:3]
            if name is None:
                name = "Layer"
            if layer is None:
                name_cell.set_property(
                    "markup", "( <i>{text}</i> )".format(text=name)
                )
                return
            indented = "  " * (len(path) - 1) + name
            if isinstance(layer, lib.layer.LayerStack):
                name_cell.set_property(
                    "markup", "<i>{text}</i>".format(text=indented)
                )
            else:
                name_cell.set_property("text", indented)

        def sep_func(model, it):
            return model[it][0] is None

        combo.set_row_separator_func(sep_func)
        combo.set_cell_data_func(cell, layer_name_render)
        combo.set_tooltip_text(
            C_(
                "fill option (not saved): Specific fill source choice",
                "Select a specific layer you want the fill to be based on"
            )
        )
        combo.set_active(0)
        self._prev_src_layer = None
        root.layer_inserted += self._layer_inserted_cb
        self._combo_cb_id = combo.connect(
            "changed", self._src_combo_changed_cb
        )
        self._src_combo = combo
        self.attach(combo, 1, row, 2, 1)

        row += 1

        text = _("Sample Merged")
        checkbut = Gtk.CheckButton.new_with_label(text)
        checkbut.set_tooltip_text(
            _("When considering which area to fill, use a\n"
              "temporary merge of all the visible layers\n"
              "underneath the current layer"))
        self.attach(checkbut, 1, row, 1, 1)
        active = bool(prefs.get(self.SAMPLE_MERGED_PREF,
                                self.DEFAULT_SAMPLE_MERGED))
        checkbut.set_active(active)
        checkbut.connect("toggled", self._sample_merged_toggled_cb)
        self._sample_merged_toggle = checkbut
        self._src_combo.set_sensitive(not active)

        row += 1
        label = Gtk.Label()
        label.set_markup(_("Target:"))
        label.set_tooltip_text(_("Where the output should go"))
        label.set_alignment(1.0, 0.5)
        label.set_hexpand(False)
        self.attach(label, 0, row, 1, 1)

        text = _("New Layer (once)")
        checkbut = Gtk.CheckButton.new_with_label(text)
        checkbut.set_tooltip_text(
            _("Create a new layer with the results of the fill.\n"
              "This is turned off automatically after use."))
        self.attach(checkbut, 1, row, 1, 1)
        active = self.DEFAULT_MAKE_NEW_LAYER
        checkbut.set_active(active)
        self._make_new_layer_toggle = checkbut

        row += 1
        self.attach(Gtk.Separator(), 0, row, 2, 1)

        row += 1
        label = Gtk.Label()
        label.set_markup(C_(
            "fill options: offset (grow/shrink) label",
            u"Offset:"
        ))
        label.set_alignment(1.0, 0.5)
        label.set_hexpand(False)
        self.attach(label, 0, row, 1, 1)

        TILE_SIZE = lib.floodfill.TILE_SIZE
        value = prefs.get(self.OFFSET_PREF, self.DEFAULT_OFFSET)
        adj = Gtk.Adjustment(value=value,
                             lower=-TILE_SIZE, upper=TILE_SIZE,
                             step_increment=1, page_increment=4)
        adj.connect("value-changed", self._offset_changed_cb)
        self._offset_adj = adj
        spinbut = Gtk.SpinButton()
        spinbut.set_tooltip_text(C_(
            "fill options: offset (grow/shrink) description",
            u"The distance in pixels to grow or shrink the fill"
        ))
        spinbut.set_hexpand(True)
        spinbut.set_adjustment(adj)
        spinbut.set_numeric(True)
        self.attach(spinbut, 1, row, 1, 1)

        row += 1
        label = Gtk.Label()
        label.set_markup(C_(
            "fill options: feather (blur) label",
            u"Feather:"
        ))
        label.set_alignment(1.0, 0.5)
        label.set_hexpand(False)
        self.attach(label, 0, row, 1, 1)

        value = prefs.get(self.FEATHER_PREF, self.DEFAULT_FEATHER)
        adj = Gtk.Adjustment(value=value,
                             lower=0, upper=TILE_SIZE,
                             step_increment=1, page_increment=4)
        adj.connect("value-changed", self._feather_changed_cb)
        self._feather_adj = adj
        spinbut = Gtk.SpinButton()
        spinbut.set_tooltip_text(C_(
            "fill options: feather (blur) description",
            u"The amount of blur to apply to the fill"
        ))
        spinbut.set_hexpand(True)
        spinbut.set_adjustment(adj)
        spinbut.set_numeric(True)
        self.attach(spinbut, 1, row, 1, 1)

        row += 1
        self.attach(Gtk.Separator(), 0, row, 2, 1)

        row += 1
        gap_closing_params = Gtk.Grid()
        self._gap_closing_grid = gap_closing_params

        text = C_(
            "fill options: gap detection on/off label",
            u'Use gap detection'
        )
        checkbut = Gtk.CheckButton.new_with_label(text)
        checkbut.set_tooltip_text(C_(
            "fill options: gap closing on/off description",
            u"Try to detect gaps and not fill past them.\n"
            u"Note: This can be a lot slower than the regular fill, "
            u"only enable when you really need it."
        ))
        self._gap_closing_toggle = checkbut
        checkbut.connect("toggled", self._gap_closing_toggled_cb)
        active = prefs.get(self.GAP_CLOSING_PREF, self.DEFAULT_GAP_CLOSING)
        checkbut.set_active(active)
        gap_closing_params.set_sensitive(active)
        self.attach(checkbut, 0, row, 2, 1)

        row += 1
        self.attach(gap_closing_params, 0, row, 2, 1)

        gcp_row = 0
        label = Gtk.Label()
        label.set_markup(C_(
            "fill options: maximum size of gaps label",
            u"Max gap size:"
        ))
        label.set_alignment(1.0, 0.5)
        label.set_hexpand(False)
        gap_closing_params.attach(label, 0, gcp_row, 1, 1)

        value = prefs.get(self.GAP_SIZE_PREF, self.DEFAULT_GAP_SIZE)
        adj = Gtk.Adjustment(value=value,
                             lower=1, upper=int(TILE_SIZE/2),
                             step_increment=1, page_increment=4)
        adj.connect("value-changed", self._max_gap_size_changed_cb)
        self._max_gap_adj = adj
        spinbut = Gtk.SpinButton()
        spinbut.set_tooltip_text(C_(
            "fill options: max gap size description",
            u"The size of the largest gaps that can be detected"
        ))
        spinbut.set_hexpand(True)
        spinbut.set_adjustment(adj)
        spinbut.set_numeric(True)
        gap_closing_params.attach(spinbut, 1, gcp_row, 1, 1)

        gcp_row += 1
        text = C_(
            "fill options: on/off sub-option to gap closing fill; "
            "When enabled, the fill will stay outside of detected "
            "gaps, when disabled, they will seep into them",
            u"Prevent seeping"
        )
        checkbut = Gtk.CheckButton.new_with_label(text)
        active = prefs.get(self.RETRACT_SEEPS_PREF, self.DEFAULT_RETRACT_SEEPS)
        checkbut.set_active(active)
        checkbut.set_tooltip_text(C_(
            "gui/fill.py - description of (Retract seeps) option",
            u"Try to prevent the fill from seeping into the gaps"
        ))
        checkbut.connect("toggled", self._retract_seeps_toggled_cb)
        self._retract_seeps_toggle = checkbut
        gap_closing_params.attach(checkbut, 1, gcp_row, 1, 1)

        row += 1
        align = Gtk.Alignment.new(0.5, 1.0, 1.0, 0.0)
        align.set_vexpand(True)
        button = Gtk.Button(label=_("Reset"))
        button.connect("clicked", self._reset_clicked_cb)
        button.set_tooltip_text(_("Reset options to their defaults"))
        align.add(button)
        self.attach(align, 0, row, 2, 1)

    def flip_gap_closing(self):
        """Turn gap closing on or off depending on its current status"""
        self._gap_closing_toggle.set_active(not self.gap_closing)

    def flip_use_src_layer(self):
        """Flip between using the default src layer and previous choice"""
        prev = self._prev_src_layer
        if not (prev and prev() and prev().root):
            return
        index = self._layer_index(prev())
        combo = self._src_combo
        choice = 0 if combo.get_active() == index else index
        with combo.handler_block(self._combo_cb_id):
            combo.set_active(choice)

    def _layer_index(self, layer):
        """Linear fetch for layer index in src selection combobox
        Returns None if the layer is not contained in any row.
        """
        for i, entry in enumerate(self._src_combo.get_model()):
            if entry[2] is layer:
                return i

    @property
    def tolerance(self):
        return float(self._tolerance_adj.get_value())

    @property
    def make_new_layer(self):
        return bool(self._make_new_layer_toggle.get_active())

    @make_new_layer.setter
    def make_new_layer(self, value):
        self._make_new_layer_toggle.set_active(bool(value))

    @property
    def sample_merged(self):
        return bool(self._sample_merged_toggle.get_active())

    @property
    def src_path(self):
        row = self._src_combo.get_active_iter()
        if row is not None:
            return self._src_combo.get_model()[row][1]
        else:
            return None

    @property
    def offset(self):
        return int(self._offset_adj.get_value())

    @property
    def feather(self):
        return int(self._feather_adj.get_value())

    @property
    def gap_closing(self):
        return bool(self._gap_closing_toggle.get_active())

    @property
    def max_gap_size(self):
        return int(self._max_gap_adj.get_value())

    @property
    def retract_seeps(self):
        return bool(self._retract_seeps_toggle.get_active())

    @property
    def gap_closing_options(self):
        if self.gap_closing:
            return lib.floodfill.GapClosingOptions(
                self.max_gap_size, self.retract_seeps)
        else:
            return None

    def _tolerance_changed_cb(self, adj):
        self.app.preferences[self.TOLERANCE_PREF] = self.tolerance

    def _sample_merged_toggled_cb(self, checkbut):
        self._src_combo.set_sensitive(not self.sample_merged)
        self.app.preferences[self.SAMPLE_MERGED_PREF] = self.sample_merged

    def _offset_changed_cb(self, adj):
        self.app.preferences[self.OFFSET_PREF] = self.offset

    def _feather_changed_cb(self, adj):
        self.app.preferences[self.FEATHER_PREF] = self.feather

    def _gap_closing_toggled_cb(self, adj):
        self._gap_closing_grid.set_sensitive(self.gap_closing)
        self.app.preferences[self.GAP_CLOSING_PREF] = self.gap_closing

    def _max_gap_size_changed_cb(self, adj):
        self.app.preferences[self.GAP_SIZE_PREF] = self.max_gap_size

    def _retract_seeps_toggled_cb(self, adj):
        self.app.preferences[self.RETRACT_SEEPS_PREF] = self.retract_seeps

    def _layer_inserted_cb(self, root, path):
        """Check if the newly inserted layer was the last actively
        selected fill src layer, and reinstate the selection if so.
        """
        layer = root.deepget(path)
        if layer and self._prev_src_layer and self._prev_src_layer() is layer:
            # Restore previous layer selection
            combo = self._src_combo
            index = self._layer_index(layer)
            if index:
                with combo.handler_block(self._combo_cb_id):
                    combo.set_active(index)

    def _src_combo_changed_cb(self, combo):
        """Track the last selected choice of layer to maintain
        selection between layer moves that use intermediate
        layer deletion (as well undoing layer deletions)
        """
        row = combo.get_active_iter()
        if row is not None:
            layer = combo.get_model()[row][2]
            if layer is None:
                self._prev_src_layer = None
            else:
                self._prev_src_layer = weakref.ref(layer)
        else:
            # Option unset by layer deletion, set to default
            # without triggering callback again
            with combo.handler_block(self._combo_cb_id):
                combo.set_active(0)

    def _reset_clicked_cb(self, button):
        self._tolerance_adj.set_value(self.DEFAULT_TOLERANCE)
        self._make_new_layer_toggle.set_active(self.DEFAULT_MAKE_NEW_LAYER)
        self._src_combo.set_active(0)
        self._sample_merged_toggle.set_active(self.DEFAULT_SAMPLE_MERGED)
        self._offset_adj.set_value(self.DEFAULT_OFFSET)
        self._feather_adj.set_value(self.DEFAULT_FEATHER)
        # Gap closing params
        self._max_gap_adj.set_value(self.DEFAULT_GAP_SIZE)
        self._retract_seeps_toggle.set_active(self.DEFAULT_RETRACT_SEEPS)
        self._gap_closing_toggle.set_active(self.DEFAULT_GAP_CLOSING)


class FlatLayerList(Gtk.ListStore):
    """Stores a flattened copy of the layer tree"""

    def __init__(self, root_stack):
        super(FlatLayerList, self).__init__()

        root_stack.layer_properties_changed += self._layer_props_changed_cb
        root_stack.layer_inserted += self._layer_inserted_cb
        root_stack.layer_deleted += self._layer_deleted_cb

        self.root = root_stack
        # Column data : name, layer_path, layer
        self.set_column_types((str, object, object))
        default_selection = C_(
            "fill option: default layer to use for"
            "fill unless (sample merged) is enabled",
            u"Selected Layer"
        )
        # Add default option and separator
        self.append((default_selection, None, None))
        self.append((None, None, None))
        # Flatten layer tree into rows
        for layer in root_stack:
            self._initalize(layer)

    def _layer_props_changed_cb(self, root, layerpath, layer, changed):
        """Update copies of layer names when changed"""
        if 'name' in changed:
            for item in self:
                if item[1] == layerpath:
                    item[0] = layer.name
                    return

    def _layer_inserted_cb(self, root, path):
        """Create a row for the inserted layer and update
        the paths of existing layers if necessary
        """
        layer = root.deepget(path)
        new_row = (layer.name, path, layer)
        for item in self:
            item_path = item[1]
            if item_path and path <= item_path:
                row_iter = item.iter
                self.insert_before(row_iter, new_row)
                self._update_paths(row_iter)
                return
        # If layer added to bottom, no other updates necessary
        self.append(new_row)

    def _layer_deleted_cb(self, root, path):
        """Remove the row for the deleted layer, and also any
        rows for layers that were children of the deleted layer
        """
        def is_child(p):
            return lib.layer.path_startswith(p, path)

        for item in self:
            if item[1] == path:
                row = item.iter
                # Remove rows for all children
                while self.remove(row) and is_child(self[row][1]):
                    pass
                # Update rows (if any) below last deleted
                if self.iter_is_valid(row):
                    self._update_paths(row)
                return

    def _update_paths(self, row_iter):
        """Update the paths for existing layers
        at or below the point of the given iterator
        """
        while row_iter:
            item = self[row_iter]
            path = self.root.deepindex(item[2])
            if path is not None:
                item[1] = path
            row_iter = self.iter_next(row_iter)

    def _initalize(self, layer):
        """Add a new row for the layer (unless it is the root)
        Subtrees are added recursively, depth-first traversal.
        """
        # if layer is not self.root:
        name = layer.name
        path = self.root.deepindex(layer)
        self.append((name, path, layer))
        if isinstance(layer, lib.layer.LayerStack):
            for child in layer:
                self._initalize(child)

/* This file is part of MyPaint.
 * Copyright (C) 2019 by the MyPaint Development Team.
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 */

#include "fill_common.hpp"
#include "fill_constants.hpp"

/*
  Helper function to copy a rectangular slice of the input
  buffer to the full input array.
*/
static void
init_rect(
    const int x, const int w, const int y, const int h,
    PixelBuffer<chan_t> input_buf, chan_t** input, const int px_x,
    const int px_y)
{
    PixelRef<chan_t> in_px = input_buf.get_pixel(px_x, px_y);
    for (int y_i = y; y_i < y + h; ++y_i) {
        for (int x_i = x; x_i < x + w; ++x_i) {
            input[y_i][x_i] = in_px.read();
            in_px.move_x(1);
        }
        in_px.move_x(0 - w);
        in_px.move_y(1);
    }
}

GridVector
nine_grid(PyObject* tile_coord, PyObject* tiles)
{
    const int num_tiles = 9;
    const int offs[]{-1, 0, 1};

    int x, y;

    PyGILState_STATE gstate;
    gstate = PyGILState_Ensure();

    PyArg_ParseTuple(tile_coord, "ii", &x, &y);
    std::vector<PixelBuffer<chan_t>> grid;

    for (int i = 0; i < num_tiles; ++i) {
        int _x = x + offs[i % 3];
        int _y = y + offs[i / 3];
        PyObject* c = Py_BuildValue("ii", _x, _y);
        PyObject* tile = PyDict_GetItem(tiles, c);
        Py_DECREF(c);
        if (tile)
            grid.push_back(PixelBuffer<chan_t>(tile));
        else
            grid.push_back(
                PixelBuffer<chan_t>(ConstTiles::ALPHA_TRANSPARENT()));
    }
    PyGILState_Release(gstate);

    return grid;
}

void
init_from_nine_grid(
    int radius, chan_t** input, bool from_above, GridVector grid)
{
    const int r = radius;

// Using macro here to avoid performance hit on gcc <= 5.4
#define B (N - r)
#define E (N + r)
    if (from_above) {
        // Reuse radius*2 rows from previous morph
        // and no need to handle the topmost tiles
        for (int i = 0; i < r * 2; ++i) {
            chan_t* tmp = input[i];
            input[i] = input[N + i];
            input[N + i] = tmp;
        } // west, mid, east: bottom (N-r) rows
        init_rect(0, r, 2 * r, B, grid[3], input, B, r);
        init_rect(r, N, 2 * r, B, grid[4], input, 0, r);
        init_rect(E, r, 2 * r, B, grid[5], input, 0, r);
    } else { // nw, north, ne
        init_rect(0, r, 0, r, grid[0], input, B, B);
        init_rect(r, N, 0, r, grid[1], input, 0, B);
        init_rect(E, r, 0, r, grid[2], input, 0, B);

        // west, mid, east
        init_rect(0, r, r, N, grid[3], input, B, 0);
        init_rect(r, N, r, N, grid[4], input, 0, 0);
        init_rect(E, r, r, N, grid[5], input, 0, 0);
    }
    // sw, south, se
    init_rect(0, r, E, r, grid[6], input, B, 0);
    init_rect(r, N, E, r, grid[7], input, 0, 0);
    init_rect(E, r, E, r, grid[8], input, 0, 0);

#undef B
#undef E
}

int
num_strand_workers(int num_strands, int min_strands_per_worker)
{
    int max_threads = std::thread::hardware_concurrency();
    int max_by_strands = num_strands / min_strands_per_worker;
    return MIN(max_threads, max_by_strands);
}

void
process_strands(
    worker_function worker, int offset, int min_strands_per_worker,
    PyObject* strands, PyObject* tiles, PyObject* result)
{
    Py_ssize_t num_strands = PyList_GET_SIZE(strands);
    int num_threads = num_strand_workers(num_strands, min_strands_per_worker);

    std::vector<std::thread> threads(num_threads);
    std::vector<std::future<PyObject*>> futures(num_threads);

    PyEval_InitThreads();
    StrandQueue work_queue(strands);

    // Create worker threads
    for (int i = 0; i < num_threads; ++i) {
        std::promise<PyObject*> promise;
        futures[i] = promise.get_future();
        threads[i] = std::thread(
            worker, offset, std::ref(work_queue), tiles, std::move(promise));
    }
    // Release the lock to let the workers work
    Py_BEGIN_ALLOW_THREADS

    for (int i = 0; i < num_threads; ++i)
    {
        // Wait for the output from the threads
        // and merge it into the final result
        futures[i].wait();
        PyObject* _m = futures[i].get();
        PyGILState_STATE state;
        state = PyGILState_Ensure();
        PyDict_Update(result, _m);
        Py_DECREF(_m);
        PyGILState_Release(state);
        threads[i].join();
    }

    Py_END_ALLOW_THREADS
}

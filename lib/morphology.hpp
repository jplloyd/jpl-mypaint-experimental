/* This file is part of MyPaint.
 * Copyright (C) 2018 by the MyPaint Development Team.
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 */

#ifndef MORPH_HPP
#define MORPH_HPP

#include "floodfill.hpp"

/*
  Chords make up the structuring elements used to perform morphological
  transformations (erosion/dilation etc.).

  Since the morph functions are using the Urbach-Wilkinson algorithm,
  instead of storing the actual chord lengths, an index to the length
  is stored, avoiding redundant lookups/tests for chords of the same
  lengths..
*/

#ifdef SWIG
%ignore chord;
#endif

struct chord
{
    chord() : x_offset (0), length_index (0) {}
    chord(int x, int len_i) : x_offset(x), length_index(len_i) {};
    int x_offset;
    int length_index;
};


// Only create wrappers for the bucket constructor
#ifdef SWIG
%ignore MorphBucket::rotate_lut();
%ignore MorphBucket::initiate;
#endif

// Comparison operation type used to template dilation/erosion
typedef chan_t op(chan_t, chan_t);

/*
  Initiates and stores data shared between tile morph operations
  and allocates space reused between morphs, specifically:

  Circular structuring element data - radius/height/chords

  Lookup table (height x N x unique_chord_lengths) for linear(-ish) morph

  Input array (N + radius*2)^2 storing the pixels necessary to perform morph
  for the given radius - rotated/updated whenever possible.

  Output array to store morphed alpha values (consider removing/replacing).
*/
class MorphBucket
{
public:
    explicit MorphBucket(int radius);
    ~MorphBucket();
    void rotate_lut();
    template <op cmp>
    void populate_row(int, int);
    template <chan_t init, chan_t lim, op cmp>
    void morph(bool can_update, PixelBuffer<chan_t>& dst);
    template <chan_t lim>
    bool can_skip(PixelBuffer<chan_t> buf);
    void initiate(
        bool can_update,
        PyObject *src_mid,
        PyObject *src_n, PyObject *src_e,
        PyObject *src_s, PyObject *src_w,
        PyObject *src_ne, PyObject *src_se,
        PyObject *src_sw, PyObject *src_nw);
private:
    int radius; // structuring element radius
    int height; // structuring element height
    std::vector<chord> se_chords; // structuring element chords
    std::vector<int> se_lengths; // structuring element chord lengths
    chan_t ***table; // lookup table for uw algorithm (y-offset, x, type)
    chan_t **input; // input 2d array populated by 3x3 input tile grid
};

PyObject *dilate(
    MorphBucket &mb,
    bool can_update,
    PyObject *src_mid,
    PyObject *src_n, PyObject *src_e,
    PyObject *src_s, PyObject *src_w,
    PyObject *src_ne, PyObject *src_se,
    PyObject *src_sw, PyObject *src_nw);

PyObject *erode(
    MorphBucket &mb,
    bool can_update,
    PyObject *src_mid,
    PyObject *src_n, PyObject *src_e,
    PyObject *src_s, PyObject *src_w,
    PyObject *src_ne, PyObject *src_se,
    PyObject *src_sw, PyObject *src_nw);


#ifdef SWIG
%ignore BlurBucket::radius;
%ignore BlurBucket::height;
%ignore BlurBucket::input_full;
%ignore BlurBucket::input_vert;
%ignore BlurBucket::output;
#endif

/*
  Holds data and allocated space used to perform
  tile-wise box blur.
*/

class BlurBucket
{
public:
    explicit BlurBucket(int radius);
    ~BlurBucket();
    const int radius;
    const int height;
    chan_t **input_full;
    chan_t **input_vert;
    chan_t output[N][N];
};

/*
  Performs a simple box blur on the source tile, outputting
  the blurred alphas to the destination tile.
*/
void blur(BlurBucket &bb, bool can_update,
          PyObject *src_mid, PyObject* dst_tile,
          PyObject *src_n, PyObject *src_e,
          PyObject *src_s, PyObject *src_w,
          PyObject *src_ne, PyObject *src_se,
          PyObject *src_sw, PyObject *src_nw);


// Gapclosing fill data utilities

#ifdef SWIG
%ignore DistanceBucket::distance;
%ignore DistanceBucket::input;
#endif

// Distance data bucket for gap closing
class DistanceBucket
{
public:
    explicit DistanceBucket(int distance);
    ~DistanceBucket();
    const int distance;
    chan_t **input;
};

// Check if there are unfillable pixels in the corners
// of the given N,E,S,W tiles that might result in gaps that
// cross their central neighbour.
// NOTE: a negative result does not guarantee that any actual detectable
// gaps exist, but a positive result guarantees that they do _not_ exist
bool no_corner_gaps(
    int distance,
    PyObject *src_n,
    PyObject *src_e,
    PyObject *src_s,
    PyObject *src_w);

// Search the given nine-grid of flooded alpha tiles for
// gaps up to a certain length, defined by the DistanceBucket,
// writing the lengths found to the given distance tile
void find_gaps(
    DistanceBucket &bucket,
    PyObject *gap_output,
    PyObject *src_mid,
    PyObject *src_n,
    PyObject *src_e,
    PyObject *src_s,
    PyObject *src_w,
    PyObject *src_ne,
    PyObject *src_se,
    PyObject *src_sw,
    PyObject *src_nw);

void test_threading(int some_number);

#endif

# This file is part of MyPaint.
# Copyright (C) 2018-2019 by the MyPaint Development Team.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.

"""This module implements tile-based morphological operations;
dilation, erosion and blur
"""
import math
import logging
import sys

import multiprocessing as mp
import numpy as np

import lib.mypaintlib as myplib

import lib.fill_common as fc
from lib.fill_common import _FULL_TILE, _EMPTY_TILE

from lib.pycompat import PY3

N = myplib.TILE_SIZE

logger = logging.getLogger(__name__)


def adjacent_tiles(tile_coord, filled):
    """ Return a tuple of tiles adjacent to the input tile coordinate.
    Adjacent tiles that are not in the tileset are replaced by the empty tile.
    """
    return tuple([filled.get(c, _EMPTY_TILE) for c in fc.adjacent(tile_coord)])


# Constants acting as placeholders when distributing
# heavy morphological workloads across worker processes
_EMPTY_TILE_PH = 0
_FULL_TILE_PH = 1


def unproxy(tile):
    """Switch out proxy values to corresponding tile references

    This is used when distributing heavy morphological operations
    across multiple working processes, where the direct references
    cannot be used because the memory is not shared.
    """
    if isinstance(tile, int):
        return [_EMPTY_TILE, _FULL_TILE][tile]
    else:
        return tile


def complement_adjacent(tiles):
    """ Ensure that each tile in the input tileset has a full neighbourhood
    of eight tiles, setting missing tiles to the empty tile.

    The new set should only be used as input to tile operations, as the empty
    tile is readonly.
    """
    new = {}
    for tile_coord in tiles.keys():
        for adj_coord in fc.adjacent(tile_coord):
            if adj_coord not in tiles and adj_coord not in new:
                new[adj_coord] = _EMPTY_TILE
    tiles.update(new)


def directly_below(coord1, coord2):
    """ Return true if the first coordinate is directly below the second"""
    return coord1[0] == coord2[0] and coord1[1] == coord2[1] + 1


def tile_partition(tiles, dilating=False):
    """Partition input tiles for easier processing
    This function partitions a tile dictionary into
    two parts: one dictionary containing tiles that
    do not need to be processed further (see note),
    and list of coordinate lists, where each list
    contains vertically contiguous coordinates,
    ordered from low to high.

    note: Tiles that never need further processing are
    those that are fully opaque and with a full neighbourhood
    of identical tiles. If the "dilating" parameter is set
    to true, just being fully opaque is enough.
    :return: (final_dict, strands_list, num_strand_tiles)
    """
    # Dict of coord->tile for tiles that need no further processing
    final = {}
    # Groups of contiguous tile coordinates
    result = []
    group = []
    previous = None
    strand_tiles = 0
    coords = tiles.keys()
    for tile_coord in sorted(coords):
        ft = tiles[tile_coord] is _FULL_TILE
        if ft and (dilating or adj_full(tile_coord, tiles)):
            final[tile_coord] = _FULL_TILE
            previous = None
            if group:
                result.append(group)
                group = []
        elif previous is None or directly_below(tile_coord, previous):
            group.append(tile_coord)
            strand_tiles += 1
        else:
            result.append(group)
            group = [tile_coord]
            strand_tiles += 1
        previous = tile_coord
    if group:
        result.append(group)
    return final, result, strand_tiles


def triples(num):
    """ Return a tuple of three minimally different
    terms whose sum equals the given integer argument
    """
    fraction = num / 3.0
    whole = num // 3
    floor = int(math.floor(fraction))
    ceil = int(math.ceil(fraction))
    if fraction - whole >= 0.5:
        return (ceil, ceil, floor)
    else:
        return (ceil, floor, floor)


def morph(offset, tiles):
    """ Either dilate or erode the given set of alpha tiles, depending
    on the sign of the offset, returning the set of morphed tiles.
    """
    # operation = myplib.dilate if offset > 0 else myplib.erode
    # Radius of the structuring element used in the morph
    # se_size = abs(offset)
    # When dilating, create new tiles to account for edge overflow
    # (without checking if they are actually needed)
    if offset > 0:
        complement_adjacent(tiles)

    # Split up the coordinates of the tiles to morphed into
    # contiguous strands, which can be processed more efficiently
    morphed, strands, num_strand_tiles = tile_partition(tiles)

    print("Prior to call")
    myplib.morph(offset, num_strand_tiles, morphed, tiles, strands)
    print("After call")
    if morphed:
        print("Back here again, morphed is not none!")
        print("Length of dict: ", len(morphed))
    else:
        print("Morphed is somehow None!")

    return morphed

    # Use a rough heuristic based on the number of tiles that need
    # processing and the size of the erosion/dilation
    # cpus = mp.cpu_count()
    # wanted_num_workers = int(math.sqrt(2*num_strand_tiles * se_size) // 50)
    # num_workers = min(cpus, wanted_num_workers)

    # # Try to use worker processes for large/heavy morphs
    # if False and num_workers > 1 and sys.platform != "win32":
    #     try:
    #         return morph_multi(
    #             num_workers, offset, tiles,
    #             operation, strands, morphed
    #         )
    #     except Exception:
    #         logger.warn("Multiprocessing failed, using single core fallback")

    # # Don't use workers for small workloads
    # skip_t = _EMPTY_TILE if offset < 0 else _FULL_TILE
    # bucket = myplib.MorphBucket(se_size)
    # for strand in strands:
    #     morph_strand(
    #         tiles, offset > 0,
    #         bucket, operation,
    #         skip_t, _FULL_TILE, strand, morphed
    #     )
    # return morphed


def morph_multi(
    num_workers, offset, tiles,
    operation, strands, morphed
):
    """Set up worker processes and a work queue to
    split up the morphological operations
    """
    # Set up IPC communication channels and tile constants
    strand_queue = mp.Queue()
    morph_results = mp.Queue()
    # Use int constants instead of tile references, since
    # the references won't be the same for the workers
    skip_tile = _EMPTY_TILE_PH if offset < 0 else _FULL_TILE_PH
    # Create and start the worker processes
    for _ in range(num_workers):
        worker = mp.Process(
            target=morph_worker,
            args=(
                tiles, strand_queue,
                morph_results, offset, operation, skip_tile, _FULL_TILE
            )
        )
        worker.start()
    # Populate the work queue with strands
    for strand in strands:
        strand_queue.put(strand)
    # Add a stop-signal value for each worker
    for signal in (None,) * num_workers:
        strand_queue.put(signal)
    # Merge the resulting tile dicts, replacing proxy constants
    # with their corresponding references for full/empty tiles
    for _ in range(num_workers):
        result = morph_results.get()
        result_items = result.items() if PY3 else result.iteritems()
        for tile_coord, tile in result_items:
            morphed[tile_coord] = unproxy(tile)
    return morphed


def morph_strand(
        tiles, skip_full, morph_bucket,
        operation, skip_tile, full_tile, keys, morphed, full_ref=_FULL_TILE):
    """ Apply a morphological operation to a strand of alpha tiles.

    Operates on vertical strands of tiles (same x-coordinate) to
    maximize the potential reuse of the UW* lookup table when moving from
    one tile to the next. Skipping tiles is still faster and therefore
    always prioritized when possible.

    * Urbach-Wilkinson (https://doi.org/10.1109/TIP.2007.9125824)
    """
    can_update = False  # reuse most of the data from the previous operation
    for tile_coord in keys:
        center_tile = tiles[tile_coord]
        # Perform the dilation/erosion
        no_skip, morphed_tile = operation(
            morph_bucket, can_update, center_tile,
            *adjacent_tiles(tile_coord, tiles)
        )
        # For very large radii, a small search is performed to see
        # if the actual morph operation can be skipped with the result
        # being either an empty or a full alpha tile.
        if no_skip:
            can_update = True
            # Skip the resulting tile if it is empty
            if center_tile is _EMPTY_TILE and not morphed_tile.any():
                continue
            morphed[tile_coord] = morphed_tile
        else:
            can_update = False
            morphed[tile_coord] = skip_tile


def morph_worker(
        tiles, strand_queue, results,
        offset, morph_op, skip_tile, full_ref):
    """ tile morphing worker function invoked by separate processes
    """
    morph_bucket = myplib.MorphBucket(abs(offset))
    morphed = {}
    # Fetch and process strands from the work queue
    # until a stop signal value is fetched
    while True:
        keys = strand_queue.get()
        if keys is None:
            break
        morph_strand(
            tiles, offset > 0, morph_bucket, morph_op,
            skip_tile, _FULL_TILE_PH, keys, morphed, full_ref=full_ref)
    results.put(morphed)


def blur(feather, tiles):
    """ Return the set of blurred tiles based on the input tiles.
    """
    # Single pixel feathering uses a single box blur
    # radiuses > 2 uses three iterations with radiuses
    # adding up to the feather radius
    if feather == 1:
        radiuses = (1,)
    elif feather == 2:
        radiuses = (1, 1)
    else:
        radiuses = triples(feather)

    # Only expand the the tile coverage once, assuming a maximum
    # total blur radius (feather value) of TILE_SIZE
    complement_adjacent(tiles)
    prev_radius = 0
    blur_bucket = None
    for radius in radiuses:
        if prev_radius != radius:
            blur_bucket = myplib.BlurBucket(radius)
        tiles = blur_pass(tiles, blur_bucket)
    return tiles


def adj_full(coord, tiles):
    return all(t is _FULL_TILE for t in adjacent_tiles(coord, tiles))


def blur_pass(tiles, blur_bucket):
    """Perform a single box blur pass for the given input tiles,
    returning the (potential) superset of blurred tiles"""
    # For each pass, create a new tile set for the blurred output,
    # which is then used as input for the next pass
    blurred, strands = tile_partition(tiles, dilating=False)[:2]
    for strand in strands:
        can_update = False
        for tile_coord in strand:
            alpha_tile = tiles[tile_coord]
            # run the box blur on the input tiles
            new = np.empty((N, N), 'uint16')
            blurred[tile_coord] = new
            myplib.blur(
                blur_bucket, can_update,
                alpha_tile, new, *adjacent_tiles(tile_coord, tiles)
            )
            can_update = True
    return blurred

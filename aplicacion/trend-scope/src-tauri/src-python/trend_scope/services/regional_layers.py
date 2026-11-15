"""Shared result metadata for temporal layers."""


def temporal_layer(kind, area, start, end, field, **data):
    span = (end - start).days + 1
    cadence = "daily" if span <= 93 else "monthly" if span <= 3652 else "yearly"
    return {"kind": kind, "area": area, "start": str(start), "end": str(end),
            "cadence": cadence, "field": field, **data}


def spatial_blocks(geometry, bounds, tile=30):
    """Return non-overlapping search blocks that touch the area."""
    west, south, east, north = bounds
    if east - west <= tile and north - south <= tile:
        return [(west, south, east, north)]

    from rasterio.features import geometry_mask
    from rasterio.transform import from_origin

    touched = geometry_mask([geometry], (round(180 / tile), round(360 / tile)), from_origin(-180, 90, tile, tile),
                            invert=True, all_touched=True)
    return [(max(west, -180 + col * tile), max(south, 90 - (row + 1) * tile),
             min(east, -180 + (col + 1) * tile), min(north, 90 - row * tile))
            for row, col in zip(*touched.nonzero())
            if max(west, -180 + col * tile) < min(east, -180 + (col + 1) * tile)
            and max(south, 90 - (row + 1) * tile) < min(north, 90 - row * tile)]

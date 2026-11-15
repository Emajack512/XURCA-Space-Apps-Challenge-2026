"""Run with python -m trend_scope.raster.manual_check; writes real fixtures only."""
from dataclasses import asdict
from pathlib import Path
import json
import numpy as np
from .contract import GridRequest
from .providers import fetch_grid

def main():
    folder = Path(__file__).with_name("fixtures")
    folder.mkdir(exist_ok=True)
    failures = []
    # Open-Meteo uses a 0.5 x 0.5 degree box (9 ERA5 cells, ~243 weighted calls) to fit the free quota.
    for provider, variable, start, end, cadence, bbox in [
        ("nasa.power.regional.monthly", "T2M", "2000-01-01", "2024-12-31", "monthly", (-67., -35., -65., -33.)),
        ("openmeteo.era5.daily", "temperature_2m_mean", "2023-01-01", "2023-12-31", "daily", (-66.5, -33.75, -66., -33.25))]:
        try:
            field = fetch_grid(GridRequest(provider, variable, start, end, cadence, bbox)).validate()
            metadata = asdict(field)
            arrays = {key: metadata.pop(key) for key in ("values", "lats", "lons", "mask")}
            np.savez_compressed(folder / (provider + ".npz"), **arrays)
            (folder / (provider + ".json")).write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
            finite = field.values[np.isfinite(field.values)]
            print(provider, field.values.shape,
                  (finite.min(), finite.max()) if finite.size else "sin datos",
                  "cobertura", field.coverage_fraction().min(), field.coverage_fraction().max(),
                  "URLs", *field.urls, sep="\n")
        except ValueError as error:
            failures.append(provider)
            print(provider, str(error))
    if failures:
        raise SystemExit("Fallaron: " + ", ".join(failures))

if __name__ == "__main__":
    main()

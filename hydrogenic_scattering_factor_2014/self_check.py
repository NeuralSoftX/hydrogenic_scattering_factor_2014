# Copyright 2026 Ivan Lobato / NeuralSoftX
# SPDX-License-Identifier: Apache-2.0
# Email: ivan.lobato@neuralsoftx.com
"""Self-check of a released payload: archives complete and physics identities hold.

Author: Ivan Lobato
"""
from __future__ import annotations

import h5py
import numpy as np

from .evaluator import (
    A_0,
    DEFAULT_COEFFICIENTS,
    DEFAULT_REFERENCE,
    INVERSE_KAPPA,
    available_models,
    electron_scattering_factor,
    load_coefficients,
)

Z_MAX = 103
REFERENCE_RESIDUAL_LIMIT = 5e-2


def _check_coefficients() -> list[str]:
    failures = []
    for model in available_models():
        for z in range(1, Z_MAX + 1):
            coef = load_coefficients(z, model)
            if coef.n_terms != 5:
                failures.append(f'{model} Z={z}: {coef.n_terms} terms')
            value = 2.0 * np.pi**2 * A_0 * float(np.sum(coef.a / coef.b))
            if abs(value - z) / z > 1e-6:
                failures.append(f'{model} Z={z}: charge sum {value} != {z}')
    return failures


def _check_references() -> list[str]:
    failures = []
    with h5py.File(DEFAULT_REFERENCE, 'r') as handle:
        for model in available_models():
            if model not in handle:
                failures.append(f'reference archive lacks model {model}')
                continue
            group = handle[model]
            worst = 0.0
            for z in range(1, Z_MAX + 1):
                element = group[f'Z{z:03d}']
                grid = np.asarray(element['feg_g'][...], dtype=np.float64)
                target = np.asarray(element['feg'][...], dtype=np.float64)
                curve = electron_scattering_factor(load_coefficients(z, model), grid)
                worst = max(
                    worst,
                    float(np.max(np.abs(curve - target))) / float(np.max(np.abs(target))),
                )
            if worst > REFERENCE_RESIDUAL_LIMIT:
                failures.append(f'{model}: reference residual {worst:.3e}')
    return failures


def _check_potential() -> list[str]:
    failures = []
    for z in (1, 6, 29, 103):
        coef = load_coefficients(z)
        decay = 2.0 * np.pi / np.sqrt(coef.b)
        amplitude = np.pi**2 * INVERSE_KAPPA * coef.a / coef.b**1.5
        r = 1e-10
        x = r * decay
        limit = float(np.sum(amplitude * np.exp(-x) * (2.0 / x + 1.0))) * r
        if abs(limit) <= 0.0 or not np.isfinite(limit):
            failures.append(f'Z={z}: non-finite short-range potential limit')
    return failures


def main() -> int:
    """Run every payload self-check and report the outcome."""
    failures = _check_coefficients() + _check_references() + _check_potential()
    if failures:
        print('hydrogenic_scattering_factor_2014 self-check FAILED')
        for item in failures[:20]:
            print(f'  {item}')
        return 1
    models = ', '.join(available_models())
    print(f'hydrogenic_scattering_factor_2014 self-check OK ({models}; Z = 1-{Z_MAX})')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

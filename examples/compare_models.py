#!/usr/bin/env python3
# Copyright 2026 Ivan Lobato / NeuralSoftX
# SPDX-License-Identifier: Apache-2.0
# Email: ivan.lobato@neuralsoftx.com
"""Print the released models for one element side by side.

Author: Ivan Lobato
"""
from __future__ import annotations

import argparse

import numpy as np

from hydrogenic_scattering_factor_2014 import (
    MODEL_PUBLISHED,
    MODEL_REFIT,
    available_models,
    electron_density,
    electron_scattering_factor,
    load_coefficients,
    xray_scattering_factor,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--element', type=int, default=29, help='atomic number')
    args = parser.parse_args()

    print('released models:', ', '.join(available_models()))
    grid = np.linspace(0.0, 12.0, 13)
    for model in (MODEL_PUBLISHED, MODEL_REFIT):
        coef = load_coefficients(args.element, model)
        print(f'\n{model}  Z={coef.atomic_number} {coef.symbol}  n_t={coef.n_terms}')
        print(f'  f_x(0) = {xray_scattering_factor(coef, 0.0):.6f}   rho(0) = '
              f'{electron_density(coef, 0.0):.6e} e/A^3')
        print('  g (1/A)   f_e (A)')
        for g in grid:
            print(f'  {g:8.3f}  {electron_scattering_factor(coef, float(g)):12.6e}')


if __name__ == '__main__':
    main()

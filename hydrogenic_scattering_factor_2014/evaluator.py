# Copyright 2026 Ivan Lobato / NeuralSoftX
# SPDX-License-Identifier: Apache-2.0
# Email: ivan.lobato@neuralsoftx.com
"""Evaluate the released hydrogenic scattering factors, densities and potentials.

Author: Ivan Lobato
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import h5py
import numpy as np

HERE = Path(__file__).resolve().parent
DATA_ROOT = HERE / 'data'
DEFAULT_COEFFICIENTS = DATA_ROOT / 'coefficients.h5'
DEFAULT_REFERENCE = DATA_ROOT.parent / 'reference' / 'reference_dirac_fock.h5'

A_0 = 0.52917721077817892
INVERSE_KAPPA = 47.877642131544313031
MODEL_PUBLISHED = 'kirkland_multiconfig_dirac_fock_1998'
MODEL_REFIT = 'kirkland_average_configuration_2010'
N_TERMS = 5
# The group returned when a caller does not name one. This is the refit against
# Kirkland's 2010 table, which is also the group MULTEM uses by default, so the
# library and the simulation code agree out of the box. MODEL_PUBLISHED remains the
# published parameterisation and must be named explicitly by a caller reproducing
# the 2014 paper's numbers.
MODEL_DEFAULT = MODEL_REFIT


@dataclass(frozen=True)
class coefficients:
    """Immutable coefficient set for one element and one released model."""

    model: str
    atomic_number: int
    symbol: str
    a: np.ndarray
    b: np.ndarray

    @property
    def n_terms(self) -> int:
        """Return the number of basis terms."""
        return int(self.a.size)


def available_models(path: str | Path = DEFAULT_COEFFICIENTS) -> tuple[str, ...]:
    """Return the model names present in a coefficient archive."""
    with h5py.File(_archive_path(path), 'r') as handle:
        return tuple(handle.keys())


def available_elements(
    model: str = MODEL_DEFAULT,
    path: str | Path = DEFAULT_COEFFICIENTS,
) -> tuple[tuple[int, str], ...]:
    """Return ``(atomic_number, symbol)`` pairs for one model."""
    archive = _archive_path(path)
    with h5py.File(archive, 'r') as handle:
        group = _model_group(handle, model, archive)
        elements = [
            (int(group[key].attrs['Z']), str(group[key].attrs['symbol']))
            for key in group
        ]
    return tuple(sorted(elements))


def load_coefficients(
    atomic_number: int,
    model: str = MODEL_DEFAULT,
    path: str | Path = DEFAULT_COEFFICIENTS,
) -> coefficients:
    """Load one element's released coefficients as float64 arrays."""
    if isinstance(atomic_number, bool) or not isinstance(atomic_number, (int, np.integer)):
        raise TypeError('atomic_number must be an integer in the released range')
    z = int(atomic_number)
    archive = _archive_path(path)
    with h5py.File(archive, 'r') as handle:
        group = _model_group(handle, model, archive)
        matches = [key for key in group if int(group[key].attrs['Z']) == z]
        if len(matches) != 1:
            available = sorted(int(group[key].attrs['Z']) for key in group)
            if not available:
                raise ValueError(f'model {model!r} contains no elements in {archive}')
            raise ValueError(
                f'atomic_number={z} is unavailable for model {model!r}; '
                f'released range is {available[0]}..{available[-1]}'
            )
        item = group[matches[0]]
        a = np.asarray(item['a'][...], dtype=np.float64)
        b = np.asarray(item['b'][...], dtype=np.float64)
        term_types = np.asarray(item['type'][...])
        symbol = str(item.attrs['symbol'])
        declared = item.attrs['n_t']

    if a.ndim != 1 or a.shape != b.shape or a.shape != term_types.shape:
        raise ValueError(
            f'invalid coefficient schema for model={model!r}, Z={z}: '
            f'a={a.shape}, b={b.shape}, type={term_types.shape}'
        )
    if a.size != N_TERMS:
        raise ValueError(
            f'model={model!r}, Z={z} carries {a.size} terms; the hydrogenic basis is '
            f'{N_TERMS} terms'
        )
    if int(declared) != a.size:
        raise ValueError(
            f'n_t={declared!r} disagrees with the coefficient count {a.size} '
            f'for model={model!r}, Z={z}'
        )
    if not np.all(np.isfinite(a)) or not np.all(np.isfinite(b)):
        raise ValueError(f'non-finite coefficients for model={model!r}, Z={z}')
    if not np.all(b > 0.0):
        raise ValueError(f'non-positive width coefficient for model={model!r}, Z={z}')
    if not np.all(term_types == b'NR'):
        raise ValueError(
            f'model={model!r}, Z={z} must contain only non-relativistic terms'
        )
    for array in (a, b, term_types):
        array.setflags(write=False)
    return coefficients(model, z, symbol, a, b)


def electron_scattering_factor(
    coef: coefficients,
    g: float | np.ndarray,
) -> float | np.ndarray:
    """Evaluate the electron scattering factor ``f_e(g)`` in ångström."""
    values, shape, scalar = _coordinates(g, name='g', allow_zero=True)
    b_g2 = coef.b[None, :] * values[:, None] ** 2
    result = (coef.a[None, :] * (2.0 + b_g2) / (1.0 + b_g2) ** 2).sum(axis=1)
    return _restore_shape(result, shape, scalar)


def xray_scattering_factor(
    coef: coefficients,
    g: float | np.ndarray,
) -> float | np.ndarray:
    """Evaluate the X-ray scattering factor ``f_x(g)`` in electrons."""
    values, shape, scalar = _coordinates(g, name='g', allow_zero=True)
    b_g2 = coef.b[None, :] * values[:, None] ** 2
    amplitude = 2.0 * np.pi**2 * A_0 * coef.a / coef.b
    result = (amplitude[None, :] / (1.0 + b_g2) ** 2).sum(axis=1)
    return _restore_shape(result, shape, scalar)


def electron_density(
    coef: coefficients,
    r: float | np.ndarray,
) -> float | np.ndarray:
    """Evaluate the electron density ``rho(r)`` in electrons per ångström cubed."""
    values, shape, scalar = _coordinates(r, name='r', allow_zero=True)
    decay = 2.0 * np.pi / np.sqrt(coef.b)
    amplitude = 2.0 * np.pi**4 * A_0 * coef.a / coef.b**2.5
    result = (amplitude[None, :] * np.exp(-values[:, None] * decay[None, :])).sum(axis=1)
    return _restore_shape(result, shape, scalar)


def electrostatic_potential(
    coef: coefficients,
    r: float | np.ndarray,
) -> float | np.ndarray:
    """Evaluate the radial electrostatic potential ``V(r)`` for strictly positive ``r``."""
    values, shape, scalar = _coordinates(r, name='r', allow_zero=False)
    decay = 2.0 * np.pi / np.sqrt(coef.b)
    amplitude = np.pi**2 * INVERSE_KAPPA * coef.a / coef.b**1.5
    x = values[:, None] * decay[None, :]
    result = (amplitude[None, :] * np.exp(-x) * (2.0 / x + 1.0)).sum(axis=1)
    return _restore_shape(result, shape, scalar)


def projected_potential(
    coef: coefficients,
    radius: float | np.ndarray,
) -> float | np.ndarray:
    """Evaluate the projected potential ``V(R)`` for strictly positive ``R``."""
    from scipy.special import kv

    values, shape, scalar = _coordinates(radius, name='radius', allow_zero=False)
    decay = 2.0 * np.pi / np.sqrt(coef.b)
    amplitude = 2.0 * np.pi**2 * INVERSE_KAPPA * coef.a / coef.b**1.5
    columns = values[:, None]
    x = columns * decay[None, :]
    k0 = kv(0, x)
    k1 = kv(1, x)
    result = (
        amplitude[None, :] * (2.0 * k0 / decay[None, :] + columns * k1)
    ).sum(axis=1)
    return _restore_shape(result, shape, scalar)


def _archive_path(path: str | Path) -> Path:
    archive = Path(path).expanduser().resolve()
    if not archive.is_file():
        raise FileNotFoundError(f'coefficient archive not found: {archive}')
    return archive


def _model_group(handle: h5py.File, model: str, archive: Path) -> h5py.Group:
    if not isinstance(model, str) or not model:
        raise TypeError('model must be a non-empty string')
    if model not in handle:
        raise ValueError(
            f'model {model!r} is unavailable in {archive}; '
            f'available: {sorted(handle.keys())}'
        )
    return handle[model]


def _coordinates(
    value: float | np.ndarray,
    name: str,
    allow_zero: bool,
) -> tuple[np.ndarray, tuple[int, ...], bool]:
    array = np.asarray(value, dtype=np.float64)
    scalar = array.ndim == 0
    flat = array.reshape(-1) if not scalar else array.reshape(1)
    if not np.all(np.isfinite(flat)):
        raise ValueError(f'{name} must be finite')
    if allow_zero:
        if np.any(flat < 0.0):
            raise ValueError(f'{name} must be non-negative')
    elif np.any(flat <= 0.0):
        raise ValueError(f'{name} must be strictly positive')
    return flat, array.shape, scalar


def _restore_shape(result: np.ndarray, shape: tuple[int, ...], scalar: bool):
    if scalar:
        return float(result[0])
    return result.reshape(shape)
